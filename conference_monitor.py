"""
Thatcher — Water Conference Monitor
- Scans Google News once a day for announcements of water-related
  conferences, summits, congresses, forums, and symposia worldwide.
- Prefers international events; requires that the event be open to outside
  (non-member / non-employee) participants — public registration, a
  delegate programme, or an open call for papers/abstracts.
- Gemini vets every hit and extracts a one-line summary with the event
  name, dates, and location where available.
- Alerts go to the same Telegram group as Watty/Daubner.
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

# ── Config ────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = "-1003759574195"  # same group as Watty/Daubner — change if Thatcher needs its own
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = "gemini-2.5-flash"

SEEN_FILE = "/root/seen_conferences.json"
LOOKBACK_MINUTES = 1560  # 26 hours — slightly wider than the 24-hour cron window

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

client = genai.Client(api_key=GEMINI_API_KEY)

# ── Conference queries ───────────────────────────────────────────────────
YEAR = datetime.now().year
NEXT_YEAR = YEAR + 1

BASE_QUERIES_EN = [
    "international water conference",
    "world water congress",
    "water summit registration",
    "water conference call for papers",
    "water policy symposium",
    "transboundary water conference",
    "water security summit",
    "water governance conference",
    "hydropolitics conference",
    "desalination conference",
    "water technology expo",
    "groundwater conference",
    "river basin conference",
    "water utilities conference",
    "climate water conference",
    "water diplomacy conference",
    "UN water conference",
    "IWA world water congress",
    "World Water Week",
    "Stockholm water conference",
]

BASE_QUERIES_DE = [
    "internationale Wasserkonferenz",
    "Wasserkongress",
    "Wasserkonferenz Anmeldung",
]

BASE_QUERIES_FR = [
    "conférence internationale sur l'eau",
    "congrès mondial de l'eau",
    "sommet de l'eau inscription",
]

# Terms most likely to carry a year in the actual event name — tagged
# dynamically with the current and next year so this doesn't need
# hand-editing every January.
YEAR_TAGGED_TERMS = [
    "international water conference",
    "world water congress",
    "water summit",
    "water policy symposium",
]


def build_queries() -> list[tuple]:
    queries = [(q, "en") for q in BASE_QUERIES_EN]
    queries += [(q, "de") for q in BASE_QUERIES_DE]
    queries += [(q, "fr") for q in BASE_QUERIES_FR]
    for term in YEAR_TAGGED_TERMS:
        queries.append((f"{term} {YEAR}", "en"))
        queries.append((f"{term} {NEXT_YEAR}", "en"))
    return queries


CONFERENCE_QUERIES = build_queries()

# Map language code to Google News locale params
LOCALE = {
    "en": "hl=en-US&gl=US&ceid=US:en",
    "de": "hl=de&gl=DE&ceid=DE:de",
    "fr": "hl=fr&gl=FR&ceid=FR:fr",
}

# ── Helpers (same pattern as water_monitor.py) ─────────────────────────────


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


def fetch_google_news(query: str, lang: str) -> list[dict]:
    locale = LOCALE.get(lang, LOCALE["en"])
    url = (
        f"https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}&{locale}"
    )
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)
    articles = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
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
                "id": make_id(link or title),
                "title": title,
                "link": link,
            })
    except Exception as e:
        print(f"  [WARN] Google News failed for '{query[:50]}': {e}")
    return articles


def collect_articles(query_list: list[tuple]) -> dict:
    """Fetch all queries, return deduplicated dict of id → article."""
    all_articles = {}
    for query, lang in query_list:
        for article in fetch_google_news(query, lang):
            if article["id"] not in all_articles:
                all_articles[article["id"]] = article
        time.sleep(0.5)
    return all_articles


def vet_with_gemini(title: str, link: str) -> str | None:
    """
    Returns a one-line summary (event name, dates, location if known) if
    this is a genuine water-related conference open to outside participants.
    Returns None if discarded.
    """
    prompt = (
        f"Article title: {title}\n"
        f"Link: {link}\n\n"
        "This article was found via searches for water-related conferences, "
        "summits, congresses, forums, and symposia.\n\n"
        "REPORT only if the article is about a specific upcoming or ongoing "
        "conference/summit/congress/forum/symposium that is substantially "
        "about water (policy, security, scarcity, technology, governance, "
        "diplomacy, infrastructure, sanitation, etc.) AND is open to outside "
        "participants — i.e. there is public registration, a delegate "
        "programme, or an open call for papers/abstracts, as opposed to a "
        "closed-door internal or members-only meeting. International or "
        "multi-country events are preferred, but a major national event with "
        "significant global relevance can also be reported.\n\n"
        "DISCARD if: it's a recap/wrap-up of a conference that already "
        "happened with no future relevance, it's closed or invite-only, it's "
        "an internal corporate/government meeting, water is only mentioned "
        "in passing, or there's no genuine news/calendar value.\n\n"
        "If DISCARD, respond with exactly: DISCARD\n"
        "If REPORT, respond with one concise sentence naming the conference, "
        "its dates if known, and its location. Respond in English regardless "
        "of the article's language."
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
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=15)
        resp.raise_for_status()
    except Exception:
        import re
        plain = re.sub(r"<[^>]+>", "", message)
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": plain,
        }, timeout=15)
    print(f"  [TELEGRAM] {message[:80]}")


def process_conferences(query_list: list[tuple], seen: set) -> int:
    """Fetch, vet, and send conference alerts. Returns alert count."""
    prefix = "🏛️ <b>Thatcher says</b>"
    alerts = 0
    articles = collect_articles(query_list)
    print(f"  [THATCHER] {len(articles)} unique articles fetched")

    for article_id, article in articles.items():
        seen_key = f"THATCHER-{article_id}"
        if seen_key in seen:
            continue
        seen.add(seen_key)

        print(f"  [THATCHER] Vetting: {article['title'][:60]}")
        summary = vet_with_gemini(article["title"], article["link"])
        if summary is None:
            print("    Discarded")
            continue

        message = (
            f"{prefix}\n"
            f"📋 {summary}\n"
            f"🔗 {article['link']}"
        )
        try:
            send_telegram(message)
            alerts += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"  [ERROR] Telegram failed: {e}")

    return alerts


# ── Main ──────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().isoformat()}] Starting conference monitor run…")
    seen = load_seen()
    alerts = process_conferences(CONFERENCE_QUERIES, seen)
    save_seen(seen)
    print(f"  Done. Thatcher: {alerts} alert(s).")


if __name__ == "__main__":
    main()
