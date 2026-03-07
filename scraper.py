import requests
from google import genai
import os
import time
import re
from io import BytesIO
import pypdf

WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "MIDWEST", "SADHANA", "544587", "506642"]
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
client = genai.Client(api_key=GEMINI_KEY)

def get_already_sent():
    if not os.path.exists("sent_alerts.txt"): return set()
    with open("sent_alerts.txt", "r") as f:
        return set(line.strip() for line in f)

def save_sent(alert_id):
    with open("sent_alerts.txt", "a") as f:
        f.write(f"{alert_id}\n")

def analyze_and_send():
    # THE STEALTH HEADERS - Mimicking a real 2026 Chrome Browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive"
    }
    
    url = "https://www.bseindia.com/corporates/ann.html"
    sent_list = get_already_sent()

    try:
        # Step 1: Get the page
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=30)
        html = response.text
        
        # DEBUG: Check if we are actually getting the table
        if "TBDATAMAIN" not in html:
            print("⚠️ ALERT: BSE Table blocked by security challenge. Approach B (API) might be needed.")
        
        # Step 2: Extract ALL PDF links and their surrounding text
        # We look for the pattern: ...[Some Text]...[PDF Link]
        matches = re.findall(r'([\s\S]{1,500}?)href=["\'](.*?\.pdf)["\']', html, re.IGNORECASE)
        
        print(f"Total PDF links found: {len(matches)}")

        for context, pdf_path in matches:
            pdf_url = f"https://www.bseindia.com{pdf_path}" if pdf_path.startswith('/') else pdf_path
            
            # Match against watchlist
            found_target = next((t for t in WATCHLIST if t.upper() in context.upper()), None)
            
            if found_target:
                alert_id = str(hash(pdf_url))
                if alert_id in sent_list: continue

                print(f"🎯 HIT: Found {found_target} near link {pdf_url}")

                # Step 3: Deep Scan the PDF
                try:
                    pdf_res = session.get(pdf_url, headers=headers, timeout=20)
                    f = BytesIO(pdf_res.content)
                    reader = pypdf.PdfReader(f)
                    pdf_text = "".join([p.extract_text() or "" for p in reader.pages[:3]])

                    prompt = f"Analyze this BSE filing for {found_target}. If it is a management change, order win, or major news, summarize in 1 sentence. Otherwise reply IGNORE. Text: {pdf_text[:3000]}"
                    
                    ai_res = client.models.generate_content(model='gemini-3.1-flash', contents=prompt)
                    summary = ai_res.text.strip()

                    if "IGNORE" not in summary.upper():
                        msg = f"🚨 *Deep Alert: {found_target}*\n\n{summary}\n\n🔗 [PDF]({pdf_url})"
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                      json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"})
                        save_sent(alert_id)
                        print(f"✅ Alert sent!")
                except Exception as e:
                    print(f"PDF Error: {e}")

    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    analyze_and_send()
