import requests
from google import genai
import os
import time
from datetime import datetime
from io import BytesIO
import pypdf

# --- CONFIGURATION ---
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "MIDWEST"]
# Add Security Codes for 100% accuracy
CODES = ["544587", "500325", "532540"] 

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
client = genai.Client(api_key=GEMINI_KEY)

def is_market_time():
    hour = datetime.now().hour
    return 6 <= hour < 24

def get_already_sent():
    if not os.path.exists("sent_alerts.txt"): return set()
    with open("sent_alerts.txt", "r") as f:
        return set(line.strip() for line in f)

def save_sent(alert_id):
    with open("sent_alerts.txt", "a") as f:
        f.write(f"{alert_id}\n")

def analyze_and_send():
    if not is_market_time():
        print("Outside 6 AM - 12 AM window. Skipping.")
        return

    url = "https://www.bseindia.com/corporates/ann.html"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    sent_list = get_already_sent()

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200: return

        raw_html = response.text.upper()
        # Isolate the Table
        table = raw_html.split("TBDATAMAIN")[1].split("</TABLE")[0] if "TBDATAMAIN" in raw_html else raw_html

        for item in WATCHLIST + CODES:
            if item in table:
                # Unique ID for this specific announcement (Company + Snippet Hash)
                idx = table.find(item)
                context_raw = table[max(0, idx-50) : min(len(table), idx+400)]
                alert_id = str(hash(context_raw))

                if alert_id in sent_list: continue

                print(f"New Filing Detected: {item}. Downloading PDF...")
                
                # Extract PDF Link
                try:
                    pdf_path = context_raw.split('HREF="')[1].split('"')[0]
                    pdf_url = f"https://www.bseindia.com{pdf_path.lower()}"
                    
                    # Read PDF Content
                    pdf_res = requests.get(pdf_url, headers=headers)
                    f = BytesIO(pdf_res.content)
                    reader = pypdf.PdfReader(f)
                    pdf_text = "".join([p.extract_text() for p in reader.pages[:3]])

                    prompt = f"""
                    Analyze this BSE filing for {item}. 
                    Headline: {context_raw[:200]}
                    PDF Text: {pdf_text[:4000]}
                    
                    If this is just a routine board meeting date or news advertisement, reply 'IGNORE'.
                    If there is 'Deep News' (CEO change, large order value, default, acquisition), 
                    summarize the REAL impact in 1 clear sentence.
                    """
                    
                    ai_response = client.models.generate_content(model='gemini-3-flash-preview', contents=prompt)
                    summary = ai_response.text.strip()

                    if "IGNORE" not in summary.upper():
                        msg = f"🚨 *DEEP ALERT: {item}*\n\n{summary}\n\n🔗 [View PDF]({pdf_url})"
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                      json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"})
                        save_sent(alert_id)
                        print(f"✅ Alert sent for {item}")
                    
                    time.sleep(10) # Stay safe on free tier

                except Exception as e:
                    print(f"Skip {item}: {e}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_and_send()
