import os
import requests
import time
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import threading
from flask import Flask, jsonify, render_template
import sqlite3
import numpy as np
import pandas as pd
from prophet import Prophet
from statsmodels.tsa.arima.model import ARIMA
import warnings
warnings.filterwarnings('ignore')  # suppress Prophet/ARIMA verbose output
import logging
logging.getLogger('cmdstanpy').setLevel(logging.WARNING)
from statsmodels.tools.sm_exceptions import ConvergenceWarning
warnings.simplefilter('ignore', ConvergenceWarning)
warnings.simplefilter('ignore', UserWarning)

from journal_math import compute_pnl_and_r
from rrg_math import compute_jdk_rs, compute_quadrant
from forecast_math import compute_forecast_metrics
import pattern_detection



def init_db():
    conn = sqlite3.connect('scan_history.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS scan_history (
            date TEXT,
            ticker TEXT,
            UNIQUE(date, ticker)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS scan_price_log (
            date TEXT,
            ticker TEXT,
            close REAL,
            swingband TEXT,
            setupLabel TEXT,
            PRIMARY KEY (date, ticker)
        )
    ''')
    
    # Check if table breadth_history exists and what its PK is
    c.execute("PRAGMA table_info(breadth_history)")
    columns = c.fetchall()
    
    needs_recreate = False
    if columns:
        pk_count = sum(1 for col in columns if col[5] > 0)
        if pk_count > 1:
            needs_recreate = True
            
    if needs_recreate:
        print("Migrating breadth_history to unique date primary key...")
        c.execute("SELECT * FROM breadth_history ORDER BY date ASC, time ASC")
        all_rows = c.fetchall()
        
        unique_date_rows = {}
        for row in all_rows:
            date_val = row[0]
            unique_date_rows[date_val] = row
            
        c.execute("DROP TABLE breadth_history")
        c.execute('''
            CREATE TABLE breadth_history (
                date TEXT PRIMARY KEY,
                time TEXT,
                advances INTEGER,
                declines INTEGER,
                unchanged INTEGER,
                pct_sma21 REAL,
                pct_sma50 REAL,
                pct_52high REAL,
                avg_recommend REAL,
                regime_score INTEGER,
                regime_band TEXT
            )
        ''')
        
        for row in unique_date_rows.values():
            c.execute(
                "INSERT INTO breadth_history VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                row
            )
    else:
        c.execute('''
            CREATE TABLE IF NOT EXISTS breadth_history (
                date TEXT PRIMARY KEY,
                time TEXT,
                advances INTEGER,
                declines INTEGER,
                unchanged INTEGER,
                pct_sma21 REAL,
                pct_sma50 REAL,
                pct_52high REAL,
                avg_recommend REAL,
                regime_score INTEGER,
                regime_band TEXT
            )
        ''')
    # Enable foreign keys
    c.execute("PRAGMA foreign_keys = ON;")
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlist_sections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        )
    ''')
    try:
        c.execute("ALTER TABLE watchlist_sections ADD COLUMN position INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # position column already exists
    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            UNIQUE(section_id, ticker),
            FOREIGN KEY(section_id) REFERENCES watchlist_sections(id) ON DELETE CASCADE
        )
    ''')
    try:
        c.execute("ALTER TABLE watchlist_items ADD COLUMN position INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # position column already exists
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_journal (
            id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            setupLabel TEXT NOT NULL,
            swingband TEXT NOT NULL,
            entry REAL NOT NULL,
            stop REAL NOT NULL,
            target1 REAL NOT NULL,
            target2 REAL NOT NULL,
            target3 REAL NOT NULL,
            riskAmount REAL NOT NULL,
            qty INTEGER NOT NULL,
            status TEXT NOT NULL,
            exitPrice REAL,
            exitDate TEXT,
            pnl REAL,
            rAchieved REAL,
            notes TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS kronos_forecasts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            pred_len    INTEGER NOT NULL,
            forecast_json TEXT NOT NULL,
            last_close  REAL NOT NULL,
            model_type  TEXT NOT NULL DEFAULT 'kronos'
        )
    ''')
    # Safe migration: add model_type column if upgrading from an older schema
    try:
        c.execute("ALTER TABLE kronos_forecasts ADD COLUMN model_type TEXT NOT NULL DEFAULT 'kronos'")
        # Backfill any existing rows that have NULL model_type (from pre-migration rows)
        c.execute("UPDATE kronos_forecasts SET model_type = 'kronos' WHERE model_type IS NULL")
        print("[DB Migration] Added model_type column to kronos_forecasts")
    except Exception:
        pass  # Column already exists — safe to ignore

    c.execute('''
        CREATE TABLE IF NOT EXISTS rrg_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            week        TEXT NOT NULL,
            sector      TEXT NOT NULL,
            jdk_rs      REAL NOT NULL,
            jdk_rs_momentum REAL NOT NULL,
            score       INTEGER,
            quadrant    TEXT,
            snapped_at  TEXT NOT NULL,
            UNIQUE(week, sector)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS pattern_cache (
            ticker TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            pattern_name TEXT,
            pattern_grade TEXT,
            pattern_desc TEXT,
            candlestick_json TEXT,
            pattern_bias REAL DEFAULT 0.0,
            max_down_vol_10 REAL,
            volume_sma_50 REAL
        )
    ''')
    try:
        c.execute("ALTER TABLE pattern_cache ADD COLUMN candlestick_json TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE pattern_cache ADD COLUMN pattern_bias REAL DEFAULT 0.0")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE pattern_cache ADD COLUMN max_down_vol_10 REAL")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE pattern_cache ADD COLUMN volume_sma_50 REAL")
    except Exception:
        pass
        
    # ---------- pattern_signals (Phase 2 addition) ----------
    c.execute('''
        CREATE TABLE IF NOT EXISTS pattern_signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            timeframe   TEXT NOT NULL DEFAULT 'D',
            signal_type TEXT NOT NULL,           -- 'candle' | 'chart'
            pattern     TEXT NOT NULL,
            direction   INTEGER NOT NULL,        -- 100 bullish, -100 bearish
            confidence  REAL,                    -- 0.0-1.0 (chart patterns only)
            description TEXT,
            detected_at TEXT NOT NULL,
            bar_date    TEXT                     -- date of the last bar in the signal
        )
    ''')
    # Index for fast per-ticker lookups
    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_pattern_signals_ticker
        ON pattern_signals (ticker, detected_at DESC)
    ''')
    try:
        c.execute("ALTER TABLE pattern_signals ADD COLUMN bar_date TEXT")
    except Exception:
        pass  # already exists
    
    # ---------- IPO / SME Momentum Tab Tables ----------
    c.execute('''
        CREATE TABLE IF NOT EXISTS ipo_listings (
            ticker          TEXT PRIMARY KEY,
            company_name    TEXT NOT NULL,
            listing_date    TEXT NOT NULL,
            issue_price     REAL,
            listing_open    REAL,
            listing_close   REAL,
            exchange        TEXT DEFAULT 'NSE',
            sector          TEXT,
            issue_size_cr   REAL,
            lot_size        INTEGER,
            gmp_at_listing  REAL,
            added_at        TEXT DEFAULT (datetime('now'))
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ipo_listing_date ON ipo_listings(listing_date DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ipo_exchange ON ipo_listings(exchange)')

    c.execute('''
        CREATE TABLE IF NOT EXISTS ipo_metrics_cache (
            ticker                  TEXT PRIMARY KEY,
            company_name            TEXT NOT NULL,
            listing_date            TEXT NOT NULL,
            exchange                TEXT NOT NULL,
            sector                  TEXT,
            issue_price             REAL,
            listing_gain_pct        REAL,
            current_vs_issue_pct    REAL,
            current_vs_listing_pct  REAL,
            days_since_listing      INTEGER,
            rvol_ratio              REAL,
            above_listing_high      INTEGER,
            drawdown_from_ath       REAL,
            swing_score             INTEGER,
            pattern_name            TEXT,
            momentum_phase          TEXT,
            current_price           REAL,
            cached_at               TEXT NOT NULL
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ipo_metrics_phase ON ipo_metrics_cache(momentum_phase)')
    
    # Run migrations for volume, change_pct, and day range columns
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN volume REAL")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN change_pct REAL")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN day_low REAL")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN day_high REAL")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()

# ---------------------------------------------------------------------------
# NSE IPO Live Feed — two-step browser-session warm-up (same pattern used
# by fetch_nse_announcements / fetch_nse_block_deals throughout this file)
# ---------------------------------------------------------------------------

NSE_IPO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/new-issues-ipo",
}

def get_nse_ipo_session():
    """Return a warmed-up requests.Session with valid NSE cookies."""
    session = requests.Session()
    session.headers.update(NSE_IPO_HEADERS)
    try:
        # Warm up by visiting the landing page first to obtain session cookies
        session.get("https://www.nseindia.com/market-data/new-issues-ipo", timeout=10)
    except Exception as e:
        print(f"[NSE IPO Session] Warm-up failed: {e}")
    return session


def fetch_nse_past_issues():
    """
    Fetch all past IPO issues from NSE public-past-issues API.
    Returns a list of raw dicts, or [] on failure.
    NSE returns either {"data": [...]} or a bare list.
    """
    session = get_nse_ipo_session()
    try:
        resp = session.get(
            "https://www.nseindia.com/api/public-past-issues",
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("data", [])
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"[NSE IPO] fetch_nse_past_issues failed: {e}")
        return []


# Fallback mock data used only when NSE fetch fails at startup
_IPO_MOCK_FALLBACK = [
    ("OLAELEC.NS",    "Ola Electric Mobility Ltd",           "2025-08-09", 76.0,   75.0,   91.0,   "NSE", "Automobile",       6145.0, 195,  15.0),
    ("PREMIERENE.NS", "Premier Energies Ltd",                "2025-09-03", 450.0,  840.0,  838.0,  "NSE", "Capital Goods",    2830.0,  33, 350.0),
    ("HYUNDAI.NS",    "Hyundai Motor India Ltd",             "2025-10-22", 1960.0, 1931.0, 1845.0, "NSE", "Automobile",      27870.0,   7, -40.0),
    ("WAAREEENER.NS", "Waaree Energies Ltd",                 "2025-10-28", 1503.0, 2550.0, 2340.0, "NSE", "Capital Goods",    4321.0,   9, 1200.0),
    ("SWIGGY.NS",     "Swiggy Ltd",                         "2025-11-13", 390.0,  420.0,  455.0,  "NSE", "Services",        11327.0,  38,  25.0),
    ("BAJAJHFL.NS",   "Bajaj Housing Finance Ltd",           "2025-09-16", 70.0,   150.0,  165.0,  "NSE", "Financial Services", 6560.0, 214,  80.0),
    ("FIRSTCRY.NS",   "Brainbees Solutions Ltd (FirstCry)",  "2025-08-13", 465.0,  651.0,  673.0,  "NSE", "Services",         4193.0,  32,  80.0),
    ("KRN.NS",        "KRN Heat Exchanger Ltd",              "2025-10-03", 220.0,  480.0,  478.0,  "NSE", "Capital Goods",     342.0,  65, 240.0),
    ("TATATECH.NS",   "Tata Technologies Ltd",               "2025-06-15", 500.0,  1200.0, 1313.0, "NSE", "IT",               3042.0,  30, 700.0),
    ("IREDA.NS",      "Indian Renewable Energy Dev Agency",  "2025-06-20", 32.0,   50.0,   60.0,   "NSE", "Financial Services", 2150.0, 460,  15.0),
    ("DOMS.NS",       "DOMS Industries Ltd",                 "2025-07-05", 790.0,  1400.0, 1395.0, "NSE", "Consumer Durables", 1200.0,  18, 500.0),
    ("MUTHOOTMF.NS",  "Muthoot Microfin Ltd",                "2025-07-28", 291.0,  275.0,  266.0,  "NSE", "Financial Services",  960.0,  51, -10.0),
    ("HAPPYFORGE.NS", "Happy Forgings Ltd",                  "2025-08-05", 850.0,  1000.0, 985.0,  "NSE", "Capital Goods",    1008.0,  17, 120.0),
    ("EXICOM.NS",     "Exicom Tele-Systems Ltd",             "2025-09-20", 142.0,  265.0,  259.0,  "NSE", "Telecommunication",  429.0, 100, 110.0),
    ("UNIPARTS.NS",   "Uniparts India Ltd",                  "2025-10-10", 577.0,  575.0,  540.0,  "NSE", "Capital Goods",     835.0,  25, -20.0),
    ("BSE.NS",        "BSE Limited",                         "2025-06-01", 400.0,  420.0,  450.0,  "BSE", "Financial Services", 5000.0,  30,  20.0),
]


def seed_ipo_listings():
    """
    Populate ipo_listings from the live NSE public-past-issues API.
    Only inserts mainboard (non-SME) listings from the last 12 months.
    Falls back to _IPO_MOCK_FALLBACK if the live fetch fails.
    """
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=365)

    conn = sqlite3.connect('scan_history.db')
    c = conn.cursor()
    # Remove stale entries older than 12 months
    c.execute(
        "DELETE FROM ipo_listings WHERE listing_date < ?",
        (cutoff.strftime("%Y-%m-%d"),)
    )
    conn.commit()

    # --- Attempt live NSE feed ---
    raw = fetch_nse_past_issues()
    live_inserted = 0

    if raw:
        # Debug: log first item's keys so mismatches are caught early
        if raw:
            print(f"[NSE IPO] Sample keys: {list(raw[0].keys())[:12]}")

        for item in raw:
            try:
                # NSE field names (confirmed from public-past-issues response)
                listing_date_str = (
                    item.get("listingDate")
                    or item.get("listing_date")
                    or item.get("Listing Date")
                    or ""
                ).strip()
                issue_price_str = str(
                    item.get("issuePrice")
                    or item.get("issue_price")
                    or item.get("Issue Price")
                    or "0"
                ).replace(",", "").replace("\u20b9", "").strip()
                symbol = (
                    item.get("symbol")
                    or item.get("companyName")
                    or item.get("Symbol")
                    or ""
                ).strip().upper()
                company_name = (
                    item.get("companyName")
                    or item.get("name")
                    or item.get("Company Name")
                    or symbol
                ).strip()
                exchange_raw = (
                    item.get("exchange")
                    or item.get("Exchange")
                    or "NSE"
                ).strip().upper()
                series = (
                    item.get("series")
                    or item.get("Series")
                    or ""
                ).strip().upper()

                if not listing_date_str or not symbol:
                    continue

                # Skip SME listings and non-equity issues
                security_type = str(item.get("securityType") or "").strip().upper()
                if "SME" in series or "SME" in exchange_raw or "SME" in security_type:
                    continue
                if security_type and security_type != "EQ":
                    continue

                # Normalise exchange to NSE / BSE only
                if "NSE" in exchange_raw:
                    exchange = "NSE"
                elif "BSE" in exchange_raw:
                    exchange = "BSE"
                else:
                    continue  # skip unknown exchanges

                # Parse listing date — NSE uses DD-MMM-YYYY or YYYY-MM-DD
                listing_date = None
                for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                    try:
                        listing_date = datetime.strptime(listing_date_str, fmt)
                        break
                    except ValueError:
                        continue
                if listing_date is None:
                    continue

                # Only last 12 months
                if listing_date < cutoff:
                    continue

                issue_price = float(issue_price_str or "0") if issue_price_str else 0.0

                # Insert NSE listing
                ticker_ns = f"{symbol}.NS"
                c.execute(
                    '''
                    INSERT OR IGNORE INTO ipo_listings (
                        ticker, company_name, listing_date, issue_price,
                        listing_open, listing_close, exchange, sector,
                        issue_size_cr, lot_size, gmp_at_listing
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        ticker_ns,
                        company_name,
                        listing_date.strftime("%Y-%m-%d"),
                        issue_price,
                        0.0,
                        0.0,
                        "NSE",
                        item.get("sector") or item.get("Sector") or "",
                        0.0,
                        0,
                        0.0,
                    )
                )
                if c.rowcount:
                    live_inserted += 1

                # Simultaneously insert BSE counterpart if it's an NSE listing (since mainboard IPOs list on both)
                if exchange == "NSE":
                    ticker_bo = f"{symbol}.BO"
                    c.execute(
                        '''
                        INSERT OR IGNORE INTO ipo_listings (
                            ticker, company_name, listing_date, issue_price,
                            listing_open, listing_close, exchange, sector,
                            issue_size_cr, lot_size, gmp_at_listing
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''',
                        (
                            ticker_bo,
                            company_name,
                            listing_date.strftime("%Y-%m-%d"),
                            issue_price,
                            0.0,
                            0.0,
                            "BSE",
                            item.get("sector") or item.get("Sector") or "",
                            0.0,
                            0,
                            0.0,
                        )
                    )
                    if c.rowcount:
                        live_inserted += 1

            except Exception as e:
                print(f"[IPO Seed] Row error: {e} | row: {item}")
                continue

        conn.commit()
        print(f"[IPO Seed] Inserted {live_inserted} mainboard IPOs (last 12 months) from NSE live feed.")

    # --- Fallback: use mock data if live fetch returned nothing ---
    if not raw:
        print("[IPO Seed] Live NSE fetch returned no data — using mock fallback.")
        for row in _IPO_MOCK_FALLBACK:
            c.execute(
                '''
                INSERT OR IGNORE INTO ipo_listings (
                    ticker, company_name, listing_date, issue_price,
                    listing_open, listing_close, exchange, sector,
                    issue_size_cr, lot_size, gmp_at_listing
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                row
            )
        conn.commit()
        print(f"[IPO Seed] Fallback: inserted {len(_IPO_MOCK_FALLBACK)} mock rows.")

    conn.close()


init_db()
seed_ipo_listings()


def classify_momentum_phase(days_since, current_vs_issue, current_vs_listing):
    hot_threshold    = 15
    broken_threshold = -10

    if days_since <= 10 and current_vs_issue > hot_threshold:
        return "HOT"
    elif current_vs_listing > 5:
        return "STABLE"
    elif current_vs_listing < broken_threshold:
        return "BROKEN"
    else:
        return "FADING"


# Bug #3 fix — defined at module level so it is not re-created on every ticker
# inside the ThreadPoolExecutor. This is the standard Wilder smoothed RSI.
def _calculate_rsi(prices, period=14):
    """Compute 14-period Wilder-smoothed RSI from a list of closing prices."""
    if len(prices) <= period:
        return 60.0  # neutral-bullish default for new listings with sparse history
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains  = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# Bug #6 fix — single helper replaces the copy-pasted volume-parsing block
# that appeared twice in get_ipo_listings() (main query + summary query).
def _parse_volume_param(val_str):
    """Parse a volume string like '100k', '1m', '500' into a float.
    Returns None if the string is empty, 'all', or unparseable."""
    if not val_str or val_str.lower() == 'all':
        return None
    try:
        s = val_str.lower().strip()
        multiplier = 1
        if s.endswith('k'):
            multiplier = 1_000
            s = s[:-1]
        elif s.endswith('m'):
            multiplier = 1_000_000
            s = s[:-1]
        return float(s) * multiplier
    except ValueError:
        return None


def refresh_ipo_metrics():
    """
    Refreshes metrics for all IPO listings in parallel and updates the ipo_metrics_cache table.
    """
    conn = sqlite3.connect('scan_history.db')
    c = conn.cursor()
    c.execute("DELETE FROM ipo_metrics_cache WHERE ticker NOT IN (SELECT ticker FROM ipo_listings)")
    conn.commit()
    c.execute("SELECT ticker, company_name, listing_date, issue_price, listing_close, exchange, sector FROM ipo_listings")
    listings = c.fetchall()
    conn.close()
    
    from datetime import datetime
    import time
    
    def _update_single(row):
        ticker, company_name, listing_date, issue_price, listing_close, exchange, sector = row
        try:
            # Fetch history
            history = fetch_historical_prices(ticker, range_str="1y")
            if not history:
                return
                
            closes  = [float(h["close"])  for h in history]
            highs   = [float(h["high"])   for h in history]
            volumes = [float(h["volume"]) for h in history]
            lows    = [float(h["low"])    for h in history]
            
            if not closes:
                return
                
            current_price = closes[-1]
            current_vol   = volumes[-1]
            # lows/highs are always populated when closes is non-empty (same Yahoo response);
            # the 'else' branch is a safety net for unexpected edge cases only.
            current_low  = lows[-1]  if lows  else current_price
            current_high = highs[-1] if highs else current_price
            avg_vol_20d  = sum(volumes[-20:]) / len(volumes[-20:]) if volumes else 1.0
            
            # Listing close
            lst_close = listing_close if listing_close else closes[0]
            
            # Calculations
            listing_gain_pct        = ((lst_close - issue_price) / issue_price * 100) if issue_price else 0.0
            current_vs_issue_pct    = ((current_price - issue_price) / issue_price * 100) if issue_price else 0.0
            current_vs_listing_pct  = ((current_price - lst_close) / lst_close * 100) if lst_close else 0.0
            
            # Days since listing
            from datetime import datetime
            try:
                lst_dt = datetime.strptime(listing_date, "%Y-%m-%d").date()
                days_since = (datetime.now().date() - lst_dt).days
            except Exception:
                days_since = 0
                
            rvol_ratio = (current_vol / avg_vol_20d) if avg_vol_20d > 0 else 1.0
            ath = max(highs) if highs else current_price
            above_listing_high = 1 if current_price >= max(closes) * 0.98 else 0
            drawdown_from_ath  = ((current_price - ath) / ath * 100) if ath else 0.0
            
            # Calculate actual indicators for swing score
            sma10 = sum(closes[-10:]) / len(closes[-10:]) if len(closes) >= 10 else current_price
            sma21 = sum(closes[-21:]) / len(closes[-21:]) if len(closes) >= 21 else current_price
            sma50 = sum(closes[-50:]) / len(closes[-50:]) if len(closes) >= 50 else current_price
            
            change   = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2  else 0.0
            perf_w   = ((closes[-1] - closes[-5]) / closes[-5] * 100) if len(closes) >= 5  else ((closes[-1] - closes[0]) / closes[0] * 100)
            perf_1m  = ((closes[-1] - closes[-21]) / closes[-21] * 100) if len(closes) >= 21 else ((closes[-1] - closes[0]) / closes[0] * 100)
            perf_3m  = ((closes[-1] - closes[-63]) / closes[-63] * 100) if len(closes) >= 63 else ((closes[-1] - closes[0]) / closes[0] * 100)
            
            # Bug #3 fix — use module-level _calculate_rsi() instead of a nested function
            # Bug #7 note — key is 'RSI' (uppercase) to match compute_swing_score() lookup
            rsi = _calculate_rsi(closes)
            
            # Bug #8 note — 'relative_volume' key matches the lookup in compute_swing_score()
            stock_dict = {
                "ticker":             ticker,
                "clean_ticker":       ticker.replace(".NS", "").replace(".BO", ""),
                "close":              current_price,
                "SMA10":              sma10,
                "SMA21":              sma21,
                "SMA50":              sma50,
                "price_52_week_high": max(highs) if highs else current_price,
                "price_52_week_low":  min(lows)  if lows  else current_price,
                "average_volume":     avg_vol_20d,
                "relative_volume":    rvol_ratio,   # matches compute_swing_score() key
                "Recommend.All":      0.5,
                "sector":             sector,
                "Perf.W":             perf_w,
                "Perf.1M":            perf_1m,
                "Perf.3M":            perf_3m,
                "change":             change,
                "RSI":                rsi,           # uppercase — matches compute_swing_score() key
            }
            
            swing_res   = compute_swing_score(stock_dict)
            swing_score = swing_res.get("swingscore", 0) if isinstance(swing_res, dict) else 0
            pattern_res = classify_technical_pattern(history)
            pattern_name = "None"
            if isinstance(pattern_res, dict):
                pattern_name = pattern_res.get("pattern", "None")
            elif isinstance(pattern_res, str):
                pattern_name = pattern_res
            
            phase = classify_momentum_phase(days_since, current_vs_issue_pct, current_vs_listing_pct)
            
            # Write to cache
            conn2 = sqlite3.connect('scan_history.db')
            c2 = conn2.cursor()
            c2.execute('''
                INSERT OR REPLACE INTO ipo_metrics_cache (
                    ticker, company_name, listing_date, exchange, sector, issue_price,
                    listing_gain_pct, current_vs_issue_pct, current_vs_listing_pct, days_since_listing,
                    rvol_ratio, above_listing_high, drawdown_from_ath, swing_score, pattern_name,
                    momentum_phase, current_price, volume, change_pct, day_low, day_high, cached_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (
                ticker, company_name, listing_date, exchange, sector, issue_price,
                round(listing_gain_pct, 2), round(current_vs_issue_pct, 2), round(current_vs_listing_pct, 2), days_since,
                round(rvol_ratio, 2), above_listing_high, round(drawdown_from_ath, 2), swing_score, pattern_name,
                phase, current_price, current_vol, round(change, 2), round(current_low, 2), round(current_high, 2)
            ))
            conn2.commit()
            conn2.close()
        except Exception as e:
            print(f"Error computing IPO metrics for {ticker}: {e}")
            
    # Run in parallel
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as executor:
        executor.map(_update_single, listings)
        
    print("IPO metrics cache refreshed successfully.")