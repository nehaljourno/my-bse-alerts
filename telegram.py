import os
import requests

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

resp = requests.post(url, json={
    "chat_id": TELEGRAM_CHAT_ID,
    "text":    "Test message from BSE scraper ✅",
}, timeout=15)

print(f"Status: {resp.status_code}")
print(f"Response: {resp.json()}")
