"""
SEBI + RBI Monitor
- Fetches RSS feeds from SEBI and RBI every run
- No filtering — all updates sent to Telegram
- No Gemini — links sent directly
- Runs every 10 minutes via cron
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

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID     = os.environ["TELEGRAM_CHAT_ID_REGULATOR"]   # new group

SEEN_FILE = "/root/seen_regulator.json"   # outside git, never wiped

LOOKBACK_MINUTES = 15   # slightly wider than 10-min cron to avoid gaps

FEEDS = [
    {
        "name":   "SEBI",
        "url":    "https://www.sebi.gov.in/sebirss.xml",
        "emoji":  "🏛",
    },
    {
        "name":   "RBI Press Release",
        "url":    "https://www.rbi.org.in/pressreleases_rss.xml",
        "emoji":  "🏦",
    },
    {
        "name":   "RBI Notification",
        "url":    "https://www.rbi.org.in/notifications_rss.xml",
        "emoji":  "🏦",
    },
    {
        "name":   "RBI Speech",
        "url":    "https://www.rbi.org.in/speeches_rss.xml",
        "emoji":  "🎙",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Helpers ───────────────────────────────────────────────────────────────────

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


def fetch_feed(feed: dict, lookback_minutes: int) -> list[dict]:
    """Fetch and parse an RSS feed, return items newer than lookback window."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    items  = []

    try:
        resp = requests.get(feed["url"], headers=HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        for item in root.findall(".//item"):
            title   = item.findtext("title", "").strip()
            link    = item.findtext("link", "").strip()
            pub_str = item.findtext("pubDate", "").strip()

            # Parse publish date if available
            if pub_str:
                try:
                    pub_dt = parsedate_to_datetime(pub_str)
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                    if pub_dt < cutoff:
                        continue
                except Exception:
                    pass   # if date unparseable, include item anyway

            item_id = make_id(link or title)
            items.append({
                "id":    item_id,
                "title": title,
                "link":  link,
            })

    except Exception as e:
        print(f"  [WARN] Failed to fetch {feed['name']}: {e}")

    return items


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
    print(f"[{datetime.now().isoformat()}] Starting SEBI/RBI monitor run…")

    seen   = load_seen()
    alerts = 0

    for feed in FEEDS:
        items = fetch_feed(feed, LOOKBACK_MINUTES)
        print(f"  {feed['name']}: {len(items)} item(s) fetched")

        for item in items:
            item_id = f"{feed['name']}-{item['id']}"
            if item_id in seen:
                continue
            seen.add(item_id)

            message = (
                f"{feed['emoji']} <b>{feed['name']}</b>\n"
                f"📋 {item['title']}\n"
                + (f"🔗 {item['link']}" if item['link'] else "")
            )

            try:
                send_telegram(message)
                alerts += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"  [ERROR] Telegram failed: {e}")

    save_seen(seen)
    print(f"  Done. {alerts} alert(s) sent.")


if __name__ == "__main__":
    main()
