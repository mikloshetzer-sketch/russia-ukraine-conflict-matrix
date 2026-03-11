import json
from pathlib import Path
from datetime import datetime

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
    "sabotage": -2
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
    "summit": 1
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
    "kherson": -1
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
    "mykolaiv": -1
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
    "eu support": -1
}


def find_matches(title_lower: str, keyword_map: dict, category: str) -> tuple[int, list]:
    score = 0
    matches = []

    for keyword, value in keyword_map.items():
        if keyword in title_lower:
            score += value
            matches.append({
                "keyword": keyword,
                "value": value,
                "category": category
            })

    return score, matches


def score_title(title: str) -> dict:
    title_lower = title.lower()

    total_score = 0
    matched_keywords = []

    for keyword_map, category in [
        (ESCALATION_KEYWORDS, "escalation"),
        (DEESCALATION_KEYWORDS, "deescalation"),
        (RUSSIA_CONTEXT, "russia_context"),
        (UKRAINE_CONTEXT, "ukraine_context"),
        (SUPPORT_PRESSURE_KEYWORDS, "support_pressure"),
    ]:
        partial_score, partial_matches = find_matches(title_lower, keyword_map, category)
        total_score += partial_score
        matched_keywords.extend(partial_matches)

    # Enyhén negatív irányba húzzuk a hírt, ha egyszerre van benne Russia és Ukraine
    # mert ez jellemzően tényleges konfliktus-eseményről szól
    if "russia" in title_lower and "ukraine" in title_lower:
        total_score -= 1
        matched_keywords.append({
            "keyword": "russia+ukraine",
            "value": -1,
            "category": "joint_conflict_context"
        })

    return {
        "title": title,
        "score": total_score,
        "matched_keywords": matched_keywords
    }


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


def classify_article_distribution(scored_articles: list) -> dict:
    escalation_count = 0
    deescalation_count = 0
    neutral_count = 0

    for article in scored_articles:
        score = article.get("score", 0)
        if score < 0:
            escalation_count += 1
        elif score > 0:
            deescalation_count += 1
        else:
            neutral_count += 1

    return {
        "escalation_articles": escalation_count,
        "deescalation_articles": deescalation_count,
        "neutral_articles": neutral_count
    }


def main():
    base_dir = Path(__file__).resolve().parent.parent
    input_file = base_dir / "data" / "raw" / "latest_news.json"
    output_dir = base_dir / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "latest_scored.json"

    with open(input_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    articles = raw_data.get("articles", [])

    scored_articles = []
    total_score = 0

    for article in articles:
        title = article.get("title", "")
        result = score_title(title)
        total_score += result["score"]

        scored_articles.append({
            "title": title,
            "link": article.get("link", ""),
            "published": article.get("published", ""),
            "source": article.get("source", ""),
            "score": result["score"],
            "matched_keywords": result["matched_keywords"]
        })

    distribution = classify_article_distribution(scored_articles)

    output = {
        "created_at": datetime.utcnow().isoformat(),
        "article_count": len(scored_articles),
        "total_score": total_score,
        "assessment": classify_total_score(total_score),
        **distribution,
        "articles": scored_articles
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Scored {len(scored_articles)} articles")
    print(f"Total score: {total_score}")
    print(f"Assessment: {output['assessment']}")
    print(
        f"Escalation: {distribution['escalation_articles']}, "
        f"De-escalation: {distribution['deescalation_articles']}, "
        f"Neutral: {distribution['neutral_articles']}"
    )


if __name__ == "__main__":
    main()
