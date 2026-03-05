import feedparser

# --- YOUR WATCHLIST ---
# Tip: Use short, unique parts of the company name
WATCHLIST = ["RELIANCE", "INFOSYS", "TATA MOTORS", "HDFC BANK", "ADANI", "Shriram Asset Management"]

def check_rss_feed():
    # This is the official BSE "Corporate Announcements" RSS Feed
    rss_url = "https://www.bseindia.com/RSS/Corporate_Ann.xml"
    
    print("Checking BSE RSS Feed...")
    
    # The robot 'parses' (reads) the feed
    feed = feedparser.parse(rss_url)
    
    found_something = False
    
    # Loop through every news item in the feed
    for entry in feed.entries:
        # entry.title usually contains 'Company Name - Subject'
        headline = entry.title.upper()
        
        # 1. Check if company is in your watchlist
        if any(company in headline for company in WATCHLIST):
            
            # 2. Filter out the boring 'Trading Window' noise
            if "TRADING WINDOW" not in headline:
                print(f"🚨 MATCH FOUND: {entry.title}")
                print(f"Link to PDF: {entry.link}")
                print("-" * 30)
                found_something = True
                
    if not found_something:
        print("Feed checked. No new watchlist matches in the latest 100 filings.")

if __name__ == "__main__":
    check_rss_feed()
