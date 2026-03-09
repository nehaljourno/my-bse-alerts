"""
BSE Corporate Announcement Scraper
- Fetches new announcements from BSE every run
- Matches against your watchlist in companies.csv
- Uses Claude AI to summarize the attached PDF/XML
- Sends a one-line alert via Telegram
"""

import os
import json
import time
import requests
import csv
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import anthropic
import tempfile

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]

COMPANIES_FILE = "companies.csv"
SEEN_FILE      = "seen_announcements.json"

BSE_API_URL = (
    "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
)
BSE_DOC_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bseindia.com/",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_companies() -> dict[str, str]:
    """Return {normalised_name: display_name} from companies.csv."""
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


def fetch_announcements(lookback_minutes: int = 15) -> list[dict]:
    """Fetch recent BSE corporate announcements."""
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
        data = resp.json()
        return data.get("Table", [])
    except Exception as e:
        print(f"[ERROR] Failed to fetch announcements: {e}")
        return []


def announcement_id(ann: dict) -> str:
    key = f"{ann.get('NEWSID','')}-{ann.get('DT_TM','')}"
    return hashlib.md5(key.encode()).hexdigest()


def get_attachment_url(ann: dict) -> str | None:
    """Build the URL to the PDF/XML attachment."""
    fname = ann.get("ATTACHMENTNAME", "").strip()
    if fname:
        return BSE_DOC_BASE + fname
    return None


def download_attachment(url: str) -> tuple[bytes, str]:
    """Download attachment; return (content, mime_type)."""
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    ct = resp.headers.get("Content-Type", "application/octet-stream").lower()
    return resp.content, ct


def summarise_with_claude(content: bytes, mime_type: str, company: str, headline: str) -> str:
    """Send document to Claude and get a one-line summary."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Determine source type for Claude
    if "pdf" in mime_type:
        doc_type = "application/pdf"
        source_type = "base64"
    else:
        # Treat XML / HTML / plain text as plain text
        try:
            text_content = content.decode("utf-8", errors="replace")
        except Exception:
            text_content = content.decode("latin-1", errors="replace")

        # Fall back to text prompt
        prompt = (
            f"Company: {company}\n"
            f"BSE Headline: {headline}\n\n"
            f"Announcement content:\n{text_content[:8000]}\n\n"
            "Summarise the key fact in ONE concise sentence (max 25 words). "
            "Focus on the most material information for an investor."
        )
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()

    # PDF path – send as base64 document
    import base64
    pdf_b64 = base64.standard_b64encode(content).decode("utf-8")

    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": doc_type,
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Company: {company}\n"
                            f"BSE Headline: {headline}\n\n"
                            "Summarise the key fact from this announcement in ONE "
                            "concise sentence (max 25 words). Focus on the most "
                            "material information for an investor."
                        ),
                    },
                ],
            }
        ],
    )
    return msg.content[0].text.strip()


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    print(f"[TELEGRAM] Sent: {message}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().isoformat()}] Starting BSE scraper run…")

    companies  = load_companies()
    seen       = load_seen()
    announcements = fetch_announcements(lookback_minutes=15)
    print(f"  Fetched {len(announcements)} announcements from BSE")

    hits = 0
    for ann in announcements:
        ann_id = announcement_id(ann)
        if ann_id in seen:
            continue
        seen.add(ann_id)

        company_name = ann.get("SLONGNAME", ann.get("SSHORTNAME", "")).strip()
        scrip_code   = ann.get("SCRIP_CD", "").strip()
        headline     = ann.get("NEWSSUB", "").strip()
        dt_tm        = ann.get("DT_TM", "").strip()

        # Match against watchlist
        matched_display = None
        if company_name.lower() in companies:
            matched_display = companies[company_name.lower()]
        elif scrip_code in companies:
            matched_display = companies[scrip_code]
        else:
            # Partial match on company name words
            for key, display in companies.items():
                if len(key) > 4 and key in company_name.lower():
                    matched_display = display
                    break

        if not matched_display:
            continue

        hits += 1
        print(f"  HIT: {matched_display} — {headline}")

        # Try to get AI summary from attachment
        summary = headline  # fallback
        attach_url = get_attachment_url(ann)
        if attach_url:
            try:
                print(f"    Downloading attachment: {attach_url}")
                content, mime = download_attachment(attach_url)
                summary = summarise_with_claude(content, mime, matched_display, headline)
                print(f"    AI Summary: {summary}")
            except Exception as e:
                print(f"    [WARN] Could not process attachment: {e}")
                summary = headline

        # Format and send Telegram alert
        time_str = dt_tm[:16] if len(dt_tm) >= 16 else dt_tm
        message = (
            f"🔔 <b>{matched_display}</b> [{scrip_code}]\n"
            f"📋 {summary}\n"
            f"🕐 {time_str}"
        )
        try:
            send_telegram(message)
            time.sleep(0.5)  # gentle rate limiting
        except Exception as e:
            print(f"    [ERROR] Telegram send failed: {e}")

    save_seen(seen)
    print(f"  Done. {hits} watchlist hit(s) found. Seen cache: {len(seen)} entries.")


if __name__ == "__main__":
    main()
