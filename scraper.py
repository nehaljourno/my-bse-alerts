import requests
import pandas as pd
from datetime import datetime

# This part tells the robot to look at the BSE Website
def fetch_news():
    url = "https://api.bseindia.com/BseOnlineReporting/api/AnnSubCategorywise/GetAnnData"
    headers = {"User-Agent": "Mozilla/5.0"}
    params = {
        "pType": "Equity",
        "pPeriod": "P",
        "pFromDate": datetime.now().strftime("%Y%m%d"),
        "pToDate": datetime.now().strftime("%Y%m%d"),
        "pCategory": "-1",
        "pSubCategory": "-1"
    }
    
    response = requests.get(url, params=params, headers=headers)
    data = response.json()
    
    # This part filters out the 'boring' stuff for you
    boring_stuff = ["trading window", "loss of share", "duplicate", "compliance"]
    
    for item in data:
        headline = item['NEWSSUB']
        company = item['SLONGNAME']
        
        # If the headline DOES NOT have boring words, print it
        if not any(word in headline.lower() for word in boring_stuff):
            print(f"INTERESTING NEWS: {company} - {headline}")

if __name__ == "__main__":
    fetch_news()
