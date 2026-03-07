import requests
from google import genai
import os
import time
from datetime import datetime
from io import BytesIO
import pypdf
import re # Added for flexible link searching

# --- CONFIGURATION ---
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "SADHANA"]

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
client = genai.Client(api_key=GEMINI_KEY)

def is_market_time():
    now_utc = datetime.utcnow()
    # 6 AM - 12 AM IST is approx 0:30 to 18:30 UTC
    return 0 <= now_utc.hour <= 19

def get_already_sent():
    if not os.path.exists("sent_alerts.txt"): return set()
    with open("sent_alerts.txt", "r") as f:
        return set(line.strip() for line in f)

def save_sent(alert_id):
    with open("sent_alerts.txt", "a") as f:
        f.write(f"{alert_id}\n")

def analyze_and_send():
    if not is_market_time():
        print("Outside market hours. Skipping.")
        return

    url = "https://www.bseindia.com/corporates/ann.html"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    sent_list = get_already_sent()

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200: return

        html = response.text
        # Look for the main data table
        table = html.split("TBDATAMAIN")[1].split("</TABLE")[0] if "TBDATAMAIN" in html.upper() else html

        for target in WATCHLIST:
            if target.upper() in table.upper():
                # Find exactly where the company is mentioned
                match_idx = table.upper().find(target.upper())
                # Look at the 1000 characters following the name to find the link
                row_context = table[match_idx : match_idx + 1000]
                
                # REFINED LINK EXTRACTION: Handles ' or " and various formats
                pdf_match = re.search(r'href=["\'](.*?\.pdf)["\']', row_context, re.IGNORECASE)
                
                if not pdf_match:
                    print(f"Match found for {target}, but no PDF link detected in this row. Skipping.")
                    continue

                pdf_path = pdf_match.group(1)
                pdf_url = f"https://www.bseindia.com{pdf_path}" if pdf_path.startswith('/') else pdf_path
                
                # Unique ID for duplicate check
                alert_id = str(hash(pdf_url))
                if alert_id in sent_list: continue

                print(f"New PDF found for {target}: {pdf_url}")

                try:
                    pdf_res = requests.get(pdf_url, headers=headers, timeout=20)
                    f = BytesIO(pdf_res.content)
                    reader = pypdf.PdfReader(f)
                    pdf_text = "".join([p.extract_text() or "" for p in reader.pages[:3]])

                    prompt = f"""
                    Analyze this BSE filing for {target}.
                    Context: {row_context[:300]}
                    PDF Text: {pdf_text[:4000]}
                    
                    If this is a routine meeting notice or old news, reply 'IGNORE'.
                    If there is a major announcement (CEO change, large order value, default), 
                    summarize it in one clear sentence.
                    """
                    
                    ai_res = client.models.generate_content(model='gemini-3.1-flash', contents=prompt)
                    summary = ai_res.text.strip()

                    if "IGNORE" not in summary.upper():
                        msg = f"🚨 *Deep Alert: {target}*\n\n{summary}\n\n🔗 [Official PDF]({pdf_url})"
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                      json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"})
                        save_sent(alert_id)
                        print(f"✅ Alert sent!")
                    
                    time.sleep(5)

                except Exception as e:
                    print(f"Error reading PDF for {target}: {e}")

    except Exception as e:
        print(f"Scraper encountered a problem: {e}")

if __name__ == "__main__":
    analyze_and_send()
