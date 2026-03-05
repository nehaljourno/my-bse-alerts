import requests
from google import genai
import os
import time  # New: This lets us add delays

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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.bseindia.com/"
    }

    print("Fetching announcements from BSE...")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            print("Successfully connected to BSE.")
            page_text = response.text.upper()
            
            for company in WATCHLIST:
                if company in page_text:
                    print(f"Match found for {company}! Preparing AI analysis...")
                    
                    # Grab context around the match
                    idx = page_text.find(company)
                    context = page_text[max(0, idx-250) : min(len(page_text), idx+250)]

                    try:
                        # THE AI REQUEST
                        ai_response = client.models.generate_content(
                            model='gemini-2.0-flash', 
                            contents=f"Summarize this BSE news for {company} in 1 sentence. Snippet: '{context}'. If routine, reply ONLY with 'IGNORE'."
                        )
                        decision = ai_response.text.strip()
                        
                        if "IGNORE" not in decision.upper():
                            message = f"📌 {decision}\n\n🔗 Source: https://www.bseindia.com/corporates/ann.html"
                            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                          json={"chat_id": TG_CHAT, "text": message})
                            print(f"✅ Telegram Alert sent for {company}!")
                        
                        # --- THE FIX: WAIT 10 SECONDS ---
                        # This prevents the 429 Error by slowing down the loop
                        print("Waiting 10 seconds to respect API limits...")
                        time.sleep(10)

                    except Exception as ai_err:
                        print(f"AI Error for {company}: {ai_err}")
                        # If we still hit a limit, wait even longer
                        time.sleep(30) 
        else:
            print(f"BSE connection failed. Code: {response.status_code}")

    except Exception as e:
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    analyze_and_send()
