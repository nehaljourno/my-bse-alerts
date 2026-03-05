import feedparser
import requests
import google.generativeai as genai
import os

# --- YOUR WATCHLIST ---
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI"]

# These lines pull your keys from the GitHub "Safe" (Secrets)
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")

# Set up the AI
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

def analyze_and_send():
    feed = feedparser.parse("https://www.bseindia.com/RSS/Corporate_Ann.xml")
    
    for entry in feed.entries:
        headline = entry.title.upper()
        
        # Check if company is in watchlist
        if any(company in headline for company in WATCHLIST):
            
            # Ask the AI for its opinion
            prompt = f"Act as a business editor. Analyze this BSE headline: '{entry.title}'. If it is a major business development (new order, earnings, resignation, etc.), write a 1-sentence summary. If it is routine/procedural, reply ONLY with 'IGNORE'."
            
            response = model.generate_content(prompt)
            decision = response.text.strip()
            
            if "IGNORE" not in decision.upper():
                # Send to Telegram
                message = f"📌 {decision}\n\n🔗 {entry.link}"
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                requests.post(url, json={"chat_id": TG_CHAT, "text": message})
                print(f"Alert sent for: {entry.title}")

if __name__ == "__main__":
    analyze_and_send()
