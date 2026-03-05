import feedparser
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
    # This is the most stable RSS link for BSE
    rss_url = "https://www.bseindia.com/RSS/Corporate_Ann.xml"
    
    # Advanced headers to look exactly like a real browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    print("Connecting to BSE...")
    session = requests.Session()
    
    try:
        # We give it 60 seconds to respond now
        response = session.get(rss_url, headers=headers, timeout=60)
        
        if response.status_code == 200:
            feed = feedparser.parse(response.text)
            print(f"Success! Found {len(feed.entries)} announcements.")
            
            for entry in feed.entries:
                headline = entry.title.upper()
                
                # Check for MIDWEST or any other watchlist company
                if any(company in headline for company in WATCHLIST):
                    print(f"Match found: {entry.title}")
                    
                    prompt = f"Act as a business editor. Analyze: '{entry.title}'. Write a 1-sentence summary."
                    
                    ai_response = client.models.generate_content(
                        model='gemini-1.5-flash',
                        contents=prompt
                    )
                    decision = ai_response.text.strip()
                    
                    if "IGNORE" not in decision.upper():
                        message = f"📌 {decision}\n\n🔗 {entry.link}"
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                      json={"chat_id": TG_CHAT, "text": message})
                        print(f"✅ Alert sent for: {entry.title}")
        else:
            print(f"BSE returned error code: {response.status_code}")

    except requests.exceptions.Timeout:
        print("BSE took too long to respond (Timeout). I will try again in 10 minutes.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    analyze_and_send()
