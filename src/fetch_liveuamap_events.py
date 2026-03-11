import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://liveuamap.com"
TIME_URL_TEMPLATE = "https://liveuamap.com/en/time/{date_str}"
USER_AGENT = "Mozilla/5.0 (compatible; ConflictMonitor/1.0; +https://github.com/mikloshetzer-sketch)"
DAYS_BACK = 3
MAX_EVENTS_PER_DAY = 150

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


def fetch_html(url: str) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


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


def extract_time_label(text: str) -> str:
    text = clean_text(text)
    m = re.match(r"^(in \d+ (minute|minutes|hour|hours)|\d+ day ago|\d+ days ago|yesterday)\b", text.lower())
    return m.group(0) if m else ""


def normalize_event(event: dict) -> dict:
    title = clean_text(event.get("title", ""))
    location = clean_text(event.get("location", ""))
    published_label = clean_text(event.get("published_label", ""))
    link = event.get("link", "").strip()

    return {
        "title": title,
        "location": location,
        "published_label": published_label,
        "link": link,
        "categories": classify_event(title),
    }


def parse_day_page(html: str, source_url: str, limit: int = MAX_EVENTS_PER_DAY) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    events = []
    seen = set()

    # 1) Első kör: tipikus cikk-linkek a /en/YYYY/.. mintára
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = clean_text(a.get_text(" ", strip=True))

        if not text:
            continue

        full_url = urljoin(BASE_URL, href)

        if re.search(r"/en/\d{4}/", href) or re.search(r"/en/\d{4}/", full_url):
            title = text

            if should_exclude(title):
                continue

            key = (title, full_url)
            if key in seen:
                continue

            seen.add(key)
            events.append(
                normalize_event(
                    {
                        "title": title,
                        "location": "",
                        "published_label": "",
                        "link": full_url,
                    }
                )
            )

        if len(events) >= limit:
            break

    # 2) Második kör: nyers oldalszöveg feldolgozása, ha kevés a találat
    if len(events) < 20:
        raw_text = soup.get_text("\n", strip=True)
        lines = [clean_text(line) for line in raw_text.splitlines() if clean_text(line)]

        i = 0
        while i < len(lines):
            line = lines[i]

            # időjelöléses sorok után gyakran hely + cím jön
            if re.match(r"^(in \d+ (minute|minutes|hour|hours)|\d+ day ago|\d+ days ago|yesterday)$", line.lower()):
                published_label = line
                location = lines[i + 1] if i + 1 < len(lines) else ""
                title = lines[i + 2] if i + 2 < len(lines) else ""

                if title and not should_exclude(title):
                    key = (title, location, published_label)
                    if key not in seen:
                        seen.add(key)
                        events.append(
                            normalize_event(
                                {
                                    "title": title,
                                    "location": location,
                                    "published_label": published_label,
                                    "link": source_url,
                                }
                            )
                        )
                i += 3
                if len(events) >= limit:
                    break
                continue

            i += 1

    return events[:limit]


def build_day_urls(days_back: int = DAYS_BACK) -> list[tuple[str, str]]:
    urls = []
    today = datetime.now(timezone.utc).date()

    for offset in range(days_back):
        d = today - timedelta(days=offset)
        date_str = d.strftime("%d.%m.%Y")
        urls.append((d.isoformat(), TIME_URL_TEMPLATE.format(date_str=date_str)))

    return urls


def aggregate_daily_stats(events_by_day: dict) -> list[dict]:
    stats = []

    for day, events in sorted(events_by_day.items()):
        counts = {
            "date": day,
            "event_count": len(events),
            "air_strike": 0,
            "frontline": 0,
            "civilian_impact": 0,
            "infrastructure": 0,
            "political_security": 0,
            "other": 0,
        }

        for event in events:
            for category in event.get("categories", []):
                if category in counts:
                    counts[category] += 1
                else:
                    counts["other"] += 1

        stats.append(counts)

    return stats


def main():
    base_dir = Path(__file__).resolve().parent.parent
    raw_dir = base_dir / "data" / "events"
    raw_dir.mkdir(parents=True, exist_ok=True)

    latest_file = raw_dir / "latest_events.json"
    daily_stats_file = raw_dir / "daily_event_stats.json"

    events_by_day = {}
    sources = []

    day_urls = build_day_urls(DAYS_BACK)

    for day_iso, url in day_urls:
        try:
            html = fetch_html(url)
            events = parse_day_page(html, url)
            events_by_day[day_iso] = events
            sources.append({"date": day_iso, "url": url, "event_count": len(events)})
            print(f"{day_iso}: collected {len(events)} events")
        except Exception as exc:
            events_by_day[day_iso] = []
            sources.append({"date": day_iso, "url": url, "event_count": 0, "error": str(exc)})
            print(f"{day_iso}: failed -> {exc}")

    all_events = []
    for day, events in sorted(events_by_day.items()):
        for event in events:
            all_events.append(
                {
                    "date": day,
                    **event,
                }
            )

    latest_payload = {
        "created_at": datetime.utcnow().isoformat(),
        "source": "LiveUAmap public day pages",
        "days_back": DAYS_BACK,
        "total_events": len(all_events),
        "sources": sources,
        "events": all_events,
    }

    daily_stats_payload = {
        "created_at": datetime.utcnow().isoformat(),
        "days_back": DAYS_BACK,
        "daily_stats": aggregate_daily_stats(events_by_day),
    }

    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(latest_payload, f, indent=2, ensure_ascii=False)

    with open(daily_stats_file, "w", encoding="utf-8") as f:
        json.dump(daily_stats_payload, f, indent=2, ensure_ascii=False)

    print(f"Saved: {latest_file}")
    print(f"Saved: {daily_stats_file}")


if __name__ == "__main__":
    main()
