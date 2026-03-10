"""
Social Media Monitor — Reddit + StockTwits
- Runs every 30 minutes
- Searches Reddit (IndiaInvestments, Dalal_Street, IndianStockMarket) and StockTwits
- If a watchlist company gets 3+ mentions OR a high-engagement post → Gemini summary → Telegram alert
"""

import os
import json
import time
import requests
import csv
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from google import genai
from google.genai import types

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID    = os.environ["TELEGRAM_CHAT_ID"]
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]
REDDIT_CLIENT_ID    = os.environ["REDDIT_CLIENT_ID"]
REDDIT_CLIENT_SECRET= os.environ["REDDIT_CLIENT_SECRET"]

COMPANIES_FILE = "companies.csv"
SEEN_FILE      = "seen_social.json"

# Alert thresholds
MIN_MENTIONS        = 3      # Alert if 3+ posts mention the company in 30 mins
MIN_UPVOTES         = 50     # Alert if a single post has 50+ upvotes
MIN_COMMENTS        = 10     # Alert if a single post has 10+ comments
STOCKTWITS_MIN_MSGS = 5      # Alert if 5+ StockTwits messages in 30 mins

REDDIT_SUBREDDITS = [
    "IndiaInvestments",
    "Dalal_Street",
    "IndianStockMarket",
    "india_stocks",
    "NSEIndia",
]

GEMINI_MODEL = "gemini-2.5-flash"

