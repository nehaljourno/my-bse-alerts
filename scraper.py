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
client = genai.Client(api_key=GEMINI_KEY)

def analyze_and_send():
    # We are going to the main announcement page instead of a hidden RSS file
    url = "https://www.bseindia.com/corporates/ann.html"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://www.bseindia.com/"
    }

    print("Fetching live announcements from BSE...")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            print("Successfully connected to BSE.")
            page_text = response.text.upper()
            
            # We look for each company in the raw text of the page
            for company in WATCHLIST:
                if company in page_text:
                    print(f"Match found for {company}!")
                    
                    # We find the specific sentence containing the company name
                    # (This is a bit technical, but it grabs the headline)
                    matches = re.findall(rf"([^.?!]*{company}[^.?!]*)", page_text)
                    headline = matches[0] if matches else f"News detected for {company}"

                    prompt = f"Act as a business editor. Analyze: '{headline}'. If it is major news (orders, earnings), write a 1-sentence summary. If routine, reply ONLY with 'IGNORE'."
                    
                    ai_response = client.models.generate_content(
                        model='gemini-1.5-flash',
                        contents=prompt
                    )
                    decision = ai_response.text.strip()
                    
                    if "IGNORE" not in decision.upper():
                        message = f"📌 {decision}\n\n🔗 View here: https://www.bseindia.com/corporates/ann.html"
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                      json={"chat_id": TG_CHAT, "text": message})
                        print(f"✅ Alert sent for {company}")
        else:
            print(f"BSE is still blocking the connection (Error {response.status_code}).")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    analyze_and_send()
