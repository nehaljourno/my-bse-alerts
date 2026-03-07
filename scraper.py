import requests
from google import genai
import os
import time
from datetime import datetime
from io import BytesIO
import pypdf

# --- CONFIGURATION ---
# Watchlist supports Company Names or Security Codes
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "MIDWEST", "544587"]

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
client = genai.Client(api_key=GEMINI_KEY)

def is_market_time():
    # Indian Standard Time (IST) is UTC + 5:30.
    # 6:00 AM IST = 12:30 AM UTC | 12:00 AM IST = 6:30 PM UTC
    now_utc = datetime.utcnow()
    # Check if UTC hour is between 0 (12:30am IST) and 18 (11:30pm IST)
    return 0 <= now_utc.hour <= 18

def get_already_sent():
    if not os.path.exists("sent_alerts.txt"): return set()
    with open("sent_alerts.txt", "r") as f:
        return set(line.strip() for line in f)

def save_sent(alert_id):
    with open("sent_alerts.txt", "a") as f:
        f.write(f"{alert_id}\n")

def analyze_and_send():
    if not is_market_time():
        print("Outside 6 AM - 12 AM IST window. Skipping.")
        return

    url = "https://www.bseindia.com/corporates/ann.html"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    sent_list = get_already_sent()

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200: return

        # TABLE ISOLATION
        html = response.text.upper()
        table = html.split("TBDATAMAIN")[1].split("</TABLE")[0] if "TBDATAMAIN" in html else html

        for target in WATCHLIST:
            if target in table:
                idx = table.find(target)
                # Capture the row context
                row_snippet = table[max(0, idx-100) : min(len(table), idx+500)]
                alert_id = str(hash(row_snippet))

                if alert_id in sent_list: continue

                try:
                    # EXTRACT PDF LINK
                    pdf_path = row_snippet.split('HREF="')[1].split('"')[0].lower()
                    pdf_url = f"https://www.bseindia.com{pdf_path}"
                    
                    print(f"Deep Scanning PDF for {target}...")
                    pdf_res = requests.get(pdf_url, headers=headers)
                    f = BytesIO(pdf_res.content)
                    reader = pypdf.PdfReader(f)
                    pdf_text = "".join([p.extract_text() for p in reader.pages[:3]])

                    # AI ANALYSIS
                    prompt = f"""
                    Analyze this Indian Stock Market filing for {target}.
                    Headline: {row_snippet[:200]}
                    PDF Content: {pdf_text[:4000]}
                    
                    Rule 1: If it's a routine board meeting date, newspaper ad, or holiday, reply 'IGNORE'.
                    Rule 2: If there's a CEO change, a large order (Cr value), a default, or an acquisition, 
                    summarize the REAL impact in one concise sentence. Avoid jargon.
                    """
                    
                    ai_res = client.models.generate_content(model='gemini-3.1-flash', contents=prompt)
                    summary = ai_res.text.strip()

                    if "IGNORE" not in summary.upper():
                        msg = f"🚨 *Deep Alert: {target}*\n\n{summary}\n\n🔗 [Official PDF]({pdf_url})"
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                      json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"})
                        save_sent(alert_id)
                        print(f"✅ Alert sent for {target}")
                    
                    time.sleep(5) # Rate limiting

                except Exception as e:
                    print(f"PDF Error for {target}: {e}")

    except Exception as e:
        print(f"Scraper error: {e}")

if __name__ == "__main__":
    analyze_and_send()
