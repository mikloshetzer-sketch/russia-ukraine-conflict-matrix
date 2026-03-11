import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

API_BASE_URL = "https://a.liveuamap.com/api"
REGION_ID = 0  # Ukraine
DAYS_BACK = 3
COUNT_PER_REQUEST = 200
TIMEOUT = 30

KEYWORD_CATEGORIES = {
    "air_strike": [
        "missile", "missiles", "drone", "drones", "strike", "strikes",
        "air raid", "shelling", "bombing", "explosion", "explosions",
        "ballistic", "rocket"
    ],
    "frontline": [
        "clash", "clashes", "battle", "fighting", "offensive", "advance",
        "assault", "frontline", "towards", "near", "captured"
    ],
    "civilian_impact": [
        "killed", "wounded", "injured", "civilian", "evacuation",
        "residential", "hospital", "school"
    ],
    "infrastructure": [
        "power", "substation", "electricity", "plant", "railway",
        "bridge", "port", "warehouse", "oil depot", "airport"
    ],
    "political_security": [
        "putin", "zelensky", "kremlin", "moscow", "kyiv",
        "sanctions", "nato", "eu", "talks", "ceasefire"
    ],
}

EXCLUDED_KEYWORDS = [
    "iran", "israel", "gaza", "hamas", "hezbollah", "tehran",
    "middle east", "west bank", "lebanon", "syria", "yemen", "houthi"
]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def should_exclude(title: str) -> bool:
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in EXCLUDED_KEYWORDS)


def classify_event(title: str) -> list[str]:
    title_lower = title.lower()
    matched = []

    for category, keywords in KEYWORD_CATEGORIES.items():
        if any(keyword in title_lower for keyword in keywords):
            matched.append(category)

    if not matched:
        matched.append("other")

    return matched


def unix_ts(dt: datetime) -> int:
    return int(dt.timestamp())


def request_liveuamap(api_key: str, ts: int, count: int = COUNT_PER_REQUEST):
    params = {
        "a": "mpts",
        "resid": REGION_ID,
        "time": ts,
        "count": count,
        "key": api_key,
    }

    response = requests.get(API_BASE_URL, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def pick_items(payload):
    """
    Próbál több lehetséges válaszstruktúrát kezelni.
    Mivel a pontos API response formátum nem teljesen dokumentált nálunk,
    több tipikus mezőt is megpróbálunk.
    """
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in ["data", "items", "points", "markers", "result", "news", "events"]:
        value = payload.get(key)
        if isinstance(value, list):
            return value

    return []


def parse_item_date(item, fallback_date: str) -> str:
    for key in ["date", "event_date", "published_at", "created_at"]:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            # ha már YYYY-MM-DD formátum van benne
            if re.match(r"^\d{4}-\d{2}-\d{2}", value.strip()):
                return value.strip()[:10]

    for key in ["time", "timestamp", "created", "updated"]:
        value = item.get(key)
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
            except Exception:
                pass

    return fallback_date


def parse_item_title(item) -> str:
    candidates = [
        item.get("title"),
        item.get("name"),
        item.get("text"),
        item.get("description"),
        item.get("news"),
    ]

    for c in candidates:
        c = clean_text(c)
        if c:
            return c

    return ""


def parse_item_location(item) -> str:
    candidates = [
        item.get("location"),
        item.get("place"),
        item.get("city"),
        item.get("region"),
    ]

    for c in candidates:
        c = clean_text(c)
        if c:
            return c

    lat = item.get("lat")
    lon = item.get("lng", item.get("lon"))
    if lat is not None and lon is not None:
        return f"{lat}, {lon}"

    return ""


def parse_item_link(item) -> str:
    for key in ["link", "url", "source_url"]:
        value = clean_text(item.get(key))
        if value:
            return value
    return ""


def normalize_items(raw_items, fallback_date: str):
    events = []
    seen = set()

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        title = parse_item_title(item)
        if not title:
            continue

        if should_exclude(title):
            continue

        location = parse_item_location(item)
        link = parse_item_link(item)
        event_date = parse_item_date(item, fallback_date)

        key = (event_date, title, location, link)
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "date": event_date,
            "title": title,
            "location": location,
            "published_label": "",
            "link": link,
            "categories": classify_event(title),
            "raw": item,
        })

    return events


def aggregate_daily_stats(events: list[dict]) -> list[dict]:
    grouped = {}

    for event in events:
        day = event.get("date", "")
        if not day:
            continue

        if day not in grouped:
            grouped[day] = {
                "date": day,
                "event_count": 0,
                "air_strike": 0,
                "frontline": 0,
                "civilian_impact": 0,
                "infrastructure": 0,
                "political_security": 0,
                "other": 0,
            }

        grouped[day]["event_count"] += 1

        for category in event.get("categories", []):
            if category in grouped[day]:
                grouped[day][category] += 1
            else:
                grouped[day]["other"] += 1

    return [grouped[d] for d in sorted(grouped.keys())]


def main():
    api_key = os.getenv("LIVEUAMAP_API_KEY")
    if not api_key:
        raise RuntimeError("Missing LIVEUAMAP_API_KEY environment variable")

    base_dir = Path(__file__).resolve().parent.parent
    out_dir = base_dir / "data" / "events"
    out_dir.mkdir(parents=True, exist_ok=True)

    latest_file = out_dir / "latest_events.json"
    daily_stats_file = out_dir / "daily_event_stats.json"
    raw_api_file = out_dir / "latest_liveuamap_api_raw.json"

    now = datetime.now(timezone.utc)
    oldest_day = (now.date() - timedelta(days=DAYS_BACK - 1)).isoformat()

    payload = request_liveuamap(api_key=api_key, ts=unix_ts(now), count=COUNT_PER_REQUEST)

    with open(raw_api_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    raw_items = pick_items(payload)
    events = normalize_items(raw_items, fallback_date=now.date().isoformat())

    # csak az utolsó N nap maradjon
    filtered_events = [e for e in events if e.get("date", "") >= oldest_day]
    daily_stats = aggregate_daily_stats(filtered_events)

    latest_payload = {
        "created_at": datetime.utcnow().isoformat(),
        "source": "LiveUAmap API",
        "days_back": DAYS_BACK,
        "total_events": len(filtered_events),
        "raw_item_count": len(raw_items),
        "events": filtered_events,
    }

    daily_stats_payload = {
        "created_at": datetime.utcnow().isoformat(),
        "days_back": DAYS_BACK,
        "daily_stats": daily_stats,
    }

    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(latest_payload, f, indent=2, ensure_ascii=False)

    with open(daily_stats_file, "w", encoding="utf-8") as f:
        json.dump(daily_stats_payload, f, indent=2, ensure_ascii=False)

    print(f"Raw API items: {len(raw_items)}")
    print(f"Filtered events: {len(filtered_events)}")
    print(f"Saved: {latest_file}")
    print(f"Saved: {daily_stats_file}")
    print(f"Saved raw API payload: {raw_api_file}")


if __name__ == "__main__":
    main()
