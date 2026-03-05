import feedparser
import requests
import google.generativeai as genai
import os

# --- CONFIGURATION ---
WATCHLIST = ["WAAREE", "RELIANCE", "TATA", "INFOSYS", "ADANI"]

# PASTE YOUR SECRETS HERE
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

def analyze_with_ai(headline):
    prompt = f"""
    You are a senior business journalist. Analyze this BSE corporate disclosure headline: "{headline}"
    
    1. Is this 'Procedural' (boring/routine) or 'Material' (important business news)?
    2. If it is Material, provide a 1-line punchy summary for a journalist.
    3. If it is Procedural, reply with the word 'IGNORE'.
    
    Examples of Material: CEO resignation, major orders, mergers, earnings beats, fraud allegations.
    Examples of Procedural: Trading window closure, board meeting intimation, change of address.
    """
    response = model.generate_content(prompt)
    return response.text.strip()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, json=payload)

def check_bse():
    feed = feedparser.parse("https://www.bseindia.com/RSS/Corporate_Ann.xml")
    
    for entry in feed.entries:
        headline = entry.title.upper()
        
        if any(company in headline for company in WATCHLIST):
            # Let the AI decide
            analysis = analyze_with_ai(entry.title)
            
            if "IGNORE" not in analysis.upper():
                # Only send to Telegram if it's interesting!
                final_alert = f"📰 {analysis}\n\n🔗 Source: {entry.link}"
                send_telegram(final_alert)
                print(f"Sent alert: {analysis}")

if __name__ == "__main__":
    check_bse()
