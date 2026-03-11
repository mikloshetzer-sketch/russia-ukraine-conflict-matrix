import csv
import json
from pathlib import Path
from email.utils import parsedate_to_datetime

ESCALATION_KEYWORDS = {
    "missile": -3,
    "missiles": -3,
    "drone": -2,
    "drones": -2,
    "strike": -3,
    "strikes": -3,
    "attack": -3,
    "attacks": -3,
    "shelling": -3,
    "bombing": -3,
    "offensive": -3,
    "advance": -2,
    "assault": -3,
    "raid": -2,
    "air raid": -3,
    "explosion": -2,
    "explosions": -2,
    "killed": -3,
    "dead": -3,
    "wounded": -2,
    "injured": -2,
    "casualties": -3,
    "mobilization": -2,
    "annexation": -3,
    "occupation": -3,
    "incursion": -3,
    "frontline": -1,
    "battle": -2,
    "clashes": -2,
    "clash": -2,
    "escalation": -3,
    "retaliation": -2,
    "saboteur": -2,
    "sabotage": -2,
}

DEESCALATION_KEYWORDS = {
    "ceasefire": 4,
    "truce": 4,
    "talks": 2,
    "negotiation": 3,
    "negotiations": 3,
    "peace": 3,
    "peace plan": 3,
    "diplomacy": 3,
    "diplomatic": 2,
    "mediator": 2,
    "mediation": 2,
    "dialogue": 2,
    "settlement": 3,
    "agreement": 3,
    "deal": 2,
    "pause": 1,
    "humanitarian corridor": 2,
    "prisoner swap": 2,
    "exchange of prisoners": 2,
    "summit": 1,
}

RUSSIA_CONTEXT = {
    "russia": -1,
    "russian": -1,
    "moscow": -1,
    "kremlin": -1,
    "putin": -1,
    "belgorod": -1,
    "kursk": -1,
    "crimea": -2,
    "donetsk": -1,
    "luhansk": -1,
    "zaporizhzhia": -1,
    "kherson": -1,
}

UKRAINE_CONTEXT = {
    "ukraine": -1,
    "ukrainian": -1,
    "kyiv": -1,
    "zelensky": -1,
    "odesa": -1,
    "kharkiv": -1,
    "dnipro": -1,
    "sumy": -1,
    "mykolaiv": -1,
}

SUPPORT_PRESSURE_KEYWORDS = {
    "sanctions": -1,
    "military aid": -1,
    "weapons package": -1,
    "long-range": -1,
    "air defense": -1,
    "f-16": -1,
    "atacms": -1,
    "himars": -1,
    "nato support": -1,
    "eu support": -1,
}

EXCLUDED_KEYWORDS = [
    "iran",
    "israel",
    "gaza",
    "hamas",
    "hezbollah",
    "tehran",
    "middle east",
    "west bank",
    "lebanon",
    "syria",
    "yemen",
    "houthis",
]


def normalize_date(date_str: str) -> str | None:
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.date().isoformat()
    except Exception:
        return None


def score_title(title: str) -> int | None:
    title_lower = title.lower()

    for excluded in EXCLUDED_KEYWORDS:
        if excluded in title_lower:
            return None

    score = 0

    for keyword_map in [
        ESCALATION_KEYWORDS,
        DEESCALATION_KEYWORDS,
        RUSSIA_CONTEXT,
        UKRAINE_CONTEXT,
        SUPPORT_PRESSURE_KEYWORDS,
    ]:
        for keyword, value in keyword_map.items():
            if keyword in title_lower:
                score += value

    if "russia" in title_lower and "ukraine" in title_lower:
        score -= 1

    return score


def classify_total_score(total_score: int) -> str:
    if total_score <= -40:
        return "strong escalation"
    if total_score <= -15:
        return "moderate escalation"
    if total_score < 10:
        return "mixed / unstable"
    if total_score < 25:
        return "moderate de-escalation"
    return "strong de-escalation"


def main():
    base_dir = Path(__file__).resolve().parent.parent
    input_file = base_dir / "data" / "raw" / "latest_news.json"
    history_file = base_dir / "data" / "conflict_history.csv"

    with open(input_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    articles = raw_data.get("articles", [])
    grouped = {}

    for article in articles:
        title = article.get("title", "")
        published = article.get("published", "")

        day = normalize_date(published)
        if not day:
            continue

        score = score_title(title)
        if score is None:
            continue

        if day not in grouped:
            grouped[day] = {
                "total_score": 0,
                "article_count": 0,
                "escalation_articles": 0,
                "deescalation_articles": 0,
                "neutral_articles": 0,
            }

        grouped[day]["total_score"] += score
        grouped[day]["article_count"] += 1

        if score < 0:
            grouped[day]["escalation_articles"] += 1
        elif score > 0:
            grouped[day]["deescalation_articles"] += 1
        else:
            grouped[day]["neutral_articles"] += 1

    existing = {}

    if history_file.exists():
        with open(history_file, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_date = row.get("date", "").strip()
                if row_date:
                    existing[row_date] = {
                        "date": row_date,
                        "total_score": row.get("total_score", "").strip(),
                        "assessment": row.get("assessment", "").strip(),
                        "article_count": row.get("article_count", "").strip(),
                        "escalation_articles": row.get("escalation_articles", "").strip(),
                        "deescalation_articles": row.get("deescalation_articles", "").strip(),
                        "neutral_articles": row.get("neutral_articles", "").strip(),
                    }

    for day, values in grouped.items():
        total_score = values["total_score"]
        existing[day] = {
            "date": day,
            "total_score": str(total_score),
            "assessment": classify_total_score(total_score),
            "article_count": str(values["article_count"]),
            "escalation_articles": str(values["escalation_articles"]),
            "deescalation_articles": str(values["deescalation_articles"]),
            "neutral_articles": str(values["neutral_articles"]),
        }

    rows = [existing[d] for d in sorted(existing.keys())]

    with open(history_file, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "date",
            "total_score",
            "assessment",
            "article_count",
            "escalation_articles",
            "deescalation_articles",
            "neutral_articles",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Backfill complete. Updated {len(grouped)} historical day(s).")


if __name__ == "__main__":
    main()
