# PythonAnywhere Deployment Guide

Deploy the Stock Screener app permanently for **free** on PythonAnywhere.
Your app will be live at `https://yourusername.pythonanywhere.com`.

> No credit card. No expiry. Truly permanent free hosting.

---

## Prerequisites

- A [PythonAnywhere](https://www.pythonanywhere.com) Beginner account (free)
- Your GitHub repo: `https://github.com/iampotato-ai/stock-screener`

---

## Phase 1 — Account Setup

1. Go to [pythonanywhere.com](https://www.pythonanywhere.com) → **Create a Beginner account**
2. Pick your username carefully — your app URL will be `yourusername.pythonanywhere.com`

---

## Phase 2 — Clone the Repo

1. Dashboard → **Consoles** → **Bash** → **Start a new console**

2. Clone the repo:
   ```bash
   git clone https://github.com/iampotato-ai/stock-screener.git
   cd stock-screener
   ```

3. Create a virtualenv:
   ```bash
   mkvirtualenv stock-screener --python=python3.11
   ```
   Your prompt will show `(stock-screener)` when active.

4. Install the slim production dependencies (excludes `torch`, `transformers`, `playwright` which are too heavy for free tier):
   ```bash
   pip install flask flask-sqlalchemy apscheduler requests pandas openpyxl xgboost==2.0.3 joblib==1.3.2 prophet statsmodels
   ```

---

## Phase 3 — Configure the WSGI File

1. Dashboard → **Web** → **Add a new web app**
2. Click **Next** → select **Manual configuration** (NOT the Flask shortcut)
3. Select **Python 3.11** → click **Next**

4. PythonAnywhere will create a WSGI file at:
   ```
   /var/www/yourusername_pythonanywhere_com_wsgi.py
   ```
   Click the link to open and edit it.

5. **Delete everything** in the file and paste the following (replace `yourusername` with your actual username):

   ```python
   import sys
   import os

   # Add project to path
   project_home = '/home/yourusername/stock-screener'
   if project_home not in sys.path:
       sys.path.insert(0, project_home)

   # Environment variables
   os.environ['FLASK_ENV'] = 'production'
   os.environ['FLASK_DEBUG'] = 'False'
   os.environ['SECRET_KEY'] = 'replace-with-a-long-random-string'
   os.environ['NLP_MODELS_ENABLED'] = 'False'
   os.environ['ENABLE_NLP_ENRICHMENT'] = 'False'
   os.environ['ENABLE_TELEGRAM_ALERTS'] = 'False'
   os.environ['ENABLE_BACKGROUND_TASKS'] = 'True'
   os.environ['EP_MODEL_TRAINING_ENABLED'] = 'False'

   # Import and expose the app
   from app import create_app
   application = create_app('production')
   ```

---

## Phase 4 — Web Tab Configuration

In the **Web** tab, set the following fields:

| Field | Value |
|---|---|
| **Source code** | `/home/yourusername/stock-screener` |
| **Working directory** | `/home/yourusername/stock-screener` |
| **Virtualenv** | `/home/yourusername/.virtualenvs/stock-screener` |

### Static Files

Scroll to the **Static files** section and add:

| URL | Directory |
|---|---|
| `/static/` | `/home/yourusername/stock-screener/static` |

This lets PythonAnywhere serve CSS/JS directly without going through Flask — faster and saves CPU quota.

---

## Phase 5 — Launch

1. Click the big green **Reload** button at the top of the Web tab.
2. Visit `https://yourusername.pythonanywhere.com` — your app is live ✅

---

## Troubleshooting

If something breaks, go to **Web tab → Error log**.

| Error | Fix |
|---|---|
| `ModuleNotFoundError: flask` | Virtualenv path is wrong in the Web tab |
| `No module named 'app'` | Source code path is wrong — check Phase 4 |
| `500 Internal Server Error` | Check error log, usually a missing env var |
| Scheduler warnings in log | Normal on PythonAnywhere — app will still load fine |

---

## Keeping It Alive

PythonAnywhere free web apps expire after **3 months of inactivity** — you'll receive an email reminder and just need to click a button to extend.

**Optional:** Add a scheduled task (Web tab → **Tasks**) to keep the scheduler warm:
```bash
curl -s https://yourusername.pythonanywhere.com/api/health > /dev/null
```
Set it to run **every hour**.

---

## Updating the App

Whenever you push new code to GitHub, SSH into the Bash console and run:

```bash
cd ~/stock-screener
git pull origin feature/workspace-ui
```

Then go to the **Web tab** and click **Reload**.

---

## Environment Variables Reference

| Variable | Production Value | Notes |
|---|---|---|
| `FLASK_ENV` | `production` | Enables `ProductionConfig` |
| `FLASK_DEBUG` | `False` | Must be off in production |
| `SECRET_KEY` | *(your secret string)* | Use a long random value |
| `NLP_MODELS_ENABLED` | `False` | Disables heavy torch/transformers |
| `ENABLE_NLP_ENRICHMENT` | `False` | Disables NLP annotation pipeline |
| `ENABLE_BACKGROUND_TASKS` | `True` | Keeps scheduler running |
| `ENABLE_TELEGRAM_ALERTS` | `False` | Set `True` if you want alerts |
| `EP_MODEL_TRAINING_ENABLED` | `False` | Disables model retraining on server |

---

## Free Tier Limits

| Resource | Limit |
|---|---|
| Disk | 512 MB |
| CPU (daily) | 100 seconds (resets daily) |
| Always-on | ✅ No spin-down |
| SQLite | ✅ Persists across restarts |
| Outbound HTTP | ⚠️ Restricted to whitelisted domains |
| Custom domain | ❌ Paid only (`yourusername.pythonanywhere.com` is free) |

> **Note on outbound HTTP:** Yahoo Finance, TradingView scanner, and Google News RSS are commonly accessible on the free tier. If an API call fails with a connection error, it is likely blocked — check [PythonAnywhere's whitelist](https://www.pythonanywhere.com/whitelist/).
