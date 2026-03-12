import json
from pathlib import Path
from datetime import datetime
from collections import Counter


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def format_number(value, decimals=2):
    try:
        num = float(value)
        formatted = f"{num:,.{decimals}f}"
        return formatted.replace(",", " ").replace(".", ",")
    except Exception:
        return str(value)


def format_int(value):
    try:
        num = int(float(value))
        return f"{num:,}".replace(",", " ")
    except Exception:
        return str(value)


def translate_assessment(assessment: str) -> str:
    mapping = {
        "strong escalation": "erős eszkaláció",
        "moderate escalation": "mérsékelt eszkaláció",
        "mixed / unstable": "vegyes / instabil",
        "moderate de-escalation": "mérsékelt enyhülés",
        "strong de-escalation": "erősebb enyhülés",
    }
    return mapping.get(assessment, assessment)


def compute_conflict_index(total_score, article_count):
    try:
        total_score = float(total_score)
        article_count = int(article_count)
        if article_count <= 0:
            return 0.0
        return round(total_score / article_count, 2)
    except Exception:
        return 0.0


def load_history(history_path: Path):
    if not history_path.exists():
        return []

    rows = []
    with open(history_path, "r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        for line in f:
            values = line.strip().split(",")
            if len(values) != len(header):
                continue
            rows.append(dict(zip(header, values)))
    return rows


def compute_trajectory(history_rows):
    if len(history_rows) < 2:
        return "nincs elég adat"

    try:
        last = float(history_rows[-1]["total_score"])
        prev = float(history_rows[-2]["total_score"])
    except Exception:
        return "nincs elég adat"

    diff = last - prev

    if diff <= -10:
        return "romló"
    if diff < 0:
        return "enyhén romló"
    if diff >= 10:
        return "javuló"
    if diff > 0:
        return "enyhén javuló"
    return "stagnáló"


def compute_outlook(total_score):
    try:
        total_score = float(total_score)
    except Exception:
        return "bizonytalan"

    if total_score <= -50:
        return "fokozott eszkalációs kockázat"
    if total_score <= -20:
        return "magas intenzitás fennmaradása valószínű"
    if total_score < 10:
        return "vegyes, instabil környezet"
    return "óvatos enyhülési jelzések"


def pick_top_articles(articles, negative=True, limit=4):
    if negative:
        filtered = [a for a in articles if a.get("score", 0) < 0]
        filtered.sort(key=lambda x: x.get("score", 0))
    else:
        filtered = [a for a in articles if a.get("score", 0) > 0]
        filtered.sort(key=lambda x: x.get("score", 0), reverse=True)

    results = []
    for article in filtered[:limit]:
        results.append({
            "title": safe_text(article.get("title")) or "N/A",
            "link": safe_text(article.get("link")),
            "score": article.get("score", 0),
            "source": safe_text(article.get("source")) or "N/A",
        })
    return results


def pick_key_headlines(articles, limit=6):
    ranked = sorted(
        articles,
        key=lambda a: abs(a.get("score", 0)),
        reverse=True
    )

    seen = set()
    results = []

    for article in ranked:
        title = safe_text(article.get("title"))
        if not title or title in seen:
            continue
        seen.add(title)

        results.append({
            "title": title,
            "link": safe_text(article.get("link")),
            "score": article.get("score", 0),
            "source": safe_text(article.get("source")) or "N/A",
        })

        if len(results) >= limit:
            break

    return results


def build_external_brief_summary(brief_data):
    if not brief_data or not isinstance(brief_data, dict):
        return ""

    summary = brief_data.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    occupied_km2 = summary.get("occupied_km2")
    daily_delta_km2 = summary.get("daily_delta_km2")
    daily_interpretation = safe_text(summary.get("daily_interpretation"))
    weekly_delta_km2 = summary.get("weekly_delta_km2")
    weekly_interpretation = safe_text(summary.get("weekly_interpretation"))
    gained_sector = safe_text(summary.get("gained_sector"))
    lost_sector = safe_text(summary.get("lost_sector"))
    uav_events_7d = summary.get("uav_events_7d")

    parts = []

    if occupied_km2 is not None:
        parts.append(
            f"A külső fronthelyzeti becslés szerint az orosz ellenőrzés alatt álló terület nagysága megközelítőleg {format_number(occupied_km2)} km²."
        )

    if daily_delta_km2 is not None and daily_interpretation:
        parts.append(
            f"Napi összevetésben a változás {format_number(daily_delta_km2)} km² volt, ami {daily_interpretation} irányába mutat."
        )

    if weekly_delta_km2 is not None and weekly_interpretation:
        parts.append(
            f"Heti távlatban a változás {format_number(weekly_delta_km2)} km², ami {weekly_interpretation} képet jelez."
        )

    if gained_sector and lost_sector:
        parts.append(
            f"A napi térképi dinamika alapján a legfontosabb előretörési irány {gained_sector} térségében jelent meg, miközben a legkedvezőtlenebb elmozdulás {lost_sector} környezetében volt megfigyelhető."
        )
    elif gained_sector:
        parts.append(
            f"A napi térképi dinamika alapján a legfontosabb előretörési irány {gained_sector} térségében jelent meg."
        )
    elif lost_sector:
        parts.append(
            f"A napi térképi dinamika alapján a legkedvezőtlenebb elmozdulás {lost_sector} környezetében volt megfigyelhető."
        )

    if uav_events_7d is not None:
        parts.append(
            f"A dróntevékenység továbbra is jelentős, az elmúlt hét napban {format_int(uav_events_7d)} UAV-eseményt rögzítettek."
        )

    return " ".join(parts)


def build_change_summary(change_data):
    if not change_data or not isinstance(change_data, dict):
        return ""

    date = safe_text(change_data.get("date"))
    vs_date = safe_text(change_data.get("vs_date"))
    gained_centroid = change_data.get("gained_centroid")
    lost_centroid = change_data.get("lost_centroid")

    parts = []

    if date and vs_date:
        parts.append(
            f"A változásjelző réteg a {vs_date} és {date} közötti elmozdulásokat mutatja."
        )

    if gained_centroid and isinstance(gained_centroid, list) and len(gained_centroid) == 2:
        parts.append(
            f"Az előretöréshez köthető fő súlypont koordinátája hozzávetőleg {gained_centroid[0]}, {gained_centroid[1]}."
        )

    if lost_centroid and isinstance(lost_centroid, list) and len(lost_centroid) == 2:
        parts.append(
            f"A veszteséghez köthető súlypont koordinátája hozzávetőleg {lost_centroid[0]}, {lost_centroid[1]}."
        )
    else:
        parts.append("Külön veszteségi súlypont nem került azonosításra.")

    return " ".join(parts)


def summarize_ua_sources(ua_sources_data, geo_candidates_data):
    if not ua_sources_data:
        return "", []

    items = []
    if isinstance(ua_sources_data, dict):
        for key in ["items", "entries", "posts", "sources", "data"]:
            value = ua_sources_data.get(key)
            if isinstance(value, list):
                items = value
                break
    elif isinstance(ua_sources_data, list):
        items = ua_sources_data

    if not items:
        return "", []

    drone_count = 0
    missile_count = 0
    shelling_count = 0
    place_counter = Counter()
    source_counter = Counter()

    important_items = []

    def add_places(item):
        candidates = item.get("place_candidates")
        if isinstance(candidates, list):
            for p in candidates:
                p = safe_text(p)
                if p:
                    place_counter[p] += 1

    for item in items:
        if not isinstance(item, dict):
            continue

        title = safe_text(item.get("title"))
        text = safe_text(item.get("text") or item.get("summary") or item.get("content"))
        source = safe_text(item.get("source") or item.get("channel") or item.get("publisher"))

        full = f"{title} {text}".lower()

        if source:
            source_counter[source] += 1

        score = 0
        if "drone" in full or "uav" in full or "shahed" in full:
            drone_count += 1
            score += 2
        if "missile" in full or "rocket" in full or "ballistic" in full:
            missile_count += 1
            score += 2
        if "shelling" in full or "artillery" in full or "bombardment" in full:
            shelling_count += 1
            score += 1

        add_places(item)

        if title:
            important_items.append({
                "title": title,
                "link": safe_text(item.get("link") or item.get("url")),
                "source": source or "operatív forrás",
                "score": score,
            })

    if geo_candidates_data:
        geo_items = []
        if isinstance(geo_candidates_data, dict):
            for key in ["items", "entries", "posts", "data"]:
                value = geo_candidates_data.get(key)
                if isinstance(value, list):
                    geo_items = value
                    break
        elif isinstance(geo_candidates_data, list):
            geo_items = geo_candidates_data

        for item in geo_items:
            if not isinstance(item, dict):
                continue
            candidates = item.get("place_candidates")
            if isinstance(candidates, list):
                for p in candidates:
                    p = safe_text(p)
                    if p:
                        place_counter[p] += 1

    top_places = [name for name, _ in place_counter.most_common(5)]
    top_sources = [name for name, _ in source_counter.most_common(4)]

    summary_parts = []
    summary_parts.append(
        f"Az ukrán operatív források napi mintája alapján a dróntevékenységre utaló említések száma {drone_count}, a rakéta- vagy nagy hatótávolságú csapásokra utaló említéseké {missile_count}, míg a tüzérségi vagy egyéb csapásjellegű aktivitásra utaló jelzéseké {shelling_count} volt."
    )

    if top_places:
        summary_parts.append(
            "A leggyakrabban előforduló helyszínjelöltek: " + ", ".join(top_places) + "."
        )

    if top_sources:
        summary_parts.append(
            "A napi operatív kép főként ezekből a forrásokból rajzolódott ki: " + ", ".join(top_sources) + "."
        )

    important_items.sort(key=lambda x: x.get("score", 0), reverse=True)
    top_items = important_items[:5]

    return " ".join(summary_parts), top_items


def build_commentary(assessment_hu, total_score, trajectory, external_brief, ua_summary):
    parts = []

    parts.append(
        f"A mai összkép alapján a konfliktus médiás értékelése: {assessment_hu}."
    )

    if total_score <= -50:
        parts.append(
            "A hírek súlypontját továbbra is a katonai nyomás, a csapásmérések és a biztonsági kockázatok alakítják."
        )
    elif total_score <= -20:
        parts.append(
            "Az intenzitás továbbra is magas maradt, és a konfliktus nem mutat egyértelmű enyhülési fordulatot."
        )
    elif total_score < 10:
        parts.append(
            "A napi információs környezet vegyes képet mutat, vagyis a katonai és a politikai-diplomáciai jelzések egyszerre maradtak jelen."
        )
    else:
        parts.append(
            "A napi médiaképben több enyhülésre vagy politikai mozgásra utaló elem jelent meg, de ez önmagában még nem jelent stabil fordulatot."
        )

    if trajectory in ["romló", "enyhén romló"]:
        parts.append("A rövid távú pálya inkább romló irányba mutat.")
    elif trajectory in ["javuló", "enyhén javuló"]:
        parts.append("A rövid távú pálya inkább enyhébb vagy javuló irányt jelez.")
    else:
        parts.append("A rövid távú pálya inkább stagnáló vagy bizonytalan.")

    if external_brief:
        parts.append("A külső fronthelyzeti adatok ezt részben operatív oldalról is alátámasztják.")

    if ua_summary:
        parts.append("Az ukrán operatív források alapján a drón- és csapásjellegű aktivitás továbbra is meghatározó maradt.")

    return " ".join(parts)


def main():
    base_dir = Path(__file__).resolve().parent.parent

    scored_path = base_dir / "data" / "processed" / "latest_scored.json"
    history_path = base_dir / "data" / "conflict_history.csv"
    brief_path = base_dir / "data" / "external" / "brief_daily.json"
    change_path = base_dir / "data" / "external" / "change_latest.json"
    ua_sources_path = base_dir / "data" / "external" / "ua_war_sources_latest.json"
    ua_geo_path = base_dir / "data" / "external" / "ua_war_sources_latest.geo_candidates.json"

    docs_dir = base_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    output_path = docs_dir / "latest_summary.json"

    scored = load_json(scored_path)
    if not scored:
        raise RuntimeError("A latest_scored.json nem olvasható vagy hiányzik.")

    history_rows = load_history(history_path)
    brief_data = load_json(brief_path)
    change_data = load_json(change_path)
    ua_sources_data = load_json(ua_sources_path)
    ua_geo_data = load_json(ua_geo_path)

    created_at = safe_text(scored.get("created_at"))
    report_date = created_at[:10] if created_at else datetime.utcnow().date().isoformat()
    article_count = scored.get("article_count", 0)
    total_score = scored.get("total_score", 0)
    assessment_raw = safe_text(scored.get("assessment")) or "unknown"
    assessment = translate_assessment(assessment_raw)
    articles = scored.get("articles", [])

    conflict_index = compute_conflict_index(total_score, article_count)
    trajectory = compute_trajectory(history_rows)
    outlook = compute_outlook(total_score)

    top_escalation = pick_top_articles(articles, negative=True, limit=4)
    top_diplomatic = pick_top_articles(articles, negative=False, limit=4)
    key_headlines = pick_key_headlines(articles, limit=6)

    external_brief = build_external_brief_summary(brief_data)
    change_summary = build_change_summary(change_data)
    ua_summary, ua_top_items = summarize_ua_sources(ua_sources_data, ua_geo_data)

    commentary = build_commentary(
        assessment_hu=assessment,
        total_score=total_score,
        trajectory=trajectory,
        external_brief=external_brief,
        ua_summary=ua_summary,
    )

    payload = {
        "report_date": report_date,
        "created_at": created_at,
        "article_count": article_count,
        "total_score": total_score,
        "conflict_index": conflict_index,
        "assessment": assessment,
        "assessment_raw": assessment_raw,
        "trajectory": trajectory,
        "outlook": outlook,
        "commentary": commentary,

        "top_escalation_signals": top_escalation,
        "top_diplomatic_signals": top_diplomatic,
        "key_headlines": key_headlines,

        "external_operational_summary": external_brief,
        "external_change_summary": change_summary,
        "ua_operational_summary": ua_summary,
        "ua_operational_items": ua_top_items,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Dashboard summary generated: {output_path}")


if __name__ == "__main__":
    main()
