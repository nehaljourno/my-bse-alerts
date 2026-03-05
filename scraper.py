import feedparser
import requests
from google import genai
import os

# ==========================================
# 1. YOUR WATCHLIST (Edit names inside the quotes)
# ==========================================
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI"]

# ==========================================
# 2. SETUP THE TOOLS (Do not edit this part)
# ==========================================
# This connects to your GitHub Secrets automatically
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")

# Initialize the AI
client = genai.Client(api_key=GEMINI_KEY)

def analyze_and_send():
    rss_url = "https://www.bseindia.com/RSS/Corporate_Ann.xml"
    
    # We use a 'User-Agent' to tell BSE we are a friendly browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print(f"Starting scan of BSE Feed...")
    
    try:
        # Fetch the news from BSE
        response = requests.get(rss_url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            feed = feedparser.parse(response.text)
            print(f"Successfully found {len(feed.entries)} total announcements.")
            
            for entry in feed.entries:
                headline = entry.title.upper()
                
                # If a company from your list is mentioned...
                if any(company in headline for company in WATCHLIST):
                    
                    # --- AI PROMPT (Tell the AI how to behave here) ---
                    prompt = f"""
                    Act as a senior business journalist. Analyze this BSE headline: '{entry.title}'. 
                    
                    If it is an important development (like new orders, earnings, or resignations), 
                    write a punchy 1-sentence summary starting with the company name. 
                    
                    If it is routine paperwork (like a 'Trading Window Closure' or 'Newspaper Ad'), 
                    reply ONLY with the word: IGNORE
                    """
                    
                    # Ask the AI for its opinion
                    ai_analysis = client.models.generate_content(
                        model='gemini-1.5-flash',
                        contents=prompt
                    )
                    decision = ai_analysis.text.strip()
                    
                    # If the AI thinks it's interesting (didn't say IGNORE)
                    if "IGNORE" not in decision.upper():
                        final_message = f"📰 {decision}\n\n🔗 Source: {entry.link}"
                        
                        # Send the alert to your Telegram
                        tg_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                        requests.post(tg_url, json={"chat_id": TG_CHAT, "text": final_message})
                        print(f"✅ Alert sent for: {entry.title}")
                    else:
                        print(f"⏭️ Skipping routine filing: {entry.title}")
        else:
            print(f"Could not reach BSE. Error code: {response.status_code}")

    except Exception as e:
        print(f"Something went wrong: {e}")

if __name__ == "__main__":
    analyze_and_send()
