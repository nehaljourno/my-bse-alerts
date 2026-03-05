import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# --- YOUR WATCHLIST ---
WATCHLIST = ["RELIANCE", "INFOSYS", "TATA", "ADANI", "HDFC"]

def run_scraper():
    options = Options()
    options.add_argument("--headless=new") # Use the 'new' stealthy headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # This line tells the website we are a real person on a Windows computer
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=options)
    # Give the browser more time to wait for the website
    driver.set_page_load_timeout(180) 
    
    try:
        print("Visiting BSE with Stealth Mode...")
        # We visit Google first so it looks like we clicked a link
        driver.get("https://www.google.com")
        time.sleep(2)
        
        driver.get("https://www.bseindia.com/corporates/ann.html")
        
        # We wait 15 seconds for the table to appear
        time.sleep(15)
        
        news_items = driver.find_elements(By.CLASS_NAME, "tableborder")
        
        found = False
        for item in news_items:
            content = item.text.upper()
            if any(company in content for company in WATCHLIST):
                if "TRADING WINDOW" not in content:
                    print(f"MATCH: {item.text}")
                    found = True
        
        if not found:
            print("Successfully checked. No matches today.")
            
    except Exception as e:
        print(f"BSE is still being difficult. Error: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_scraper()
