import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


API_URL = "https://a.liveuamap.com/api"
REGION_ID = 3   # Ukraine
COUNT = 200
DAYS_BACK = 3
TIMEOUT = 30


KEYWORD_CATEGORIES = {
    "air_strike": [
        "missile", "missiles", "drone", "drones", "strike",
        "air raid", "shelling", "bombing", "explosion",
        "rocket", "ballistic"
    ],
    "frontline": [
        "clash", "battle", "fighting", "offensive",
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
    ]
}


EXCLUDED_KEYWORDS = [
    "iran", "israel", "gaza", "hamas", "hezbollah",
    "tehran", "middle east", "west bank",
    "lebanon", "syria", "yemen", "houthi"
]


def clean_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def should_exclude(title):
    title = title.lower()
    return any(k in title for k in EXCLUDED_KEYWORDS)


def classify_event(title):

    title_lower = title.lower()
    categories = []

    for category, keywords in KEYWORD_CATEGORIES.items():
        if any(k in title_lower for k in keywords):
            categories.append(category)

    if not categories:
        categories.append("other")

    return categories


def request_liveuamap(api_key):

    params = {
        "a": "mpts",
        "resid": REGION_ID,
        "time": int(time.time()),
        "count": COUNT,
        "key": api_key
    }

    response = requests.get(API_URL, params=params, timeout=TIMEOUT)

    print("Status:", response.status_code)
    print("URL:", response.url)

    if response.status_code != 200:
        print(response.text)

    response.raise_for_status()

    return response.json()


def normalize_event(item):

    title = clean_text(item.get("name") or item.get("title"))
    location = clean_text(item.get("place") or item.get("location"))
    link = clean_text(item.get("link"))

    timestamp = item.get("time") or item.get("timestamp")

    if timestamp:
        date = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat()
    else:
        date = datetime.utcnow().date().isoformat()

    return {
        "date": date,
        "title": title,
        "location": location,
        "link": link,
        "categories": classify_event(title),
        "lat": item.get("lat"),
        "lng": item.get("lng")
    }


def aggregate_daily_stats(events):

    stats = {}

    for e in events:

        day = e["date"]

        if day not in stats:

            stats[day] = {
                "date": day,
                "event_count": 0,
                "air_strike": 0,
                "frontline": 0,
                "civilian_impact": 0,
                "infrastructure": 0,
                "political_security": 0,
                "other": 0
            }

        stats[day]["event_count"] += 1

        for cat in e["categories"]:

            if cat in stats[day]:
                stats[day][cat] += 1
            else:
                stats[day]["other"] += 1

    return list(stats.values())


def main():

    api_key = os.getenv("LIVEUAMAP_API_KEY")

    if not api_key:
        raise RuntimeError("LIVEUAMAP_API_KEY missing")

    payload = request_liveuamap(api_key)

    items = payload.get("helyszínek") or payload.get("points") or payload.get("data") or []

    events = []

    for item in items:

        title = clean_text(item.get("name") or item.get("title"))

        if not title:
            continue

        if should_exclude(title):
            continue

        events.append(normalize_event(item))

    cutoff = datetime.utcnow().date() - timedelta(days=DAYS_BACK - 1)

    events = [e for e in events if datetime.fromisoformat(e["date"]).date() >= cutoff]

    base_dir = Path(__file__).resolve().parent.parent

    out_dir = base_dir / "data" / "events"

    out_dir.mkdir(parents=True, exist_ok=True)

    latest_file = out_dir / "latest_events.json"
    stats_file = out_dir / "daily_event_stats.json"

    latest_payload = {
        "created_at": datetime.utcnow().isoformat(),
        "source": "LiveUAmap API",
        "total_events": len(events),
        "events": events
    }

    stats_payload = {
        "created_at": datetime.utcnow().isoformat(),
        "daily_stats": aggregate_daily_stats(events)
    }

    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(latest_payload, f, indent=2, ensure_ascii=False)

    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats_payload, f, indent=2, ensure_ascii=False)

    print("Events:", len(events))
    print("Saved:", latest_file)
    print("Saved:", stats_file)


if __name__ == "__main__":
    main()
