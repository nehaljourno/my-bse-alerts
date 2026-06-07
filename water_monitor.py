"""
Water News Monitor
- Scans Google News every 4 hours across two keyword sets
- "Watty says"   — broad water news queries
- "Daubner says" — specific GIZ/multilateral water policy queries (EN/DE/FR)
- Gemini vets every article before sending
- All alerts go to one Telegram group
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
TELEGRAM_CHAT_ID   = "-1003759574195"
GEMINI_API_KEY     = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL       = "gemini-2.5-flash"

SEEN_FILE        = "/root/seen_water.json"
LOOKBACK_MINUTES = 245   # slightly wider than 4-hour cron window

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

client = genai.Client(api_key=GEMINI_API_KEY)

# ── Watty queries — broad water news ─────────────────────────────────────────
WATTY_QUERIES = [
    # Policy & politics
    ("water policy government",         "en"),
    ("water law regulation",            "en"),
    ("water rights dispute",            "en"),
    ("river water sharing treaty",      "en"),
    ("transboundary water agreement",   "en"),
    # Crisis & environment
    ("water scarcity crisis",           "en"),
    ("drought water shortage",          "en"),
    ("groundwater depletion",           "en"),
    ("water pollution contamination",   "en"),
    ("water quality disease",           "en"),
    ("flood water disaster",            "en"),
    ("glacier melt freshwater",         "en"),
    # Access & equity
    ("drinking water access rural",     "en"),
    ("water sanitation poverty",        "en"),
    ("water inequality community",      "en"),
    ("water privatisation",             "en"),
    # Innovation & technology
    ("water technology innovation",     "en"),
    ("water desalination",              "en"),
    ("water recycling treatment",       "en"),
    ("rainwater harvesting",            "en"),
    # Positive & solutions
    ("water conservation success",      "en"),
    ("water restoration river lake",    "en"),
    ("clean water project",             "en"),
    # India-specific
    ("India water crisis",              "en"),
    ("Ganga Yamuna river pollution",    "en"),
    ("India water policy NITI Aayog",   "en"),
]

# ── Daubner queries — GIZ/multilateral water policy (EN/DE/FR) ───────────────
DAUBNER_QUERIES = [
    # English
    ('"Global Water Security for Resilient Development"',                                   "en"),
    ('"Water Security in Africa" OR "WASA program"',                                        "en"),
    ('"Interactive Dialogue 5" AND "Germany" AND "Mexico"',                                 "en"),
    ('"Water in Multilateral Processes" "UN-Water Conference"',                             "en"),
    ('"Team Europe Initiative" AND "Water Security"',                                       "en"),
    ('"GIZ" AND "Global Water Security"',                                                   "en"),
    ('"AMCOW" AND "African Union" AND "Water"',                                             "en"),
    ('"Integrated Water Resources Management" OR IWRM',                                     "en"),
    ('"African Union Commission" water',                                                    "en"),
    # German
    ('"Globale Wassersicherheit"',                                                          "de"),
    ('"Interaktiver Dialog 5" AND "Deutschland" AND "Mexiko"',                              "de"),
    ('"UN-Wasser-Konferenz"',                                                               "de"),
    ('"Wasser in multilateralen Prozessen"',                                                "de"),
    ('"Team Europe Initiative" AND "Wasser"',                                               "de"),
    ('"GIZ" AND "Wassersicherheit"',                                                        "de"),
    ('"Afrikanische Union" AND "Wasser"',                                                   "de"),
    ('"Grenzüberschreitende Wasserbewirtschaftung"',                                        "de"),
    ('"Grenzüberschreitende Governance" OR "Wasser-Governance"',                            "de"),
    ('"Flusseinzugsgebietsorganisation"',                                                   "de"),
    ('"Integriertes Wasserressourcen-Management" OR IWRM',                                  "de"),
    ('"Wasserdiplomatie" OR "Hydropolitik"',                                                "de"),
    ('"Wasserresilienz" OR "Wasserkonflikt"',                                               "de"),
    # French
    ('"Sécurité hydrique mondiale" OR "Sécurité de l\'eau pour un développement résilient"',"fr"),
    ('"Dialogue interactif 5" AND "Allemagne" AND "Mexique"',                               "fr"),
    ('"L\'eau dans les processus multilatéraux"',                                           "fr"),
    ('"Initiative Team Europe" AND "Eau"',                                                  "fr"),
    ('"GIZ" AND "Sécurité de l\'eau"',                                                      "fr"),
    ('"Union Africaine" AND "Eau"',                                                         "fr"),
    ('"COMAE"',                                                                             "fr"),
    ('"Gouvernance transfrontalière de l\'eau" OR "Gestion transfrontalière des eaux"',     "fr"),
    ('"Organisme de bassin" OR "Organisme de bassin fluvial"',                              "fr"),
    ('"Diplomatie de l\'eau" OR "Hydro-politique"',                                         "fr"),
    ('"Gestion intégrée des ressources en eau" OR GIRE',                                    "fr"),
    ('"Résilience hydrique" OR "Conflit lié à l\'eau"',                                     "fr"),
]

# Map language code to Google News locale params
LOCALE = {
    "en": "hl=en-US&gl=US&ceid=US:en",
    "de": "hl=de&gl=DE&ceid=DE:de",
    "fr": "hl=fr&gl=FR&ceid=FR:fr",
}

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


def fetch_google_news(query: str, lang: str) -> list[dict]:
    locale = LOCALE.get(lang, LOCALE["en"])
    url    = (
        f"https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}&{locale}"
    )
    cutoff   = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)
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


def vet_with_gemini(title: str, link: str, brand: str) -> str | None:
    """
    Returns a one-line summary if article is genuinely about water
    and has news value. Returns None if discarded.
    """
    if brand == "DAUBNER":
        context = (
            "This article was found via searches about GIZ water programs, "
            "multilateral water policy, African Union water governance, "
            "water diplomacy, or transboundary water management. "
            "Accept articles substantially covering these specific topics even if "
            "they are technical policy documents or multilateral meeting reports."
        )
    else:
        context = (
            "This article was found via broad water news searches. "
            "Accept articles substantially about water policy, access, drought, "
            "floods, pollution, technology, treaties, or water-related human stories."
        )

    prompt = (
        f"Article title: {title}\n"
        f"Link: {link}\n\n"
        f"Context: {context}\n\n"
        "DISCARD if: water is only mentioned in passing, the article is primarily "
        "about something else, it is a press release or advertisement, or it has "
        "no genuine news value.\n\n"
        "REPORT if: the article is substantially relevant to the context above "
        "and has genuine news value.\n\n"
        "If DISCARD, respond with exactly: DISCARD\n"
        "If REPORT, respond with one concise sentence capturing the news value. "
        "Include the location or country if relevant. "
        "Respond in English regardless of the article's language."
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
    print(f"  [TELEGRAM] {message[:80]}")


def process_query_set(brand: str, query_list: list[tuple], seen: set) -> int:
    """Fetch, vet, and send articles for one brand. Returns alert count."""
    prefix  = "💧 <b>Watty says</b>" if brand == "WATTY" else "🌍 <b>Daubner says</b>"
    emoji   = "💧" if brand == "WATTY" else "🌍"
    alerts  = 0

    articles = collect_articles(query_list)
    print(f"  [{brand}] {len(articles)} unique articles fetched")

    for article_id, article in articles.items():
        seen_key = f"{brand}-{article_id}"
        if seen_key in seen:
            continue
        seen.add(seen_key)

        print(f"  [{brand}] Vetting: {article['title'][:60]}")
        summary = vet_with_gemini(article["title"], article["link"], brand)

        if summary is None:
            print(f"    Discarded")
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().isoformat()}] Starting water monitor run…")

    seen         = load_seen()
    watty_alerts   = process_query_set("WATTY",   WATTY_QUERIES,   seen)
    daubner_alerts = process_query_set("DAUBNER", DAUBNER_QUERIES, seen)

    save_seen(seen)
    print(f"  Done. Watty: {watty_alerts} alert(s). Daubner: {daubner_alerts} alert(s).")


if __name__ == "__main__":
    main()
