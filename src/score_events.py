import json
import csv
from pathlib import Path
from datetime import datetime


CATEGORY_WEIGHTS = {
    "air_strike": -3,
    "frontline": -2,
    "civilian_impact": -3,
    "infrastructure": -2,
    "political_security": -1,
    "other": -1,
}


def classify_event_assessment(total_score: int) -> str:
    if total_score <= -120:
        return "very high activity"
    if total_score <= -60:
        return "high activity"
    if total_score <= -25:
        return "elevated activity"
    if total_score <= -10:
        return "moderate activity"
    return "low activity"


def score_single_event(event: dict) -> dict:
    categories = event.get("categories", [])
    score = 0
    matched_categories = []

    for category in categories:
        weight = CATEGORY_WEIGHTS.get(category, CATEGORY_WEIGHTS["other"])
        score += weight
        matched_categories.append(
            {
                "category": category,
                "weight": weight
            }
        )

    return {
        "title": event.get("title", ""),
        "date": event.get("date", ""),
        "location": event.get("location", ""),
        "published_label": event.get("published_label", ""),
        "link": event.get("link", ""),
        "categories": categories,
        "score": score,
        "matched_categories": matched_categories,
    }


def aggregate_by_day(scored_events: list[dict]) -> list[dict]:
    grouped = {}

    for event in scored_events:
        day = event.get("date", "")
        if not day:
            continue

        if day not in grouped:
            grouped[day] = {
                "date": day,
                "event_count": 0,
                "total_score": 0,
                "air_strike": 0,
                "frontline": 0,
                "civilian_impact": 0,
                "infrastructure": 0,
                "political_security": 0,
                "other": 0,
            }

        grouped[day]["event_count"] += 1
        grouped[day]["total_score"] += event.get("score", 0)

        for category in event.get("categories", []):
            if category in grouped[day]:
                grouped[day][category] += 1
            else:
                grouped[day]["other"] += 1

    results = []
    for day in sorted(grouped.keys()):
        row = grouped[day]
        row["assessment"] = classify_event_assessment(row["total_score"])
        results.append(row)

    return results


def save_latest_scores(output_path: Path, scored_events: list[dict], daily_scores: list[dict]):
    payload = {
        "created_at": datetime.utcnow().isoformat(),
        "event_count": len(scored_events),
        "days_covered": len(daily_scores),
        "daily_scores": daily_scores,
        "events": scored_events,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def save_event_history(csv_path: Path, daily_scores: list[dict]):
    existing = {}

    if csv_path.exists():
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_date = row.get("date", "").strip()
                if row_date:
                    existing[row_date] = row

    for row in daily_scores:
        existing[row["date"]] = {
            "date": row["date"],
            "event_count": str(row["event_count"]),
            "total_score": str(row["total_score"]),
            "assessment": row["assessment"],
            "air_strike": str(row["air_strike"]),
            "frontline": str(row["frontline"]),
            "civilian_impact": str(row["civilian_impact"]),
            "infrastructure": str(row["infrastructure"]),
            "political_security": str(row["political_security"]),
            "other": str(row["other"]),
        }

    rows = [existing[d] for d in sorted(existing.keys())]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "date",
            "event_count",
            "total_score",
            "assessment",
            "air_strike",
            "frontline",
            "civilian_impact",
            "infrastructure",
            "political_security",
            "other",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    base_dir = Path(__file__).resolve().parent.parent
    input_file = base_dir / "data" / "events" / "latest_events.json"
    output_json = base_dir / "data" / "events" / "latest_event_scores.json"
    output_csv = base_dir / "data" / "events" / "event_history.csv"

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    raw_events = raw_data.get("events", [])
    scored_events = []

    for event in raw_events:
        scored = score_single_event(event)
        scored_events.append(scored)

    daily_scores = aggregate_by_day(scored_events)

    save_latest_scores(output_json, scored_events, daily_scores)
    save_event_history(output_csv, daily_scores)

    print(f"Scored {len(scored_events)} events")
    print(f"Saved JSON: {output_json}")
    print(f"Saved CSV: {output_csv}")

    if daily_scores:
        latest_day = daily_scores[-1]
        print(
            f"Latest day {latest_day['date']} -> "
            f"{latest_day['event_count']} events, "
            f"score {latest_day['total_score']}, "
            f"{latest_day['assessment']}"
        )


if __name__ == "__main__":
    main()
