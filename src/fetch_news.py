import feedparser
import json
from pathlib import Path
from datetime import datetime

RSS_SOURCES = [
    "https://news.google.com/rss/search?q=russia+ukraine+war+when:7d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=ukraine+frontline+when:7d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=russia+missile+attack+ukraine+when:7d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=ceasefire+talks+ukraine+russia+when:7d&hl=en-US&gl=US&ceid=US:en"
]


def fetch_rss():
    articles = []

    for url in RSS_SOURCES:
        feed = feedparser.parse(url)

        for entry in feed.entries[:25]:
            articles.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": feed.feed.get("title", "unknown")
            })

    return articles


def main():
    base_dir = Path(__file__).resolve().parent.parent
    output_dir = base_dir / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)

    articles = fetch_rss()

    output = {
        "date": datetime.utcnow().isoformat(),
        "article_count": len(articles),
        "articles": articles
    }

    output_file = output_dir / "latest_news.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(articles)} articles to {output_file}")


if __name__ == "__main__":
    main()
