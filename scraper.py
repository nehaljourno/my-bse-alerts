from seleniumbase import Driver
from google import genai
import os, time, re, requests
from io import BytesIO
import pypdf

# --- CONFIGURATION ---
# Focus on the core list + RailTel (Code: 543265)
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "RAILTEL", "543265", "544587"]

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
    # Use 'uc=True' to bypass BSE's anti-bot detection
    driver = Driver(browser="chrome", uc=True, headless=True)
    sent_list = get_already_sent()
    
    try:
        url = "https://www.bseindia.com/corporates/ann.html"
        driver.get(url)
        time.sleep(15) # Wait for the table to fully populate

        html = driver.page_source
        # Extract PDF links and the surrounding 600 characters of text
        matches = re.findall(r'([\s\S]{1,600}?)href=["\'](.*?\.pdf)["\']', html, re.IGNORECASE)
        print(f"BSE Scan Complete: {len(matches)} announcements found.")

        for context, pdf_path in matches:
            pdf_url = f"https://www.bseindia.com{pdf_path}" if pdf_path.startswith('/') else pdf_path
            
            # Match against our new watchlist
            found_target = next((t for t in WATCHLIST if t.upper() in context.upper()), None)
            
            if found_target:
                alert_id = str(hash(pdf_url))
                if alert_id in sent_list: continue

                print(f"🎯 Target Identified: {found_target}. Analyzing content...")

                try:
                    # Download PDF
                    pdf_res = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
                    f = BytesIO(pdf_res.content)
                    reader = pypdf.PdfReader(f)
                    pdf_text = "".join([p.extract_text() or "" for p in reader.pages[:3]])

                    # Refined Prompt for RailTel and Order Wins
                    prompt = f"""
                    Analyze this stock market filing for {found_target}.
                    Text: {pdf_text[:4000]}
                    
                    TASK: 
                    1. If this is a NEW ORDER, AWARD, or CONTRACT, summarize the total value (Cr) and client.
                    2. If this is a MANAGEMENT CHANGE, summarize who joined/left.
                    3. If it is a routine notice (Board Meeting date only, Holiday, or general compliance), reply ONLY 'IGNORE'.
                    """
                    
                    ai_res = client.models.generate_content(model='gemini-3.1-flash', contents=prompt)
                    summary = ai_res.text.strip()

                    if "IGNORE" not in summary.upper():
                        msg = f"🚀 *New Alert: {found_target}*\n\n{summary}\n\n🔗 [Official PDF]({pdf_url})"
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                      json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"})
                        save_sent(alert_id)
                        print(f"✅ Alert pushed to Telegram for {found_target}")
                except Exception as e:
                    print(f"PDF Analysis Error: {e}")

    finally:
        driver.quit()

if __name__ == "__main__":
    analyze_and_send()