# Initialise Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_companies() -> dict:
    """Returns {search_term: display_name} for matching."""
    companies = {}
    with open(COMPANIES_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("company_name", "").strip()
            code = row.get("bse_code", "").strip()
            nse  = row.get("nse_symbol", "").strip()
            if name:
                companies[name.lower()] = name
                # Add shortened name (first word) for better matching
                first_word = name.split()[0].lower()
                if len(first_word) > 4:
                    companies[first_word] = name
            if code:
                companies[code] = name or code
            if nse:
                companies[nse.lower()] = name or nse
    return companies


def load_seen() -> set:
    if Path(SEEN_FILE).exists():
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    # Keep seen cache from growing forever — keep last 2000 entries
    seen_list = list(seen)[-2000:]
    with open(SEEN_FILE, "w") as f:
        json.dump(seen_list, f)


def match_company(text: str, companies: dict) -> str | None:
    """Return display name if any watchlist company is mentioned in text."""
    text_lower = text.lower()
    for term, display in companies.items():
        if term in text_lower:
            return display
    return None


# ── Reddit ────────────────────────────────────────────────────────────────────

def get_reddit_token() -> str:
    resp = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": "BSESocialMonitor/1.0"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_reddit_posts(token: str, lookback_minutes: int = 35) -> list[dict]:
    """Fetch recent posts from all monitored subreddits."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    headers = {
        "Authorization": f"bearer {token}",
        "User-Agent": "BSESocialMonitor/1.0",
    }
    posts = []
    for sub in REDDIT_SUBREDDITS:
        try:
            url  = f"https://oauth.reddit.com/r/{sub}/new.json?limit=50"
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            for post in resp.json()["data"]["children"]:
                d = post["data"]
                created = datetime.fromtimestamp(d["created_utc"], tz=timezone.utc)
                if created < cutoff:
                    continue
                posts.append({
                    "id":        d["id"],
                    "subreddit": sub,
                    "title":     d.get("title", ""),
                    "text":      d.get("selftext", ""),
                    "upvotes":   d.get("ups", 0),
                    "comments":  d.get("num_comments", 0),
                    "url":       f"https://reddit.com{d.get('permalink','')}",
                    "created":   created.isoformat(),
                    "source":    "reddit",
                })
            time.sleep(0.5)  # Reddit rate limit
        except Exception as e:
            print(f"  [WARN] Reddit fetch failed for r/{sub}: {e}")
    return posts


# ── StockTwits ────────────────────────────────────────────────────────────────

def fetch_stocktwits(nse_symbol: str, lookback_minutes: int = 35) -> list[dict]:
    """Fetch recent StockTwits messages for a symbol."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    try:
        url  = f"https://api.stocktwits.com/api/2/streams/symbol/{nse_symbol}.json"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 404:
            return []  # Symbol not on StockTwits
        resp.raise_for_status()
        messages = []
        for msg in resp.json().get("messages", []):
            created = datetime.fromisoformat(
                msg["created_at"].replace("Z", "+00:00")
            )
            if created < cutoff:
                continue
            messages.append({
                "id":      str(msg["id"]),
                "text":    msg.get("body", ""),
                "upvotes": msg.get("likes", {}).get("total", 0),
                "comments":0,
                "url":     f"https://stocktwits.com/symbol/{nse_symbol}",
                "created": created.isoformat(),
                "source":  "stocktwits",
            })
        return messages
    except Exception as e:
        print(f"  [WARN] StockTwits fetch failed for {nse_symbol}: {e}")
        return []


# ── Gemini ────────────────────────────────────────────────────────────────────

def summarise_chatter(company: str, posts: list[dict]) -> str:
    """Ask Gemini to summarise what's being said about the company."""
    posts_text = "\n\n".join([
        f"Source: {p['source'].upper()} | Upvotes: {p['upvotes']} | Comments: {p.get('comments',0)}\n{p['title'] + ' — ' if p.get('title') else ''}{p['text'][:500]}"
        for p in posts[:10]  # Cap at 10 posts
    ])

    prompt = (
        f"Company: {company}\n\n"
        f"The following social media posts mention this company:\n\n{posts_text}\n\n"
        "You are a journalist with the biggest pink-sheet newspaper in India. "
        "Summarise what is being said about this company on social media in ONE concise sentence. "
        "Focus on the sentiment and any specific claims or rumours being discussed. "
        "Do not repeat the individual posts — synthesise the overall chatter into one insight."
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
        resp  = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text":    plain,
        }, timeout=15)
        resp.raise_for_status()
    print(f"[TELEGRAM] Sent: {message[:80]}...")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().isoformat()}] Starting social media monitor run…")

    companies = load_companies()
    seen      = load_seen()

    # ── Reddit ────────────────────────────────────────────────────────────────
    print("  Fetching Reddit posts…")
    try:
        token       = get_reddit_token()
        reddit_posts = fetch_reddit_posts(token)
        print(f"  Fetched {len(reddit_posts)} Reddit posts")
    except Exception as e:
        print(f"  [ERROR] Reddit auth failed: {e}")
        reddit_posts = []

    # Group Reddit posts by matched company
    company_reddit: dict[str, list] = {}
    for post in reddit_posts:
        post_id = f"reddit-{post['id']}"
        if post_id in seen:
            continue
        seen.add(post_id)

        full_text = f"{post['title']} {post['text']}"
        matched   = match_company(full_text, companies)
        if not matched:
            continue

        if matched not in company_reddit:
            company_reddit[matched] = []
        company_reddit[matched].append(post)

    # ── StockTwits ────────────────────────────────────────────────────────────
    print("  Fetching StockTwits messages…")
    company_stocktwits: dict[str, list] = {}

    # Load NSE symbols from CSV
    nse_symbols = {}
    with open(COMPANIES_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            nse = row.get("nse_symbol", "").strip()
            name = row.get("company_name", "").strip()
            if nse and name:
                nse_symbols[nse] = name

    for symbol, display in nse_symbols.items():
        msgs = fetch_stocktwits(symbol, lookback_minutes=35)
        new_msgs = []
        for msg in msgs:
            msg_id = f"st-{msg['id']}"
            if msg_id in seen:
                continue
            seen.add(msg_id)
            new_msgs.append(msg)
        if new_msgs:
            company_stocktwits[display] = new_msgs
        time.sleep(0.3)

    # ── Evaluate and alert ────────────────────────────────────────────────────
    alerted_companies = set()

    # Check Reddit
    for company, posts in company_reddit.items():
        should_alert = False
        reason       = ""

        high_engagement = [
            p for p in posts
            if p["upvotes"] >= MIN_UPVOTES or p["comments"] >= MIN_COMMENTS
        ]

        if len(posts) >= MIN_MENTIONS:
            should_alert = True
            reason = f"{len(posts)} mentions on Reddit"
        elif high_engagement:
            should_alert = True
            best = max(high_engagement, key=lambda x: x["upvotes"] + x["comments"])
            reason = f"High-engagement Reddit post ({best['upvotes']} upvotes, {best['comments']} comments)"

        if should_alert and company not in alerted_companies:
            print(f"  ALERT: {company} — {reason}")
            try:
                summary = summarise_chatter(company, posts)
                message = (
                    f"🐦 <b>{company}</b> — Social Chatter\n"
                    f"📋 {summary}\n"
                    f"📊 {reason}\n"
                    f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                )
                send_telegram(message)
                alerted_companies.add(company)
                time.sleep(0.5)
            except Exception as e:
                print(f"  [ERROR] Failed to send alert for {company}: {e}")

    # Check StockTwits
    for company, msgs in company_stocktwits.items():
        if company in alerted_companies:
            continue

        should_alert = False
        reason       = ""

        high_engagement = [m for m in msgs if m["upvotes"] >= 10]

        if len(msgs) >= STOCKTWITS_MIN_MSGS:
            should_alert = True
            reason = f"{len(msgs)} messages on StockTwits"
        elif high_engagement:
            should_alert = True
            best   = max(high_engagement, key=lambda x: x["upvotes"])
            reason = f"High-liked StockTwits message ({best['upvotes']} likes)"

        if should_alert:
            print(f"  ALERT: {company} — {reason}")
            try:
                summary = summarise_chatter(company, msgs)
                message = (
                    f"🐦 <b>{company}</b> — Social Chatter\n"
                    f"📋 {summary}\n"
                    f"📊 {reason}\n"
                    f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                )
                send_telegram(message)
                alerted_companies.add(company)
                time.sleep(0.5)
            except Exception as e:
                print(f"  [ERROR] Failed to send alert for {company}: {e}")

    save_seen(seen)
    print(f"  Done. {len(alerted_companies)} company alert(s) sent.")


if __name__ == "__main__":
    main()
