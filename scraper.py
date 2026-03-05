import feedparser
import requests
from google import genai
import os

# ==========================================
# 1. YOUR WATCHLIST
# ==========================================
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI", "MIDWEST"]

# ==========================================
# 2. SETUP THE TOOLS
# ==========================================
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")

client = genai.Client(api_key=GEMINI_KEY)

def analyze_and_send():
    # UPDATED 2026 URL: BSE moved the feed to their 'corporates' section
    rss_url = "https://www.bseindia.com/corporates/ann.xml"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/xml, text/xml, */*"
    }

    print(f"Starting scan of updated BSE Feed...")
    
    try:
        response = requests.get(rss_url, headers=headers, timeout=30)
        
        # If the new link also fails, we use the mobile-compatible fallback
        if response.status_code == 404:
            print("Primary feed moved. Trying fallback mobile feed...")
            rss_url = "https://m.bseindia.com/RSS/Corporate_Ann.xml"
            response = requests.get(rss_url, headers=headers, timeout=30)

        if response.status_code == 200:
            feed = feedparser.parse(response.text)
            print(f"Successfully found {len(feed.entries)} total announcements.")
            
            if len(feed.entries) == 0:
                print("Feed is technically readable but contains no current data.")
                return

            for entry in feed.entries:
                headline = entry.title.upper()
                
                if any(company in headline for company in WATCHLIST):
                    prompt = f"""
                    Act as a senior business journalist. Analyze this BSE headline: '{entry.title}'. 
                    Write a one sentence summary of it
                    """
                    
                    ai_analysis = client.models.generate_content(
                        model='gemini-1.5-flash',
                        contents=prompt
                    )
                    decision = ai_analysis.text.strip()
                    
                    if "IGNORE" not in decision.upper():
                        final_message = f"📰 {decision}\n\n🔗 Source: {entry.link}"
                        tg_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                        requests.post(tg_url, json={"chat_id": TG_CHAT, "text": final_message})
                        print(f"✅ Alert sent for: {entry.title}")
        else:
            print(f"BSE Error {response.status_code}. The site might be down for maintenance.")

    except Exception as e:
        print(f"Something went wrong: {e}")

if __name__ == "__main__":
    analyze_and_send()
