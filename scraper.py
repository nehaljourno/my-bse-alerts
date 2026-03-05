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

# Initialize AI Client
client = genai.Client(api_key=GEMINI_KEY)

def analyze_and_send():
    url = "https://www.bseindia.com/corporates/ann.html"
    
    # Simple header to avoid being blocked
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.bseindia.com/"
    }

    print("Connecting to BSE...")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            print("Successfully connected to BSE.")
            page_text = response.text.upper()
            
            for company in WATCHLIST:
                if company in page_text:
                    print(f"Match found for {company}!")
                    
                    # Find a bit of text around the company name
                    idx = page_text.find(company)
                    context = page_text[max(0, idx-200) : min(len(page_text), idx+200)]

                    try:
                        # Use 1.5-flash as it is more stable for free users
                        ai_response = client.models.generate_content(
                            model='gemini-1.5-flash', 
                            contents=f"Summarize this BSE news for {company} in 1 sentence. Snippet: '{context}'. If it is routine/old, reply ONLY with 'IGNORE'."
                        )
                        decision = ai_response.text.strip()
                        
                        if "IGNORE" not in decision.upper():
                            message = f"📌 {decision}\n\n🔗 Source: https://www.bseindia.com/corporates/ann.html"
                            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                          json={"chat_id": TG_CHAT, "text": message})
                            print(f"✅ Alert sent for {company}!")
                        
                        # Wait 15 seconds so we don't hit the free limit
                        time.sleep(15)

                    except Exception as ai_err:
                        # If the AI quota is still '0', this will tell us
                        print(f"AI skipped {company}. Reason: {ai_err}")
                        time.sleep(5)
        else:
            print(f"BSE connection failed. Code: {response.status_code}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_and_send()
