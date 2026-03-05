import requests
from datetime import datetime

# --- YOUR WATCHLIST ---
WATCHLIST = ["RELIANCE", "INFOSYS", "TATA MOTORS", "HDFC BANK", "Geojit Financial Services"] 

def fetch_news():
    url = "https://api.bseindia.com/BseOnlineReporting/api/AnnSubCategorywise/GetAnnData"
    
    # This is the "Fake ID" part (Headers)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bseindia.com/",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.bseindia.com"
    }
    
    params = {
        "pType": "Equity",
        "pPeriod": "P",
        "pFromDate": datetime.now().strftime("%Y%m%d"),
        "pToDate": datetime.now().strftime("%Y%m%d"),
        "pCategory": "-1",
        "pSubCategory": "-1"
    }
    
    try:
        # We tell the robot to try and connect
        response = requests.get(url, params=params, headers=headers)
        
        # Check if the website actually allowed us in
        if response.status_code != 200:
            print(f"BSE blocked us. Status Code: {response.status_code}")
            return

        data = response.json()
        
        found_something = False
        for item in data:
            company_name = item['SLONGNAME'].upper()
            headline = item['NEWSSUB']
            
            if any(name in company_name for name in WATCHLIST):
                if "trading window" not in headline.lower():
                    print(f"🚨 ALERT for {item['SLONGNAME']}: {headline}")
                    found_something = True
        
        if not found_something:
            print("Successfully checked BSE. No new updates for your companies yet.")
            
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    fetch_news()
