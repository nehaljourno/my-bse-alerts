from seleniumbase import Driver
from google import genai
import os
import time
import re
from io import BytesIO
import pypdf
import requests

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
    # Initialize Undetected Driver
    driver = Driver(browser="chrome", uc=True, headless=True)
    sent_list = get_already_sent()
    
    try:
        url = "https://www.bseindia.com/corporates/ann.html"
        driver.get(url)
        time.sleep(10) # Wait for JS to render the table

        # Get the actual rendered HTML
        html = driver.page_source
        
        # Look for PDF links in the rendered page
        matches = re.findall(r'href=["\'](.*?\.pdf)["\']', html, re.IGNORECASE)
        print(f"Total PDFs found: {len(matches)}")

        for pdf_path in matches:
            pdf_url = f"https://www.bseindia.com{pdf_path}" if pdf_path.startswith('/') else pdf_path
            
            # Find the text near this link
            link_pos = html.find(pdf_path)
            context = html[max(0, link_pos-500) : min(len(html), link_pos+500)].upper()

            found_target = next((t for t in WATCHLIST if t.upper() in context), None)
            
            if found_target:
                alert_id = str(hash(pdf_url))
                if alert_id in sent_list: continue

                print(f"🎯 HIT: {found_target} -> {pdf_url}")

                try:
                    # Download PDF using the driver's cookies to stay stealthy
                    pdf_res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
                    f = BytesIO(pdf_res.content)
                    reader = pypdf.PdfReader(f)
                    pdf_text = "".join([p.extract_text() or "" for p in reader.pages[:3]])

                    prompt = f"Analyze this filing for {found_target}. Text: {pdf_text[:3000]}. If it's a management change or major order, summarize in 1 sentence. Else reply IGNORE."
                    
                    ai_res = client.models.generate_content(model='gemini-3.1-flash', contents=prompt)
                    summary = ai_res.text.strip()

                    if "IGNORE" not in summary.upper():
                        msg = f"🚨 *Deep Alert: {found_target}*\n\n{summary}\n\n🔗 [PDF]({pdf_url})"
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                      json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"})
                        save_sent(alert_id)
                except Exception as e:
                    print(f"PDF Error: {e}")

    finally:
        driver.quit()

if __name__ == "__main__":
    analyze_and_send()
