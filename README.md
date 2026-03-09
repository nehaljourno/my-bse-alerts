# BSE Corporate Announcement Scraper 🔔

Monitors BSE India for corporate announcements, filters by your watchlist, uses Claude AI to summarise the attached PDF/XML, and fires a one-line Telegram alert.

---

## How it works

```
GitHub Actions (every 10 min, market hours)
        │
        ▼
  Fetch BSE API  ──►  Filter by companies.csv
        │
        ▼
  Download PDF/XML attachment
        │
        ▼
  Claude AI → one-line summary
        │
        ▼
  Telegram alert 🔔
```

---

## Quick Setup (15 minutes)

### 1 — Fork / clone this repo

```bash
git clone https://github.com/YOUR_USERNAME/bse-scraper.git
cd bse-scraper
```

### 2 — Edit your watchlist

Open `companies.csv` and add the companies you want to track.  
Both the company name and BSE scrip code are matched, so providing both improves accuracy:

```csv
company_name,bse_code
Reliance Industries,500325
Tata Motors,500570
```

You can find BSE scrip codes at [bseindia.com](https://www.bseindia.com/).

### 3 — Create a Telegram Bot

1. Open Telegram and message `@BotFather`
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** (looks like `123456:ABC-DEF...`)
4. Start a chat with your new bot (or add it to a group)
5. Get your **chat ID**:
   - For personal chat: message `@userinfobot`
   - For a group: add `@RawDataBot` to the group, it will show the chat ID

### 4 — Get API keys

| Key | Where to get it |
|-----|----------------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) |
| `TELEGRAM_BOT_TOKEN` | From `@BotFather` (step 3 above) |
| `TELEGRAM_CHAT_ID` | Your personal or group chat ID |

### 5 — Add GitHub Secrets

In your GitHub repo:  
**Settings → Secrets and variables → Actions → New repository secret**

Add these three secrets:

| Secret name | Value |
|-------------|-------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your chat / group ID |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |

### 6 — Push and enable Actions

```bash
git add companies.csv
git commit -m "Add my watchlist"
git push
```

Then go to **Actions** tab in GitHub and make sure workflows are enabled.

To test immediately: **Actions → BSE Announcement Scraper → Run workflow**

---

## Sample Telegram Alert

```
🔔 Reliance Industries [500325]
📋 Board approves ₹5,000 Cr capex for new petrochemical plant in Gujarat.
🕐 2025-03-07 14:32
```

---

## Customisation

### Change the schedule

Edit `.github/workflows/scraper.yml`:

```yaml
# Every 5 minutes all day
- cron: "*/5 * * * 1-5"

# Every 10 minutes, all hours
- cron: "*/10 * * * *"
```

> ⚠️ GitHub Actions has a minimum interval of ~5 minutes and may delay low-priority runs by a few minutes.

### Run outside market hours

Remove the hour restriction in the cron:
```yaml
- cron: "*/10 * * * 1-5"   # Mon–Fri, any time
```

### Change the AI summary style

In `scraper.py`, find the prompt and edit to taste:
```python
"Summarise the key fact from this announcement in ONE "
"concise sentence (max 25 words)."
```

---

## File structure

```
bse-scraper/
├── .github/
│   └── workflows/
│       └── scraper.yml          # GitHub Actions schedule
├── scraper.py                   # Main script
├── companies.csv                # Your watchlist ← edit this
├── seen_announcements.json      # Auto-managed cache (don't edit)
├── requirements.txt
└── README.md
```

---

## Cost estimate

| Service | Estimated cost |
|---------|---------------|
| GitHub Actions | Free (2,000 min/month on free tier; ~300 runs/month) |
| Claude API | ~$0.003 per PDF summary (Sonnet) |
| Telegram | Free |

For 10 hits/day → ~₹7/day in Claude API costs.

---

## Troubleshooting

**No alerts received**
- Check the Actions run log for errors
- Verify all three secrets are set correctly
- Run the workflow manually and check the output

**"Failed to fetch announcements"**
- BSE occasionally blocks scrapers; the script will retry on the next run
- If persistent, the BSE API URL may have changed — open an issue

**Too many / too few matches**
- Add BSE scrip codes to `companies.csv` for exact matching
- Partial name matching can produce false positives for short names
