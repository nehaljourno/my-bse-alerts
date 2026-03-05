import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- YOUR WATCHLIST ---
WATCHLIST = ["RELIANCE", "INFOSYS", "TATA", "ADANI", "HDFC"]

def fetch_bse_direct():
    chrome_options = Options()
    chrome_options.add_argument("--headless") # Runs without a window
    chrome_options.add_argument("--no-sandbox")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        print("Opening BSE Announcements Page...")
        driver.get("https://www.bseindia.com/corporates/ann.html")
        
        # Wait up to 20 seconds for the news table to actually appear
        wait = WebDriverWait(driver, 20)
        table = wait.until(EC.presence_of_element_located((By.ID, "lblann")))
        
        # Once the table is loaded, we grab the text
        news_items = driver.find_elements(By.CLASS_NAME, "tableborder")
        
        found = False
        for item in news_items:
            text = item.text.upper()
            # Check if any of your companies are mentioned in the text
            if any(company in text for company in WATCHLIST):
                if "TRADING WINDOW" not in text:
                    print(f"🚨 MATCH FOUND: \n{item.text}")
                    print("-" * 30)
                    found = True
        
        if not found:
            print("Page loaded successfully, but no watchlist matches found right now.")

    except Exception as e:
        print(f"Error: The page took too long to load or was blocked. {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    fetch_bse_direct()
