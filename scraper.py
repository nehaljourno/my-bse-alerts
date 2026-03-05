import feedparser
import requests
from google import genai
import os

# --- YOUR WATCHLIST ---
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "MIDWEST"]

# Set up the AI Client (New Version)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")

def analyze_and_send():
    print("Checking BSE RSS Feed...")
    feed = feedparser.parse("https://www.bseindia.com/RSS/Corporate_Ann.xml")
    
    if not feed.entries:
        print("Feed is empty or unreachable.")
        return

    for entry in feed.entries:
        headline = entry.title.upper()
        
        if any(company in headline for company in WATCHLIST):
            prompt = f"Act as a business editor. Analyze this BSE alert: '{entry.title}'. If it is a major business development (new order, earnings, resignation, etc.), write a 1-sentence summary. If it is routine/procedural, reply ONLY with 'IGNORE'."
            
            # Using the new SDK method
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            decision = response.text.strip()
            
            if "IGNORE" not in decision.upper():
                message = f"📌 {decision}\n\n🔗 {entry.link}"
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                requests.post(url, json={"chat_id": TG_CHAT, "text": message})
                print(f"Alert sent for: {entry.title}")

if __name__ == "__main__":
    analyze_and_send()
