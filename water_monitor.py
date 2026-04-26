"""
Water News Monitor
- Searches Google News RSS with multiple water-related queries every hour
- Deduplicates across all queries
- Sends each article to Gemini for vetting and summarisation
- Sends approved stories to a dedicated Telegram group
"""

import os
import json
import time
import requests
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime
from google import genai

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = "-1003759574195"   # water news group

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL   = "gemini-2.5-flash"

SEEN_FILE        = "/root/seen_water.json"
LOOKBACK_MINUTES = 65   # slightly wider than 60-min cron to avoid gaps

# ── Search queries — cast wide across all water angles ────────────────────────
QUERIES = [
    # Policy & politics
    "water policy government",
    "water law regulation",
    "water rights dispute",
    "river water sharing treaty",
    "transboundary water agreement",
    # Crisis & environment
    "water scarcity crisis",
    "drought water shortage",
    "groundwater depletion",
    "water pollution contamination",
    "water quality disease",
    "flood water disaster",
    "glacier melt freshwater",
    # Access & equity
    "drinking water access rural",
    "water sanitation poverty",
    "water inequality community",
    "water privatisation",
    # Innovation & technology
    "water technology innovation",
    "water desalination",
    "water recycling treatment",
    "rainwater harvesting",
    # Positive & solutions
    "water conservation success",
    "water restoration river lake",
    "clean water project",
    # India-specific
    "India water crisis",
    "Ganga Yamuna river pollution",
    "India water policy NITI Aayog",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

client = genai.Client(api_key=GEMINI_API_KEY)

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_seen() -> set:
    if Path(SEEN_FILE).exists():
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    seen_list = list(seen)[-10000:]
    with open(SEEN_FILE, "w") as f:
        json.dump(seen_list, f)


def make_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def fetch_google_news(query: str, lookback_minutes: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    url    = (
        "https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}"
        "&hl=en-IN&gl=IN&ceid=IN:en"
    )
    articles = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        for item in root.findall(".//item"):
            title   = item.findtext("title", "").strip()
            link    = item.findtext("link", "").strip()
            pub_str = item.findtext("pubDate", "").strip()

            if pub_str:
                try:
                    pub_dt = parsedate_to_datetime(pub_str)
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                    if pub_dt < cutoff:
                        continue
                except Exception:
                    pass

            articles.append({
                "id":    make_id(link or title),
                "title": title,
                "link":  link,
            })

    except Exception as e:
        print(f"  [WARN] Google News failed for '{query}': {e}")

    return articles


def vet_with_gemini(title: str, link: str) -> str | None:
    """
    Returns a one-line summary if the article is genuinely about water
    and has news value. Returns None if it should be discarded.
    """
    prompt = (
        f"Article title: {title}\n"
        f"Link: {link}\n\n"
        "You are a journalist at a global publication covering water issues. "
        "Decide if this article is genuinely and substantially about water — "
        "this includes water policy, water access, drought, floods, water pollution, "
        "water technology, river and lake health, water treaties, sanitation, "
        "groundwater, glaciers, water rights, or water-related diseases.\n\n"
        "DISCARD if: water is only mentioned in passing, the article is primarily "
        "about something else (finance, cricket, entertainment), it is a press release "
        "or advertisement, or it has no genuine news value.\n\n"
        "REPORT if: the article is substantially about water and has genuine news value "
        "— a new policy, a crisis, a conflict, a scientific finding, a human story, "
        "a triumph, an innovation, or a significant event.\n\n"
        "If DISCARD, respond with exactly: DISCARD\n"
        "If REPORT, respond with one concise sentence capturing the news value. "
        "Include the location or country if relevant."
    )
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        result = response.text.strip()
        if result.upper() == "DISCARD":
            return None
        return result
    except Exception as e:
        print(f"  [WARN] Gemini failed: {e}")
        return None


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id":                  TELEGRAM_CHAT_ID,
            "text":                     message,
            "parse_mode":               "HTML",
            "disable_web_page_preview": True,
        }, timeout=15)
        resp.raise_for_status()
    except Exception:
        import re
        plain = re.sub(r"<[^>]+>", "", message)
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text":    plain,
        }, timeout=15)
    print(f"  [TELEGRAM] Sent: {message[:80]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().isoformat()}] Starting water news monitor run…")

    seen   = load_seen()
    alerts = 0

    # Collect all articles across all queries, deduplicating by ID
    all_articles = {}
    for query in QUERIES:
        articles = fetch_google_news(query, LOOKBACK_MINUTES)
        for a in articles:
            if a["id"] not in all_articles:
                all_articles[a["id"]] = a
        time.sleep(0.5)   # gentle on Google News

    print(f"  {len(all_articles)} unique articles fetched across {len(QUERIES)} queries")

    for article_id, article in all_articles.items():
        seen_key = f"water-{article_id}"
        if seen_key in seen:
            continue
        seen.add(seen_key)

        print(f"  Vetting: {article['title'][:70]}")
        summary = vet_with_gemini(article["title"], article["link"])

        if summary is None:
            print(f"    Discarded by Gemini")
            continue

        message = (
            f"💧 <b>Water</b>\n"
            f"📋 {summary}\n"
            f"🔗 {article['link']}"
        )

        try:
            send_telegram(message)
            alerts += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"  [ERROR] Telegram failed: {e}")

    save_seen(seen)
    print(f"  Done. {alerts} article(s) sent.")


if __name__ == "__main__":
    main()
