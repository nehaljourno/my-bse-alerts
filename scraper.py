"""
BSE Corporate Announcement Scraper
- Fetches new announcements from BSE every run
- Matches against watchlist in companies.csv
- Routes alerts based on 'groups' column:
    bse       → BSE Telegram group only
    regulator → SEBI/RBI Telegram group only
    both      → both groups
- Uses Gemini AI (with Google Search grounding) to summarise the attached PDF
- Sends a "slow day" message if no alerts for 6 hours
"""

import os
import re
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
TELEGRAM_BOT_TOKEN      = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID        = os.environ["TELEGRAM_CHAT_ID"]
TELEGRAM_CHAT_ID_REGULATOR = os.environ.get("TELEGRAM_CHAT_ID_REGULATOR", "")

COMPANIES_FILE  = "companies.csv"
SEEN_FILE       = "/root/seen_announcements.json"
LAST_ALERT_FILE = "last_alert.json"

SLOW_DAY_HOURS = 6

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

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
GEMINI_MODEL = "gemini-2.5-flash"

# Words ignored when comparing company names
NAME_STOPWORDS = {
    "limited", "ltd", "the", "india", "indian", "co",
    "company", "corporation", "corp", "and", "of",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_name(s: str) -> str:
    """Lowercase, strip punctuation and boilerplate words like Ltd/Limited."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    words = [w for w in s.split() if w not in NAME_STOPWORDS]
    return " ".join(words)


def load_companies():
    """
    Returns two dicts:
      by_code: bse_code (str)        → (display_name, groups)
      by_name: normalized full name  → (display_name, groups)
    groups is a set: {'bse'}, {'regulator'}, or {'bse', 'regulator'}
    """
    by_code = {}
    by_name = {}
    with open(COMPANIES_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("company_name", "").strip()
            code = row.get("bse_code", "").strip()
            # Handle codes accidentally saved as floats, e.g. "500325.0"
            if code.endswith(".0"):
                code = code[:-2]
            groups_str = row.get("groups", "bse").strip()
            groups = set(groups_str.split(",")) if groups_str else {"bse"}
            if "both" in groups:
                groups = {"bse", "regulator"}
            if code:
                by_code[code] = (name or code, groups)
            if name:
                norm = normalize_name(name)
                if norm:
                    by_name[norm] = (name, groups)
    return by_code, by_name


def match_company(scrip_code: str, company_name: str, by_code: dict, by_name: dict):
    """
    Match priority:
      1. Exact scrip code (authoritative — BSE always provides SCRIP_CD)
      2. Exact normalized name
      3. Strict prefix match: announcement name STARTS WITH the watchlist name
         (never a substring match anywhere in the name)
    Returns (display_name, groups) or (None, set()).
    """
    if scrip_code in by_code:
        return by_code[scrip_code]

    ann_norm = normalize_name(company_name)
    if not ann_norm:
        return None, set()

    if ann_norm in by_name:
        return by_name[ann_norm]

    for wl_norm, val in by_name.items():
        if len(wl_norm) >= 6 and ann_norm.startswith(wl_norm + " "):
            return val

    return None, set()


def load_seen() -> set:
    if Path(SEEN_FILE).exists():
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f, indent=2)


def load_last_alert_time() -> datetime | None:
    if Path(LAST_ALERT_FILE).exists():
        with open(LAST_ALERT_FILE) as f:
            data = json.load(f)
            ts = data.get("last_alert")
            if ts:
                return datetime.fromisoformat(ts)
    return None


def save_last_alert_time():
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


def extract_grounding_urls(response) -> list:
    """Pull source URLs from Gemini's Google Search grounding metadata."""
    urls = []
    try:
        for cand in (response.candidates or []):
            gm = getattr(cand, "grounding_metadata", None)
            if not gm:
                continue
            for chunk in (getattr(gm, "grounding_chunks", None) or []):
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", None) if web else None
                if uri:
                    urls.append(uri)
    except Exception:
        pass
    return urls


def summarise_with_gemini(content: bytes, mime_type: str, company: str, headline: str):
    """Returns (summary_text, grounding_urls)."""
    prompt = (
        f"Company: {company}\n"
        f"BSE Headline: {headline}\n\n"
        "You are a journalist at Mint (livemint.com), India's biggest business newspaper. "
        "First, decide if this BSE announcement has genuine news value. "
        "DISCARD routine announcements: closure of trading window, investor meets, "
        "transfer and dematerialisation of physical shares, change of address, "
        "ISIN updates, compliance filings, or administrative/regulatory routine. "
        "REPORT announcements with genuine news value: press releases, acquisitions, "
        "mergers, board appointments or resignations, financial results, investor "
        "presentations, new orders, joint ventures, fundraising, or material business developments.\n\n"
        "If DISCARD, respond with exactly: DISCARD\n\n"
        "If REPORT, write a 2-3 line summary as if you were pitching this story to your editor. "
        "Lead with the news value, not what the company wants to say. "
        "Use Google Search to find relevant context from Mint's past reportage on this "
        "company or topic, and weave in one line of that context if it strengthens the pitch.\n\n"
        "SPECIAL CASE: If this announcement is a clarification sought by the exchange from "
        "the company regarding a news report, or the company's reply to such a clarification, "
        "use Google Search to find the original news article being referred to and add its "
        "direct URL at the end on a new line, in exactly this format:\n"
        "📰 Article: <url>\n"
        "Only include a URL you actually found via search — never invent one."
    )

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )

    if "pdf" in mime_type:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=content, mime_type="application/pdf"),
                prompt,
            ],
            config=config,
        )
    else:
        try:
            text_content = content.decode("utf-8", errors="replace")
        except Exception:
            text_content = content.decode("latin-1", errors="replace")
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"{prompt}\n\nAnnouncement content:\n{text_content[:8000]}",
            config=config,
        )

    return response.text.strip(), extract_grounding_urls(response)


