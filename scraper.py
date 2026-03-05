import requests
from google import genai
import os
import time
import re

# --- YOUR WATCHLIST ---
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "MIDWEST"]

# Setup
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
client = genai.Client(api_key=GEMINI_KEY)

def analyze_and_send():
    url = "https://www.bseindia.com/corporates/ann.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    print("Fetching live data from BSE...")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            # FOCUS ON THE TABLE ONLY
            # We cut the page text to just the announcement table area
            raw_html = response.text.upper()
            if "TBDATAMAIN" in raw_html: # This is the specific table ID BSE uses
                table_content = raw_html.split("TBDATAMAIN")[1].split("</TABLE")[0]
            else:
                table_content = raw_html
                
            print("Table isolated. Scanning for your watchlist...")

            for company in WATCHLIST:
                if company in table_content:
                    print(f"Verified Table Match: {company}!")
                    
                    # Extract the specific row context
                    idx = table_content.find(company)
                    context = table_content[max(0, idx-100) : min(len(table_content), idx+400)]

                    try:
                        # USING GEMINI 3 FLASH (The March 2026 Standard)
                        ai_response = client.models.generate_content(
                            model='gemini-3-flash-preview', 
                            contents=f"Extract the specific news title for {company} from this BSE table snippet and summarize it in 1 short sentence. Snippet: '{context}'. If it's old or routine, reply ONLY with 'IGNORE'."
                        )
                        decision = ai_response.text.strip()
                        
                        if "IGNORE" not in decision.upper():
                            message = f"📢 {company}: {decision}\n\n🔗 View: https://www.bseindia.com/corporates/ann.html"
                            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                          json={"chat_id": TG_CHAT, "text": message})
                            print(f"✅ Telegram Alert sent for {company}!")
                        
                        time.sleep(10) # Safety delay

                    except Exception as ai_err:
                        print(f"AI Error: {ai_err}")
        else:
            print(f"BSE Fetch Failed. Code: {response.status_code}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_and_send()
