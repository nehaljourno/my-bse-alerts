"""
News Monitor — Google News RSS
- Runs every 30 minutes
- Searches Google News RSS for each watchlist company
- Alerts via Telegram + Gemini summary when significant news detected
"""

import os
import json
import time
import requests
import csv
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from google import genai

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
GEMINI_API_KEY     = os.environ["GEMINI_API_KEY"]

COMPANIES_FILE = "companies.csv"
SEEN_FILE      = "seen_social.json"
GEMINI_MODEL   = "gemini-2.5-flash"

# Alert thresholds
NEWS_MIN_ARTICLES = 3    # Alert if 3+ new articles in 30 mins
NEWS_KEYWORDS     = [    # Alert immediately if any article contains these
    "acquisition", "merger", "takeover", "buyout",
    "fraud", "raid", "arrest", "scam", "default",
    "results", "profit", "loss", "revenue",
    "order win", "contract", "joint venture",
    "ipo", "fundraise", "qip", "rights issue",
    "ceo", "md", "chairman", "resignation", "appointed",
    "fire", "explosion", "shutdown", "recall",
    "agreement", "tariff", "fine", "tax", "investigation",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Initialise Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_companies() -> list[dict]:
    companies = []
    with open(COMPANIES_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("company_name", "").strip()
            code = row.get("bse_code", "").strip()
            if name:
                companies.append({"name": name, "code": code})
    return companies


def load_seen() -> set:
    if Path(SEEN_FILE).exists():
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    seen_list = list(seen)[-5000:]
    with open(SEEN_FILE, "w") as f:
        json.dump(seen_list, f)


def make_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


# ── Google News RSS ───────────────────────────────────────────────────────────

def fetch_google_news(company_name: str, lookback_minutes: int = 35) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    query  = f"{company_name} stock India"
    url    = (
        f"https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}"
        f"&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        root  = ET.fromstring(resp.content)
        items = root.findall(".//item")

        articles = []
        for item in items:
            title   = item.findtext("title", "")
            link    = item.findtext("link", "")
            pub_str = item.findtext("pubDate", "")

            try:
                from email.utils import parsedate_to_datetime
                pub_dt = parsedate_to_datetime(pub_str)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            if pub_dt < cutoff:
                continue

            articles.append({
                "id":     make_id(link or title),
                "title":  title,
                "link":   link,
                "pub_dt": pub_dt.isoformat(),
            })

        return articles

    except Exception as e:
        print(f"    [WARN] Google News fetch failed for {company_name}: {e}")
        return []


def has_keyword(articles: list[dict]) -> str | None:
    for article in articles:
        title_lower = article["title"].lower()
        for kw in NEWS_KEYWORDS:
            if kw in title_lower:
                return kw
    return None


# ── Gemini ────────────────────────────────────────────────────────────────────

def summarise_news(company: str, articles: list[dict], trigger: str) -> str:
    headlines = "\n".join([f"- {a['title']}" for a in articles[:10]])
    prompt = (
        f"Company: {company}\n"
        f"Trigger: {trigger}\n\n"
        f"Recent news headlines:\n{headlines}\n\n"
        "You are a journalist with the biggest pink-sheet newspaper in India. "
        "Summarise what is happening with this company based on these headlines "
        "in ONE concise sentence. Focus on the news value, not PR speak."
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return response.text.strip()


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       message,
            "parse_mode": "HTML",
        }, timeout=15)
        resp.raise_for_status()
    except Exception:
        import re
        plain = re.sub(r"<[^>]+>", "", message)
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text":    plain,
        }, timeout=15)
    print(f"[TELEGRAM] Sent alert for: {message[:60]}...")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().isoformat()}] Starting news monitor run…")

    companies = load_companies()
    seen      = load_seen()
    alerts    = 0

    for company in companies:
        name = company["name"]

        articles = fetch_google_news(name, lookback_minutes=35)

        # Filter out already-seen articles
        new_articles = []
        for a in articles:
            art_id = f"news-{a['id']}"
            if art_id not in seen:
                seen.add(art_id)
                new_articles.append(a)

        if new_articles:
            keyword = has_keyword(new_articles)
            trigger = None

            if keyword:
                trigger = f"Keyword match: '{keyword}'"
            elif len(new_articles) >= NEWS_MIN_ARTICLES:
                trigger = f"{len(new_articles)} new articles in 30 mins"

            if trigger:
                print(f"  NEWS HIT: {name} — {trigger}")
                try:
                    summary = summarise_news(name, new_articles, trigger)
                    message = (
                        f"📰 <b>{name}</b> — News Alert\n"
                        f"📋 {summary}\n"
                        f"📊 {trigger}\n"
                        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    )
                    send_telegram(message)
                    alerts += 1
                    time.sleep(0.5)
                except Exception as e:
                    print(f"    [ERROR] {e}")

        time.sleep(1)  # Be gentle with Google News rate limits

    save_seen(seen)
    print(f"  Done. {alerts} alert(s) sent.")


if __name__ == "__main__":
    main()