def send_telegram(chat_id: str, message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id":    chat_id,
            "text":       message,
            "parse_mode": "HTML",
        }, timeout=15)
        resp.raise_for_status()
    except Exception:
        plain = re.sub(r"<[^>]+>", "", message)
        requests.post(url, json={
            "chat_id": chat_id,
            "text":    plain,
        }, timeout=15)
    print(f"  [TELEGRAM → {chat_id}] {message[:60]}…")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().isoformat()}] Starting BSE scraper run…")

    by_code, by_name = load_companies()
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

        matched_display, matched_groups = match_company(
            scrip_code, company_name, by_code, by_name
        )

        if not matched_display:
            continue

        print(f"  HIT: {matched_display} [{','.join(matched_groups)}] — {headline}")

        is_clarification = "clarification" in f"{headline} {bse_headline}".lower()

        # Summarise with Gemini
        summary     = bse_headline if bse_headline else headline
        source_urls = []
        attach_url  = get_attachment_url(ann)

        if attach_url:
            try:
                print(f"    Downloading: {attach_url}")
                content, mime = download_attachment(attach_url)
                summary, source_urls = summarise_with_gemini(
                    content, mime, matched_display, headline
                )
                print(f"    AI Summary: {summary}")
            except Exception as e:
                print(f"    [WARN] Attachment processing failed: {e}")

        if summary.strip().upper().startswith("DISCARD"):
            print(f"    Skipping — Gemini flagged as routine")
            continue

        # Fallback: clarification announcement but Gemini didn't include a link —
        # use the first source URL from its search grounding metadata
        if is_clarification and "http" not in summary and source_urls:
            summary += f"\n📰 Article: {source_urls[0]}"

        time_str = dt_tm[:16] if len(dt_tm) >= 16 else dt_tm
        message = (
            f"🔔 <b>{matched_display}</b> [{scrip_code}]\n"
            f"📋 {summary}\n"
            f"🕐 {time_str}\n"
            + (f"📎 Here is the BSE link - {attach_url}" if attach_url else "")
        )

        # Route to correct Telegram group(s)
        sent = False
        if "bse" in matched_groups:
            try:
                send_telegram(TELEGRAM_CHAT_ID, message)
                sent = True
            except Exception as e:
                print(f"    [ERROR] BSE Telegram failed: {e}")

        if "regulator" in matched_groups and TELEGRAM_CHAT_ID_REGULATOR:
            try:
                send_telegram(TELEGRAM_CHAT_ID_REGULATOR, message)
                sent = True
            except Exception as e:
                print(f"    [ERROR] Regulator Telegram failed: {e}")

        if sent:
            save_last_alert_time()
            real_alerts += 1
            time.sleep(0.5)

    # ── Slow day check ────────────────────────────────────────────────────────
    if real_alerts == 0:
        last_alert = load_last_alert_time()
        silence_threshold = datetime.now() - timedelta(hours=SLOW_DAY_HOURS)
        if last_alert is None or last_alert < silence_threshold:
            try:
                send_telegram(TELEGRAM_CHAT_ID, "🔕 The scraper is working fine")
                save_last_alert_time()
                print(f"  Sent slow day message")
            except Exception as e:
                print(f"  [ERROR] Slow day message failed: {e}")

    save_seen(seen)
    print(f"  Done. {real_alerts} real alert(s) sent. Seen cache: {len(seen)} entries.")


if __name__ == "__main__":
    main()
