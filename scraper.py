import requests
from google import genai
import os
import time

# --- YOUR WATCHLIST ---
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "MIDWEST"]

# Setup
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
client = genai.Client(api_key=GEMINI_KEY)

def analyze_and_send():
    url = "https://www.bseindia.com/corporates/ann.html"
    headers = {"User-Agent": "Mozilla/5.0"}

    print("Fetching live table from BSE...")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            # FIX: We find the 'table' part of the page so we don't see footer/header links
            page_content = response.text
            if '<table' in page_content:
                # We extract only the announcement table area
                table_area = page_content.split('<table')[1].split('</table')[0].upper()
            else:
                table_area = page_content.upper()

            print("Successfully connected. Scanning table...")
            
            for company in WATCHLIST:
                # Searching only inside the table area
                if company in table_area:
                    print(f"Verified Match in Table: {company}")
                    
                    # Grab context around the match
                    idx = table_area.find(company)
                    context = table_area[max(0, idx-150) : min(len(table_area), idx+300)]

                    try:
                        # FIX: Using Gemini 3 Flash (the 2026 standard)
                        ai_response = client.models.generate_content(
                            model='gemini-3-flash', 
                            contents=f"Summarize this BSE announcement for {company}: '{context}'. If it is routine paperwork, reply IGNORE."
                        )
                        decision = ai_response.text.strip()
                        
                        if "IGNORE" not in decision.upper():
                            message = f"🔔 {company} Update: {decision}\n\n🔗 https://www.bseindia.com/corporates/ann.html"
                            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                          json={"chat_id": TG_CHAT, "text": message})
                            print(f"✅ Alert sent!")
                        
                        time.sleep(5) # Minimal delay for Gemini 3

                    except Exception as ai_err:
                        print(f"AI Error: {ai_err}")
        else:
            print(f"BSE connection failed: {response.status_code}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_and_send()
