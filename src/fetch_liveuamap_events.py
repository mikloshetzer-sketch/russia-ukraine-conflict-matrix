import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


API_URL = "https://a.liveuamap.com/api"
REGION_ID = 3   # Ukraine
COUNT = 50      # a képen is 50 látszik, induljunk kisebbről
DAYS_BACK = 3
TIMEOUT = 30

KEYWORD_CATEGORIES = {
    "air_strike": [
        "missile", "missiles", "drone", "drones", "strike",
        "air raid", "shelling", "bombing", "explosion",
        "rocket", "ballistic"
    ],
    "frontline": [
        "clash", "clashes", "battle", "fighting", "offensive",
        "advance", "assault", "frontline", "captured"
    ],
    "civilian_impact": [
        "killed", "wounded", "injured", "civilian",
        "evacuation", "hospital", "school"
    ],
    "infrastructure": [
        "power", "substation", "electricity",
        "bridge", "port", "railway", "airport"
    ],
    "political_security": [
        "putin", "zelensky", "kremlin",
        "moscow", "kyiv", "sanctions", "nato",
        "talks", "ceasefire"
    ],
}

EXCLUDED_KEYWORDS = [
    "iran", "israel", "gaza", "hamas", "hezbollah",
    "tehran", "middle east", "west bank",
    "lebanon", "syria", "yemen", "houthi"
]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def should_exclude(title: str) -> bool:
    title_lower = title.lower()
    return any(k in title_lower for k in EXCLUDED_KEYWORDS)


def classify_event(title: str) -> list[str]:
    title_lower = title.lower()
    categories = []

    for category, keywords in KEYWORD_CATEGORIES.items():
        if any(k in title_lower for k in keywords):
            categories.append(category)

    if not categories:
        categories.append("other")

    return categories


def save_debug_files(base_dir: Path, response: requests.Response) -> None:
    debug_dir = base_dir / "data" / "events"
    debug_dir.mkdir(parents=True, exist_ok=True)

    body_path = debug_dir / "liveuamap_last_response.txt"
    meta_path = debug_dir / "liveuamap_last_response_meta.json"

    body_path.write_text(response.text, encoding="utf-8", errors="ignore")
    meta_path.write_text(
        json.dumps(
            {
                "status_code": response.status_code,
                "url": response.url,
                "content_type": response.headers.get("content-type", ""),
                "headers": dict(response.headers),
                "saved_at": datetime.utcnow().isoformat(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def request_liveuamap(api_key: str, base_dir: Path) -> dict:
    params = {
        "a": "mpts",
        "resid": REGION_ID,
        "time": int(time.time()),
        "count": COUNT,
        "key": api_key,
    }

    headers = {
        "Accept": "application/json,text/plain,*/*",
        "User-Agent": "Mozilla/5.0 (compatible; ConflictMonitor/1.0)",
    }

    response = requests.get(
        API_URL,
        params=params,
        headers=headers,
        timeout=TIMEOUT,
        allow_redirects=True,
    )

    save_debug_files(base_dir, response)

    print("Status:", response.status_code)
    print("URL:", response.url)
    print("Content-Type:", response.headers.get("content-type", ""))

    if response.status_code != 200:
        raise RuntimeError(
            f"LiveUAmap API HTTP hiba: {response.status_code}. "
            f"Nézd meg: data/events/liveuamap_last_response.txt"
        )

    content_type = response.headers.get("content-type", "").lower()
    text_start = response.text[:200].lstrip().lower()

    if "json" not in content_type and text_start.startswith("<!doctype html") or text_start.startswith("<html"):
        raise RuntimeError(
            "A LiveUAmap nem JSON-t adott vissza, hanem HTML oldalt. "
            "Valószínűleg a kulcs/jogosultság vagy az endpoint-hozzáférés a gond. "
            "Nézd meg: data/events/liveuamap_last_response.txt"
        )

    try:
        return response.json()
    except Exception as exc:
        raise RuntimeError(
            "A válasz nem feldolgozható JSON. "
            "Nézd meg: data/events/liveuamap_last_response.txt"
        ) from exc


def extract_items(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []

    # A képen magyar mezőnév látszik: "helyszínek"
    for key in ["helyszínek", "points", "data", "items", "result"]:
        value = payload.get(key)
        if isinstance(value, list):
            return value

    return []


def parse_timestamp(item: dict) -> str:
    for key in ["time", "timestamp", "created_at", "updated_at"]:
        value = item.get(key)
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
            except Exception:
                pass

        if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value):
            return value[:10]

    return datetime.utcnow().date().isoformat()


def normalize_event(item: dict) -> dict | None:
    title = clean_text(item.get("name") or item.get("title"))
    if not title:
        return None

    if should_exclude(title):
        return None

    location = clean_text(item.get("place") or item.get("location"))
    link = clean_text(item.get("link") or item.get("url"))
    lat = item.get("lat")
    lng = item.get("lng") or item.get("lon")
    date = parse_timestamp(item)

    return {
        "date": date,
        "title": title,
        "location": location,
        "link": link,
        "lat": lat,
        "lng": lng,
        "categories": classify_event(title),
    }


def aggregate_daily_stats(events: list[dict]) -> list[dict]:
    stats = {}

    for event in events:
        day = event["date"]

        if day not in stats:
            stats[day] = {
                "date": day,
                "event_count": 0,
                "air_strike": 0,
                "frontline": 0,
                "civilian_impact": 0,
                "infrastructure": 0,
                "political_security": 0,
                "other": 0,
            }

        stats[day]["event_count"] += 1

        for category in event["categories"]:
            if category in stats[day]:
                stats[day][category] += 1
            else:
                stats[day]["other"] += 1

    return [stats[d] for d in sorted(stats.keys())]


def main():
    api_key = os.getenv("LIVEUAMAP_API_KEY")
    if not api_key:
        raise RuntimeError("A LIVEUAMAP_API_KEY környezeti változó hiányzik.")

    base_dir = Path(__file__).resolve().parent.parent
    out_dir = base_dir / "data" / "events"
    out_dir.mkdir(parents=True, exist_ok=True)

    latest_file = out_dir / "latest_events.json"
    stats_file = out_dir / "daily_event_stats.json"
    raw_json_file = out_dir / "latest_liveuamap_api_raw.json"

    payload = request_liveuamap(api_key, base_dir)

    raw_json_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    items = extract_items(payload)
    events = []

    for item in items:
        if not isinstance(item, dict):
            continue

        event = normalize_event(item)
        if event:
            events.append(event)

    cutoff = datetime.utcnow().date() - timedelta(days=DAYS_BACK - 1)
    events = [e for e in events if datetime.fromisoformat(e["date"]).date() >= cutoff]

    latest_payload = {
        "created_at": datetime.utcnow().isoformat(),
        "source": "LiveUAmap API",
        "region_id": REGION_ID,
        "days_back": DAYS_BACK,
        "total_events": len(events),
        "raw_item_count": len(items),
        "events": events,
    }

    stats_payload = {
        "created_at": datetime.utcnow().isoformat(),
        "days_back": DAYS_BACK,
        "daily_stats": aggregate_daily_stats(events),
    }

    latest_file.write_text(
        json.dumps(latest_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    stats_file.write_text(
        json.dumps(stats_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Raw items:", len(items))
    print("Filtered events:", len(events))
    print("Saved:", latest_file)
    print("Saved:", stats_file)
    print("Saved raw JSON:", raw_json_file)


if __name__ == "__main__":
    main()
