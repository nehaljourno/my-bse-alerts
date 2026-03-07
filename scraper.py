import requests
from google import genai
import os
import time
from datetime import datetime
from io import BytesIO
import pypdf
import re

# --- CONFIGURATION ---
# Added SADHANA as requested
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "MIDWEST", "SADHANA", "544587", "506642"]

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
client = genai.Client(api_key=GEMINI_KEY)

def is_market_time():
    now_utc = datetime.utcnow()
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
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    sent_list = get_already_sent()

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200: return

        html = response.text
        # ISOLATE TABLE AND SPLIT INTO INDIVIDUAL ROWS
        if "TBDATAMAIN" in html.upper():
            table_content = html.upper().split("TBDATAMAIN")[1].split("</TABLE")[0]
            rows = table_content.split("<TR")
        else:
            rows = html.split("<tr")

        for row in rows:
            # Check if any watchlist item is in this SPECIFIC row
            found_target = next((t for t in WATCHLIST if t.upper() in row.upper()), None)
            
            if found_target:
                # Look for PDF link only within this specific row
                pdf_match = re.search(r'HREF=["\'](.*?\.PDF)["\']', row, re.IGNORECASE)
                
                if pdf_match:
                    pdf_path = pdf_match.group(1)
                    pdf_url = f"https://www.bseindia.com{pdf_path}" if pdf_path.startswith('/') else pdf_path
                    
                    alert_id = str(hash(pdf_url))
                    if alert_id in sent_list: continue

                    print(f"🎯 Target Found: {found_target}. Processing PDF: {pdf_url}")

                    try:
                        pdf_res = requests.get(pdf_url, headers=headers, timeout=20)
                        f = BytesIO(pdf_res.content)
                        reader = pypdf.PdfReader(f)
                        pdf_text = "".join([p.extract_text() or "" for p in reader.pages[:3]])

                        prompt = f"""
                        Analyze this BSE filing for {found_target}.
                        PDF Text Snippet: {pdf_text[:4000]}
                        
                        Rule: If this is a routine notice (holiday, board meeting date only), reply 'IGNORE'.
                        Rule: If there is a management change (CEO/Director), order win, or acquisition, 
                        summarize the specific impact in one clear sentence.
                        """
                        
                        ai_res = client.models.generate_content(model='gemini-3.1-flash', contents=prompt)
                        summary = ai_res.text.strip()

                        if "IGNORE" not in summary.upper():
                            msg = f"🚨 *Deep Alert: {found_target}*\n\n{summary}\n\n🔗 [Official PDF]({pdf_url})"
                            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                          json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"})
                            save_sent(alert_id)
                            print(f"✅ Alert sent for {found_target}")
                        
                        time.sleep(2) # Slight delay to be polite to the server
                    except Exception as e:
                        print(f"PDF error for {found_target}: {e}")
                else:
                    # This explains why Reliance "failed" before—it found the name in a non-link row
                    print(f"Found {found_target} in a row, but no PDF link exists there. Moving to next row...")

    except Exception as e:
        print(f"Scraper encountered a problem: {e}")

if __name__ == "__main__":
    analyze_and_send()
