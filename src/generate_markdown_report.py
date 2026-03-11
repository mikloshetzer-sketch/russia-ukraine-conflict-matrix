import json
from pathlib import Path
from datetime import datetime


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_top_articles(articles, condition, limit=5):
    filtered = [a for a in articles if condition(a)]
    filtered.sort(key=lambda x: x.get("score", 0))
    return filtered[:limit] if limit else filtered


def safe_top_positive_articles(articles, condition, limit=5):
    filtered = [a for a in articles if condition(a)]
    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)
    return filtered[:limit] if limit else filtered


def extract_keyword_summary(articles):
    keyword_counter = {}

    for article in articles:
        for match in article.get("matched_keywords", []):
            keyword = match.get("keyword", "").strip()
            category = match.get("category", "").strip()
            if not keyword:
                continue

            key = (keyword, category)
            keyword_counter[key] = keyword_counter.get(key, 0) + 1

    ranked = sorted(keyword_counter.items(), key=lambda x: x[1], reverse=True)
    return ranked[:10]


def generate_assessment_text(total_score, assessment, article_count, escalation_count, deescalation_count):
    if assessment == "strong escalation":
        return (
            f"A napi médiakép kifejezetten erős eszkalációs képet mutatott. "
            f"A {article_count} feldolgozott hír közül {escalation_count} negatív, konfliktuserősítő jellegű volt, "
            f"míg csak {deescalation_count} utalt tárgyalási vagy enyhülési irányra. "
            f"Ez intenzív katonai aktivitásra, csapásokra és instabil fronthelyzetre utal."
        )
    elif assessment == "moderate escalation":
        return (
            f"A napi hírkép inkább eszkalációs irányba mutatott. "
            f"A konfliktushoz kapcsolódó hírek között a katonai események és támadások domináltak, "
            f"de megjelent néhány enyhülésre utaló fejlemény is."
        )
    elif assessment == "mixed / unstable":
        return (
            f"A napi kép vegyes és ingadozó volt. "
            f"Az orosz–ukrán háborúról szóló hírekben egyszerre volt jelen a katonai nyomás, "
            f"valamint néhány diplomáciai vagy politikai enyhülési jelzés."
        )
    elif assessment == "moderate de-escalation":
        return (
            f"A napi médiakép mérsékelt enyhülést mutatott. "
            f"A katonai események mellett erősebben jelentek meg tárgyalási, egyeztetési vagy politikai rendezésre utaló hírek."
        )
    else:
        return (
            f"A napi hírek alapján erősebb deeszkalációs irány rajzolódott ki. "
            f"A konfliktusról szóló tudósításokban az egyeztetés, rendezés és enyhülés jelei domináltak."
        )


def build_thematic_summary(articles):
    themes = {
        "frontline": ["frontline", "donetsk", "luhansk", "kherson", "zaporizhzhia", "kursk", "battle", "advance", "offensive"],
        "air_attacks": ["missile", "drone", "air raid", "strike", "shelling", "bombing", "explosion"],
        "diplomacy": ["ceasefire", "negotiation", "talks", "peace", "agreement", "diplomacy", "dialogue", "summit"],
        "support": ["sanctions", "military aid", "f-16", "atacms", "himars", "air defense", "eu support", "nato support"],
    }

    counts = {theme: 0 for theme in themes}

    for article in articles:
        title = article.get("title", "").lower()
        for theme, keywords in themes.items():
            if any(keyword in title for keyword in keywords):
                counts[theme] += 1

    lines = []

    if counts["frontline"] > 0:
        lines.append(f"A fronthelyzettel és szárazföldi harcokkal kapcsolatos hírek száma magas volt ({counts['frontline']} cikk).")
    if counts["air_attacks"] > 0:
        lines.append(f"A légi csapásokhoz, rakéta- és dróntámadásokhoz kötődő tudósítások hangsúlyosak maradtak ({counts['air_attacks']} cikk).")
    if counts["diplomacy"] > 0:
        lines.append(f"A diplomáciai és tárgyalásos fejlemények kisebb, de látható súllyal jelentek meg ({counts['diplomacy']} cikk).")
    if counts["support"] > 0:
        lines.append(f"A külső támogatással, fegyverszállításokkal és szankciós környezettel foglalkozó hírek is jelen voltak ({counts['support']} cikk).")

    if not lines:
        lines.append("A napi híranyagban nem rajzolódott ki egyetlen markáns tematikus tengely sem, a tudósítások széttartó képet adtak.")

    return lines


