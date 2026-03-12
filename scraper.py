"""
BSE Corporate Announcement Scraper
- Fetches new announcements from BSE every run
- Matches against your watchlist in companies.csv
- Uses Gemini AI to summarise the attached PDF/XML
- Sends a one-line alert via Telegram
- Sends a "slow day" message if no alerts for 6 hours
"""

import os
import json
import time
import requests
import csv
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from google import genai
from google.genai import types

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
GEMINI_API_KEY     = os.environ["GEMINI_API_KEY"]

COMPANIES_FILE  = "companies.csv"
SEEN_FILE       = "seen_announcements.json"
LAST_ALERT_FILE = "last_alert.json"   # tracks when we last sent a real alert

SLOW_DAY_HOURS  = 6    # send "slow day" message after this many hours of silence

BSE_API_URL  = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_DOC_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bseindia.com/",
}

# Initialise Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "gemini-2.5-flash"

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_companies() -> dict:
    companies = {}
    with open(COMPANIES_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("company_name", "").strip()
            code = row.get("bse_code", "").strip()
            if name:
                companies[name.lower()] = name
            if code:
                companies[code] = name or code
    return companies


def load_seen() -> set:
    if Path(SEEN_FILE).exists():
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f, indent=2)


def load_last_alert_time() -> datetime | None:
    """Return the datetime of the last real alert sent, or None."""
    if Path(LAST_ALERT_FILE).exists():
        with open(LAST_ALERT_FILE) as f:
            data = json.load(f)
            ts = data.get("last_alert")
            if ts:
                return datetime.fromisoformat(ts)
    return None


def save_last_alert_time():
    """Save current time as the last alert time."""
    with open(LAST_ALERT_FILE, "w") as f:
        json.dump({"last_alert": datetime.now().isoformat()}, f)


def fetch_announcements(lookback_minutes: int = 10) -> list:
    now   = datetime.now()
    from_ = now - timedelta(minutes=lookback_minutes)
    params = {
        "pageno":      "1",
        "strCat":      "-1",
        "strPrevDate": from_.strftime("%Y%m%d"),
        "strScrip":    "",
        "strSearch":   "P",
        "strToDate":   now.strftime("%Y%m%d"),
        "strType":     "C",
        "subcategory": "-1",
    }
    try:
        resp = requests.get(BSE_API_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json().get("Table", [])
    except Exception as e:
        print(f"[ERROR] Failed to fetch announcements: {e}")
        return []


def announcement_id(ann: dict) -> str:
    key = f"{ann.get('NEWSID','')}-{ann.get('DT_TM','')}"
    return hashlib.md5(key.encode()).hexdigest()


def get_attachment_url(ann: dict):
    fname = str(ann.get("ATTACHMENTNAME") or "").strip()
    return (BSE_DOC_BASE + fname) if fname else None


def download_attachment(url: str):
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    ct = resp.headers.get("Content-Type", "application/octet-stream").lower()
    return resp.content, ct


def summarise_with_gemini(content: bytes, mime_type: str, company: str, headline: str) -> str:
    prompt = (
        f"Company: {company}\n"
        f"BSE Headline: {headline}\n\n"
        "You are a journalist with the biggest pink-sheet newspaper in India. "
        "First, decide if this announcement has genuine news value. "
        "DISCARD routine announcements with no news value such as: closure of trading window, "
        "investor meets, transfer and dematerialisation of physical shares, change of address, "
        "ISIN updates, compliance filings, or any other administrative/regulatory routine. "
        "REPORT announcements that have genuine news value such as: press releases, acquisitions, "
        "mergers, board appointments or resignations, financial results, investor presentations, "
        "new orders, joint ventures, fundraising, or any material business development. "
        "If you decide to DISCARD, respond with exactly the word: DISCARD\n"
        "If you decide to REPORT, respond with one concise sentence summarising the news value. "
        "Do not focus on what the company wants to say, but on the news value."
    )

    if "pdf" in mime_type:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=content, mime_type="application/pdf"),
                prompt,
            ],
        )
    else:
        try:
            text_content = content.decode("utf-8", errors="replace")
        except Exception:
            text_content = content.decode("latin-1", errors="replace")
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"{prompt}\n\nAnnouncement content:\n{text_content[:8000]}",
        )

    return response.text.strip()


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
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text":    plain,
        }, timeout=15)
        resp.raise_for_status()
    print(f"[TELEGRAM] Sent: {message[:80]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().isoformat()}] Starting BSE scraper run…")

    companies     = load_companies()
    seen          = load_seen()
    announcements = fetch_announcements(lookback_minutes=10)
    print(f"  Fetched {len(announcements)} announcements from BSE")

    real_alerts = 0

    for ann in announcements:
        ann_id = announcement_id(ann)
        if ann_id in seen:
            continue
        seen.add(ann_id)

        company_name = str(ann.get("SLONGNAME") or ann.get("SSHORTNAME") or "").strip()
        scrip_code   = str(ann.get("SCRIP_CD") or "").strip()
        headline     = str(ann.get("NEWSSUB") or "").strip()
        bse_headline = str(ann.get("HEADLINE") or "").strip()
        dt_tm        = str(ann.get("DT_TM") or "").strip()

        matched_display = None
        if company_name.lower() in companies:
            matched_display = companies[company_name.lower()]
        elif scrip_code in companies:
            matched_display = companies[scrip_code]
        else:
            for key, display in companies.items():
                if len(key) > 4 and key in company_name.lower():
                    matched_display = display
                    break

        if not matched_display:
            continue

        print(f"  HIT: {matched_display} — {headline}")

        # Use the richer HEADLINE field as fallback if Gemini fails
        summary    = bse_headline if bse_headline else headline
        attach_url = get_attachment_url(ann)

        if attach_url:
            try:
                print(f"    Downloading: {attach_url}")
                content, mime = download_attachment(attach_url)
                summary = summarise_with_gemini(content, mime, matched_display, headline)
                print(f"    AI Summary: {summary}")
            except Exception as e:
                print(f"    [WARN] Attachment processing failed: {e}")

        # Skip routine announcements flagged by Gemini
        if summary.strip().upper() == "DISCARD":
            print(f"    Skipping — Gemini flagged as routine announcement")
            continue

        time_str = dt_tm[:16] if len(dt_tm) >= 16 else dt_tm
        message = (
            f"🔔 <b>{matched_display}</b> [{scrip_code}]\n"
            f"📋 {summary}\n"
            f"🕐 {time_str}\n"
            + (f"📎 Here is the BSE link - {attach_url}" if attach_url else "")
        )
        try:
            send_telegram(message)
            save_last_alert_time()
            real_alerts += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"    [ERROR] Telegram send failed: {e}")

    # ── Slow day check ────────────────────────────────────────────────────────
    if real_alerts == 0:
        last_alert = load_last_alert_time()
        silence_threshold = datetime.now() - timedelta(hours=SLOW_DAY_HOURS)

        if last_alert is None or last_alert < silence_threshold:
            try:
                send_telegram("🔕 Scraper is working, it's just a slow day.")
                save_last_alert_time()
                print(f"  Sent slow day message (no alerts for {SLOW_DAY_HOURS}+ hours)")
            except Exception as e:
                print(f"  [ERROR] Slow day message failed: {e}")

    save_seen(seen)
    print(f"  Done. {real_alerts} real alert(s) sent. Seen cache: {len(seen)} entries.")


if __name__ == "__main__":
    main()
