import feedparser
import requests
from google import genai
import os

# --- YOUR WATCHLIST ---
# Added "MIDW" to catch "Midwest", "Mid-West", or "Midwest Ltd"
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "MIDW"]

# Setup
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
client = genai.Client(api_key=GEMINI_KEY)

def analyze_and_send():
    # This is the direct 'Query' link used by the BSE 2026 interface
    rss_url = "https://www.bseindia.com/include/DefaultRSS.aspx?strType=C"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.bseindia.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    print(f"Connecting to BSE Live Query...")
    
    try:
        # Use a timeout of 30 seconds
        response = requests.get(rss_url, headers=headers, timeout=30)
        
        # If the direct query also 404s, we try the 'Archives' link
        if response.status_code == 404:
            print("Primary query failed. Trying Archives feed...")
            rss_url = "https://www.bseindia.com/RSS/Corporate_Announcements.xml"
            response = requests.get(rss_url, headers=headers, timeout=30)

        if response.status_code == 200:
            feed = feedparser.parse(response.text)
            print(f"Success! Found {len(feed.entries)} announcements.")
            
            if not feed.entries:
                print("Connected, but the feed is currently empty.")
                return

            for entry in feed.entries:
                headline = entry.title.upper()
                
                if any(company in headline for company in WATCHLIST):
                    print(f"Match for {headline}!")
                    
                    prompt = f"Summarize this BSE news for an investor in 1 sentence: '{entry.title}'. If it's routine paperwork, reply ONLY with 'IGNORE'."
                    
                    ai_response = client.models.generate_content(
                        model='gemini-1.5-flash',
                        contents=prompt
                    )
                    decision = ai_response.text.strip()
                    
                    if "IGNORE" not in decision.upper():
                        message = f"🔔 {decision}\n\n🔗 {entry.link}"
                        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                                      json={"chat_id": TG_CHAT, "text": message})
                        print(f"✅ Alert sent!")
        else:
            print(f"BSE still returning {response.status_code}. They may have IP-blocked GitHub.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_and_send()
