import requests
from google import genai
import os
import re

# --- YOUR WATCHLIST ---
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "MIDWEST"]

# Setup
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")

# Initialize the 2026 AI Client
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
            # We clean the text to make it easier for the AI to read
            page_text = response.text.upper()
            
            for company in WATCHLIST:
                if company in page_text:
                    print(f"Match found for {company}!")
                    
                    # Grab a chunk of text around the company name to give context to the AI
                    start_index = max(0, page_text.find(company) - 200)
                    end_index = min(len(page_text), page_text.find(company) + 300)
                    context = page_text[start_index:end_index]

                    # THE FIX: Updated to 'gemini-2.0-flash'
                    prompt = f"Act as a business editor. Here is a snippet from BSE: '{context}'. If it shows a major new announcement for {company}, write a 1-sentence summary. If it is old or routine, reply ONLY with 'IGNORE'."
                    
                    ai_response = client.models.generate_content(
                        model='gemini-2.0-flash', 
                        contents=prompt
                    )
                    decision = ai_response.text.strip()
                    
                    if "IGNORE" not in decision.upper():
                        message = f"📌 {decision}\n\n🔗 Source: https://www.bseindia.com/corporates/ann.html"
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                      json={"chat_id": TG_CHAT, "text": message})
                        print(f"✅ Telegram Alert sent for {company}!")
                    else:
                        print(f"⏭️ AI decided to ignore routine news for {company}.")
        else:
            print(f"BSE connection failed. Code: {response.status_code}")

    except Exception as e:
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    analyze_and_send()