def main():
    base_dir = Path(__file__).resolve().parent.parent
    scored_path = base_dir / "data" / "processed" / "latest_scored.json"
    reports_dir = base_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    data = load_json(scored_path)

    created_at = data.get("created_at", "")
    date_str = created_at[:10] if created_at else datetime.utcnow().date().isoformat()
    article_count = data.get("article_count", 0)
    total_score = data.get("total_score", 0)
    assessment = data.get("assessment", "unknown")
    escalation_count = data.get("escalation_articles", 0)
    deescalation_count = data.get("deescalation_articles", 0)
    neutral_count = data.get("neutral_articles", 0)
    articles = data.get("articles", [])

    top_escalatory = safe_top_articles(articles, lambda a: a.get("score", 0) < 0, limit=5)
    top_deescalatory = safe_top_positive_articles(articles, lambda a: a.get("score", 0) > 0, limit=5)
    keyword_summary = extract_keyword_summary(articles)
    thematic_summary = build_thematic_summary(articles)
    narrative = generate_assessment_text(
        total_score,
        assessment,
        article_count,
        escalation_count,
        deescalation_count,
    )

    report_path = reports_dir / f"{date_str}_report.md"

    lines = []
    lines.append(f"# Napi konfliktusjelentés – Oroszország–Ukrajna")
    lines.append("")
    lines.append(f"**Dátum:** {date_str}")
    lines.append(f"**Feldolgozott cikkek száma:** {article_count}")
    lines.append(f"**Összesített konfliktusindex:** {total_score}")
    lines.append(f"**Minősítés:** {assessment}")
    lines.append("")

    lines.append("## Vezetői összefoglaló")
    lines.append("")
    lines.append(narrative)
    lines.append("")

    lines.append("## Napi megoszlás")
    lines.append("")
    lines.append(f"- Eszkalációs cikkek: **{escalation_count}**")
    lines.append(f"- Deeszkalációs cikkek: **{deescalation_count}**")
    lines.append(f"- Semleges cikkek: **{neutral_count}**")
    lines.append("")

    lines.append("## Tematikus értékelés")
    lines.append("")
    for item in thematic_summary:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Leggyakoribb konfliktusjelző kulcsszavak")
    lines.append("")
    if keyword_summary:
        for (keyword, category), count in keyword_summary:
            lines.append(f"- `{keyword}` ({category}) – {count} előfordulás")
    else:
        lines.append("- Nem volt kimutatható kulcsszóhalmozódás.")
    lines.append("")

    lines.append("## Leginkább eszkalációs jellegű hírek")
    lines.append("")
    if top_escalatory:
        for article in top_escalatory:
            title = article.get("title", "N/A")
            score = article.get("score", 0)
            source = article.get("source", "N/A")
            link = article.get("link", "")
            lines.append(f"- **[{title}]({link})** — pontszám: `{score}`, forrás: {source}")
    else:
        lines.append("- Nem volt markánsan eszkalációs cikk.")
    lines.append("")

    lines.append("## Leginkább deeszkalációs jellegű hírek")
    lines.append("")
    if top_deescalatory:
        for article in top_deescalatory:
            title = article.get("title", "N/A")
            score = article.get("score", 0)
            source = article.get("source", "N/A")
            link = article.get("link", "")
            lines.append(f"- **[{title}]({link})** — pontszám: `{score}`, forrás: {source}")
    else:
        lines.append("- Nem volt markánsan deeszkalációs cikk.")
    lines.append("")

    lines.append("## Elemzői megjegyzés")
    lines.append("")
    lines.append(
        "A jelentés automatizált RSS-alapú hírgyűjtésre és kulcsszavas pontozásra épül. "
        "Ez gyors napi trendkövetésre alkalmas, de nem helyettesíti a mélyebb kvalitatív elemzést, "
        "különösen akkor, ha a címek több konfliktust vagy geopolitikai összefüggést is érintenek."
    )
    lines.append("")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Markdown report generated: {report_path}")


if __name__ == "__main__":
    main()
