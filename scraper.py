import requests
from google import genai
from google.api_core import exceptions # Add this for smarter error handling
import os
import time

WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "MIDWEST"]

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
client = genai.Client(api_key=GEMINI_KEY)

def analyze_and_send():
    url = "https://www.bseindia.com/corporates/ann.html"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            page_text = response.text.upper()
            
            for company in WATCHLIST:
                if company in page_text:
                    print(f"Match for {company}!")
                    idx = page_text.find(company)
                    context = page_text[max(0, idx-200) : min(len(page_text), idx+200)]

                    try:
                        # FALLBACK MODEL: 1.5-flash is more stable for free accounts
                        ai_response = client.models.generate_content(
                            model='gemini-1.5-flash', 
                            contents=f"Summarize this news snippet for {company}: '{context}'. If routine, reply IGNORE."
                        )
                        decision = ai_response.text.strip()
                        
                        if "IGNORE" not in decision.upper():
                            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                          json={"chat_id": TG_CHAT, "text": f"📌 {decision}"})
                            print(f"✅ Alert sent for {company}")
                        
                        time.sleep(12) # Stay safe under the 1-minute limit
                    
                    except Exception as e:
                        if "429" in str(e):
                            print(f"Quota still locked. Try linking a billing account in AI Studio to unlock from 'Limit 0'.")
                        else:
                            print(f"AI Error: {e}")
    except Exception as e:
        print(f"BSE Fetch Error: {e}")

if __name__ == "__main__":
    analyze_and_send()
