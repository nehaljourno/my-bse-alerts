import requests
from google import genai
import os
import time
from io import BytesIO
import pypdf

# Config
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "MIDWEST", "SADHANA"]
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
    # The "Secret" Mobile API URL - Much more reliable than the website
    url = "https://api.bseindia.com/BseDirect/External/CorporateAnnouncement.aspx"
    
    headers = {
        "User-Agent": "BSEIndia/3.0 (Android)", # Mimics the official app
        "Accept": "application/json",
        "Host": "api.bseindia.com"
    }
    
    sent_list = get_already_sent()

    try:
        # Step 1: Get the clean JSON data
        response = requests.get(url, headers=headers, timeout=20)
        data = response.json() # This is a list of announcements
        
        for ann in data:
            company_name = ann.get("SLONGNAME", "").upper()
            subject = ann.get("NEWSSUB", "")
            pdf_link = ann.get("ATTACHMENTNAME", "") # Direct link!
            
            # Check if company is in our watchlist
            if any(t in company_name for t in WATCHLIST):
                pdf_url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{pdf_link}"
                alert_id = str(hash(pdf_url))

                if alert_id in sent_list: continue

                print(f"🎯 Match Found: {company_name}")

                # Step 2: Read PDF
                try:
                    pdf_res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
                    f = BytesIO(pdf_res.content)
                    reader = pypdf.PdfReader(f)
                    pdf_text = "".join([p.extract_text() or "" for p in reader.pages[:3]])

                    prompt = f"Analyze this filing for {company_name}. Subject: {subject}. PDF Content: {pdf_text[:3000]}. If it involves management changes, orders, or defaults, summarize in 1 clear sentence. Otherwise reply IGNORE."
                    
                    ai_res = client.models.generate_content(model='gemini-3.1-flash', contents=prompt)
                    summary = ai_res.text.strip()

                    if "IGNORE" not in summary.upper():
                        msg = f"🚨 *Deep Alert: {company_name}*\n\n{summary}\n\n🔗 [Open PDF]({pdf_url})"
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                      json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"})
                        save_sent(alert_id)
                        print(f"✅ Alert sent!")
                except Exception as e:
                    print(f"PDF Error: {e}")

    except Exception as e:
        print(f"API Access Error: {e}. BSE might be down or blocking the Data Center IP.")

if __name__ == "__main__":
    analyze_and_send()
