import os
import requests
import time
import json
import urllib.request
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import threading
from flask import Flask, jsonify, render_template, request
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
from fx_utils import fetch_usd_inr_rate



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
            volume                  REAL,
            change_pct              REAL,
            day_low                 REAL,
            day_high                REAL,
            is_blue_bar             INTEGER DEFAULT 0,
            is_green_bar            INTEGER DEFAULT 0,
            is_orange_bar           INTEGER DEFAULT 0,
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
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN is_blue_bar INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN is_green_bar INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN is_orange_bar INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
        
    # ---------- Episodic Pivot (EP) Tables ----------
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_bars (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            trade_date      TEXT NOT NULL,
            open            REAL,
            high            REAL,
            low             REAL,
            close           REAL,
            volume          INTEGER,
            delivery_qty    INTEGER,
            delivery_pct    REAL,
            turnover        REAL,
            prev_close      REAL,
            gap_pct         REAL,
            close_loc       REAL,
            atr_14          REAL,
            rel_volume_20   REAL,
            rel_volume_50   REAL,
            price_change_pct REAL,
            intraday_range_pct REAL,
            UNIQUE (symbol, exchange, trade_date)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_daily_bars_symbol_date ON daily_bars (symbol, trade_date DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_daily_bars_date ON daily_bars (trade_date DESC)')

    c.execute('''
        CREATE TABLE IF NOT EXISTS fundamentals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            result_date     TEXT NOT NULL,
            quarter         TEXT,
            revenue         REAL,
            revenue_yoy_pct REAL,
            revenue_qoq_pct REAL,
            net_profit      REAL,
            net_profit_yoy_pct REAL,
            ebitda          REAL,
            ebitda_margin   REAL,
            eps             REAL,
            eps_yoy_pct     REAL,
            guidance_text   TEXT,
            surprise_type   TEXT,
            consecutive_quarters_growth INTEGER,
            source          TEXT,
            UNIQUE (symbol, exchange, quarter)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS corporate_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            event_date      TEXT NOT NULL,
            event_type      TEXT,
            headline        TEXT,
            sentiment       INTEGER,
            catalyst_score  REAL,
            source          TEXT,
            raw_url         TEXT
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_corp_events_symbol_date ON corporate_events (symbol, event_date DESC)')

    c.execute('''
        CREATE TABLE IF NOT EXISTS ep_features (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            feature_date    TEXT NOT NULL,
            perf_3m         REAL,
            perf_6m         REAL,
            range_60d_pct   REAL,
            avg_vol_rank    REAL,
            neglect_score   REAL,
            has_result      INTEGER DEFAULT 0,
            revenue_growth  REAL,
            profit_growth   REAL,
            has_corp_event  INTEGER DEFAULT 0,
            event_type      TEXT,
            catalyst_score  REAL,
            gap_pct         REAL,
            rel_volume      REAL,
            close_loc       REAL,
            repricing_score REAL,
            ep_score        REAL,
            ep_type         TEXT,
            confidence      TEXT,
            market_cap_cr   REAL,
            avg_turnover_cr REAL,
            float_days      REAL,
            UNIQUE (symbol, exchange, feature_date)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ep_features_date ON ep_features (feature_date DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ep_features_score ON ep_features (feature_date DESC, ep_score DESC)')

    c.execute('''
        CREATE TABLE IF NOT EXISTS ep_watchlist (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            catalyst_date   TEXT NOT NULL,
            ep_type         TEXT NOT NULL,
            status          TEXT DEFAULT 'ACTIVE',
            trigger_type    TEXT,
            entry_price     REAL,
            stop_price      REAL,
            target_price    REAL,
            entry_date      TEXT,
            days_on_watch   INTEGER DEFAULT 0,
            notes           TEXT,
            ep_score        REAL,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS sugar_babies (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT UNIQUE NOT NULL,
            exchange        TEXT NOT NULL,
            added_date      TEXT,
            avg_burst_pct   REAL,
            avg_burst_days  REAL,
            episode_count   INTEGER,
            notes           TEXT,
            is_active       INTEGER DEFAULT 1
        )
    ''')
    
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
    Only inserts mainboard (non-SME) listings from the last 18 months.
    Falls back to _IPO_MOCK_FALLBACK if the live fetch fails.
    """
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=548)

    conn = sqlite3.connect('scan_history.db')
    c = conn.cursor()
    # Remove stale entries older than 18 months
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

                # Only last 18 months
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
        print(f"[IPO Seed] Inserted {live_inserted} mainboard IPOs (last 18 months) from NSE live feed.")

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


# ---------- Episodic Pivot (EP) Scoring Helpers ----------

def compute_neglect_score(perf_3m, perf_6m, range_60d_pct, avg_vol_rank):
    """
    All inputs normalized/scaled between 0 and 1.
    Higher score indicates greater neglect. Handles None inputs dynamically.
    """
    n_perf_3m = max(0.0, min(1.0, (0.0 - perf_3m) / 40.0 + 0.5)) if perf_3m is not None else None
    n_perf_6m = max(0.0, min(1.0, (0.0 - perf_6m) / 60.0 + 0.5)) if perf_6m is not None else None
    n_range = max(0.0, min(1.0, 1.0 - (range_60d_pct / 40.0))) if range_60d_pct is not None else None
    n_vol_rank = max(0.0, min(1.0, 1.0 - avg_vol_rank)) if avg_vol_rank is not None else None

    weights = []
    vals = []
    if n_perf_3m is not None:
        weights.append(0.35)
        vals.append(n_perf_3m)
    if n_perf_6m is not None:
        weights.append(0.25)
        vals.append(n_perf_6m)
    if n_range is not None:
        weights.append(0.20)
        vals.append(n_range)
    if n_vol_rank is not None:
        weights.append(0.20)
        vals.append(n_vol_rank)

    if not weights:
        return 0.5

    total_w = sum(weights)
    neglect = sum(v * w for v, w in zip(vals, weights)) / total_w
    return round(neglect, 3)


EP_CATALYST_BASE = {
    "BLOWOUT_EARNINGS":  0.90,   # Revenue + profit both 100%+ YoY
    "STRONG_BEAT":       0.70,   # Revenue 40–100% YoY
    "TURNAROUND":        0.80,   # Profit swings from loss to strong profit
    "ORDER_WIN":         0.65,   # Major order announcement (>30% of mktcap)
    "MGMT_CHANGE":       0.55,   # New CEO / promoter buyback
    "THEME_CATALYST":    0.50,   # Government policy, PLI, sector tailwind
    "CAPEX_EXPANSION":   0.45,
    "ABNORMAL_VOLUME":   0.60,   # Volume EP / 9M equivalent (no news yet)
    "GUIDANCE_CUT":     -0.80,   # Negative catalyst (Short EP)
    "FRAUD_CONCERN":    -0.90,
    "UNKNOWN":           0.20,
}


def compute_catalyst_score(event_type, revenue_growth, profit_growth,
                           consecutive_quarters=0, market_cap_cr=None):
    base = EP_CATALYST_BASE.get(event_type, 0.20)
    if base < 0:  # Short EP — return negative value for separation
        return round(base, 3)

    bonus = 0.0
    if revenue_growth and revenue_growth >= 100:
        bonus += 0.10
    elif revenue_growth and revenue_growth >= 50:
        bonus += 0.05

    if profit_growth and profit_growth >= 200:
        bonus += 0.10
    elif profit_growth and profit_growth >= 100:
        bonus += 0.05

    if consecutive_quarters and consecutive_quarters >= 2:
        bonus += 0.05

    if market_cap_cr and market_cap_cr < 5000:
        bonus += 0.05

    return round(min(1.0, base + bonus), 3)


def compute_repricing_score(gap_pct, rel_volume, close_loc, price_change_pct,
                            intraday_range_pct):
    # Gap component: 5% gap -> 0.25; 20% gap -> 1.0
    n_gap = max(0.0, min(1.0, gap_pct / 20.0))

    # Volume confirmation: 3x normal -> 0.222; 10x -> 1.0
    n_vol = max(0.0, min(1.0, (rel_volume - 1.0) / 9.0))

    # Close location: closing near high is a bull signal
    n_close = max(0.0, min(1.0, close_loc))

    # Overall day strength
    n_strength = max(0.0, min(1.0, price_change_pct / 15.0))

    repricing = (0.30 * n_gap +
                 0.35 * n_vol +
                 0.20 * n_close +
                 0.15 * n_strength)
    return round(repricing, 3)


def compute_ep_score(neglect_score, catalyst_score, repricing_score,
                     liquidity_ok=True):
    raw = (0.25 * neglect_score +
           0.35 * abs(catalyst_score) +
           0.30 * repricing_score)

    # Small liquidity penalty if stock is too illiquid
    liquidity_adj = 0.0 if liquidity_ok else -0.10

    ep_score = round(max(0.0, min(1.0, raw + liquidity_adj)), 3)
    return ep_score


def assign_ep_type(catalyst_score, event_type, rel_volume, gap_pct,
                   revenue_growth=0, profit_growth=0, day1_messy=False,
                   is_negative_catalyst=False):
    if is_negative_catalyst or catalyst_score < 0:
        return "Short EP"
    if event_type in ("ABNORMAL_VOLUME", "UNKNOWN"):
        return "Volume EP"
    if day1_messy:
        return "Delayed EP"
    if event_type in ("BLOWOUT_EARNINGS", "STRONG_BEAT", "BEAT") and revenue_growth >= 100:
        return "Growth EP"
    if event_type == "TURNAROUND":
        return "Turnaround EP"
    if event_type in ("THEME_CATALYST", "ORDER_WIN", "MGMT_CHANGE", "CAPEX_EXPANSION"):
        return "Story EP"
    if event_type in ("BLOWOUT_EARNINGS", "STRONG_BEAT", "BEAT", "MISS"):
        return "Growth EP"
    return "Growth EP"


def assign_confidence(ep_score, neglect_score, catalyst_score, repricing_score):
    if ep_score >= 0.72 and catalyst_score >= 0.70 and repricing_score >= 0.60:
        return "HIGH"
    if ep_score >= 0.55:
        return "MEDIUM"
    return "LOW"


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
            history = fetch_historical_prices(ticker, range_str="2y")
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
            
            # Calculate volume indicators
            # 50-period Volume SMA
            vols = [float(h["volume"]) for h in history if h.get("volume") is not None]
            if len(vols) >= 50:
                volume_sma_50 = sum(vols[-50:]) / 50.0
            elif vols:
                volume_sma_50 = sum(vols) / len(vols)
            else:
                volume_sma_50 = 0.0

            # Highest down-day volume of the last 10 down-days
            down_day_vols = []
            for i in range(1, len(history)):
                current_close = float(history[i]["close"])
                prev_close = float(history[i-1]["close"])
                if current_close < prev_close:
                    down_day_vols.append(float(history[i]["volume"]))
            
            if len(down_day_vols) >= 10:
                max_down_vol_10 = max(down_day_vols[-10:])
            elif down_day_vols:
                max_down_vol_10 = max(down_day_vols)
            else:
                max_down_vol_10 = 0.0

            # Determine bar flags
            is_up_day = closes[-1] > closes[-2] if len(closes) >= 2 else False
            is_blue = 1 if (is_up_day and max_down_vol_10 > 0 and current_vol > max_down_vol_10) else 0
            is_green = 1 if (is_up_day and volume_sma_50 > 0 and current_vol > volume_sma_50 and not is_blue) else 0
            is_orange = 1 if (volume_sma_50 > 0 and current_vol <= volume_sma_50 / 5.0) else 0

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
                    momentum_phase, current_price, volume, change_pct, day_low, day_high,
                    is_blue_bar, is_green_bar, is_orange_bar, cached_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (
                ticker, company_name, listing_date, exchange, sector, issue_price,
                round(listing_gain_pct, 2), round(current_vs_issue_pct, 2), round(current_vs_listing_pct, 2), days_since,
                round(rvol_ratio, 2), above_listing_high, round(drawdown_from_ath, 2), swing_score, pattern_name,
                phase, current_price, current_vol, round(change, 2), round(current_low, 2), round(current_high, 2),
                is_blue, is_green, is_orange
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


def fetch_screener_fundamentals(symbol):
    """
    Scrapes quarterly results from screener.in for a given symbol.
    # FRAGILE: screener.in HTML structure
    # TODO: Phase 3 — add EBITDA row scraping
    """
    import urllib.request
    import re
    url = f"https://www.screener.in/company/{symbol}/"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
        
        # 1. Find the quarters table
        quarters_match = re.search(r'id=["\']quarters["\']', content)
        if not quarters_match:
            return []
        start_idx = quarters_match.start()
        table_start = content.find('<table', start_idx)
        table_end = content.find('</table>', table_start)
        if table_start == -1 or table_end == -1:
            return []
        table_html = content[table_start:table_end+8]
        
        # 2. Parse headers to get quarters and data-date-keys
        thead_match = re.search(r'<thead.*?>(.*?)</thead>', table_html, re.DOTALL)
        if not thead_match:
            return []
        thead_html = thead_match.group(1)
        th_matches = re.finditer(r'<th\b[^>]*data-date-key=["\'](.*?)["\'][^>]*>(.*?)</th>', thead_html, re.DOTALL)
        quarters = []
        for m in th_matches:
            date_key = m.group(1).strip()
            q_name = re.sub(r'<.*?>', '', m.group(2)).strip()
            quarters.append({"quarter": q_name, "date_key": date_key})
        # FRAGILE: screener.in HTML structure version check
        if len(quarters) == 0:
            print(f"[Warning] Parsed 0 quarters from screener.in for {symbol}. The HTML structure might have changed.")
            
        # 3. Parse rows in tbody
        tbody_match = re.search(r'<tbody.*?>(.*?)</tbody>', table_html, re.DOTALL)
        if not tbody_match:
            return []
        tbody_html = tbody_match.group(1)
        rows = re.findall(r'<tr.*?>.*?</tr>', tbody_html, re.DOTALL)
        
        revenue_row = None
        net_profit_row = None
        eps_row = None
        
        for r in rows:
            td_name_match = re.search(r'<td class="text".*?>(.*?)</td>', r, re.DOTALL)
            if not td_name_match:
                continue
            name_text = re.sub(r'<.*?>', '', td_name_match.group(1)).strip().lower()
            
            # Extract values
            td_all = re.findall(r'<td.*?>.*?</td>', r, re.DOTALL)
            val_tds = td_all[1:]
            vals = []
            for v in val_tds:
                v_clean = re.sub(r'<.*?>', '', v).replace('&nbsp;', '').strip()
                v_val = None
                if v_clean and v_clean not in ('-', ''):
                    try:
                        is_neg = False
                        if v_clean.startswith('(') and v_clean.endswith(')'):
                            is_neg = True
                            v_clean = v_clean[1:-1]
                        v_val = float(v_clean.replace(',', ''))
                        if is_neg:
                            v_val = -v_val
                    except ValueError:
                        pass
                vals.append(v_val)
                
            if any(x in name_text for x in ('sales', 'revenue', 'interest earned')):
                revenue_row = vals
            elif any(x in name_text for x in ('net profit', 'profit after tax')):
                net_profit_row = vals
            elif 'eps' in name_text:
                eps_row = vals
                
        # Assemble list of quarters
        fundamentals_list = []
        for idx, q in enumerate(quarters):
            rev = revenue_row[idx] if revenue_row and idx < len(revenue_row) else None
            prof = net_profit_row[idx] if net_profit_row and idx < len(net_profit_row) else None
            eps_val = eps_row[idx] if eps_row and idx < len(eps_row) else None
            
            fundamentals_list.append({
                "quarter": q["quarter"],
                "date_key": q["date_key"],
                "revenue": rev,
                "net_profit": prof,
                "eps": eps_val
            })
        return fundamentals_list
    except Exception as e:
        print(f"[EP Ingest] Failed to fetch/parse screener.in for {symbol}: {e}")
        return []


def compute_yoy_metrics(quarters_data):
    """
    Computes YoY metrics, consecutive quarters of growth, and surprise types.
    Note: quarters_data is ordered oldest-first (from left-to-right on screener.in columns),
    so i - 4 correctly points to the corresponding quarter from one year (4 quarters) ago.
    """
    for i in range(len(quarters_data)):
        q = quarters_data[i]
        if i >= 4:
            prev_q = quarters_data[i - 4]
            if q["revenue"] is not None and prev_q["revenue"] and prev_q["revenue"] > 0:
                q["revenue_yoy_pct"] = round((q["revenue"] - prev_q["revenue"]) / prev_q["revenue"] * 100, 2)
            else:
                q["revenue_yoy_pct"] = None
                
            if q["net_profit"] is not None and prev_q["net_profit"] and prev_q["net_profit"] > 0:
                q["net_profit_yoy_pct"] = round((q["net_profit"] - prev_q["net_profit"]) / prev_q["net_profit"] * 100, 2)
            else:
                q["net_profit_yoy_pct"] = None
                
            if q["eps"] is not None and prev_q["eps"] and prev_q["eps"] > 0:
                q["eps_yoy_pct"] = round((q["eps"] - prev_q["eps"]) / prev_q["eps"] * 100, 2)
            else:
                q["eps_yoy_pct"] = None
        else:
            q["revenue_yoy_pct"] = None
            q["net_profit_yoy_pct"] = None
            q["eps_yoy_pct"] = None
            
    for i in range(len(quarters_data)):
        consec = 0
        idx = i
        while idx >= 0:
            q_idx = quarters_data[idx]
            if q_idx["revenue_yoy_pct"] is not None and q_idx["net_profit_yoy_pct"] is not None:
                if q_idx["revenue_yoy_pct"] > 0 and q_idx["net_profit_yoy_pct"] > 0:
                    consec += 1
                    idx -= 1
                    continue
            break
        quarters_data[i]["consecutive_quarters_growth"] = consec
        
        q_rev_yoy = quarters_data[i]["revenue_yoy_pct"]
        q_prof_yoy = quarters_data[i]["net_profit_yoy_pct"]
        q_profit = quarters_data[i]["net_profit"]
        prev_profit = quarters_data[i-4]["net_profit"] if i >= 4 else None
        
        # TODO: Phase 3 refinement — blowout turnaround detection.
        # Currently, if prev_profit < 0, q_prof_yoy is None, meaning a blowout from a negative profit base
        # is classified as TURNAROUND. We can calculate YoY percentage growth using absolute base values:
        # e.g., (q_profit - prev_profit) / abs(prev_profit) * 100 to allow BLOWOUT_EARNINGS classification.
        surprise = "UNKNOWN"
        if q_rev_yoy is not None:
            if q_prof_yoy is not None and q_rev_yoy >= 100 and q_prof_yoy >= 100:
                surprise = "BLOWOUT_EARNINGS"
            elif prev_profit is not None and prev_profit < 0 and q_profit is not None and q_profit > 0:
                surprise = "TURNAROUND"
            elif q_prof_yoy is not None and q_rev_yoy >= 40:
                surprise = "STRONG_BEAT"
            elif q_prof_yoy is not None and (q_rev_yoy < 0 or q_prof_yoy < 0):
                surprise = "MISS"
            elif q_prof_yoy is not None:
                surprise = "BEAT"
        quarters_data[i]["surprise_type"] = surprise
        
    return quarters_data

def send_telegram_alert(message):
    """
    Sends a notification message to the configured Telegram chat/channel.
    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from environment variables.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            headers = {"Content-Type": "application/json"}
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                response.read()
            print(f"[Telegram Alert] Sent successfully: {message}")
        except Exception as e:
            print(f"[Telegram Alert] Failed to send: {e}")
    else:
        print(f"[Telegram Alert Log (Mock)] {message}")


def fetch_nse_delivery_data(date_str):
    """
    date_str in YYYY-MM-DD format.
    Downloads the delivery archives data from nseindia.
    """
    import urllib.request
    import csv
    import io
    
    try:
        parts = date_str.split('-')
        if len(parts) != 3:
            return {}
        ddmmyyyy = f"{parts[2]}{parts[1]}{parts[0]}"
        url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            
        reader = csv.reader(io.StringIO(content))
        header = next(reader)
        header = [h.strip() for h in header]
        
        try:
            symbol_idx = header.index("SYMBOL")
            deliv_qty_idx = header.index("DELIV_QTY")
            deliv_per_idx = header.index("DELIV_PER")
        except ValueError:
            print("[EP Ingest] Delivery columns not found in Bhav Copy header")
            return {}
            
        delivery_map = {}
        for row in reader:
            if not row or len(row) <= max(symbol_idx, deliv_qty_idx, deliv_per_idx):
                continue
            sym = row[symbol_idx].strip().upper()
            deliv_qty = row[deliv_qty_idx].strip()
            deliv_per = row[deliv_per_idx].strip()
            
            try:
                dq = int(deliv_qty)
                dp = float(deliv_per)
                delivery_map[sym] = (dq, dp)
            except ValueError:
                continue
        print(f"[EP Ingest] Successfully loaded delivery data for {len(delivery_map)} symbols.")
        return delivery_map
    except Exception as e:
        print(f"[EP Ingest] Failed to fetch delivery data for {date_str}: {e}")
        return {}


def refresh_ep_screener():
    """
    Computes EOD Episodic Pivot (EP) features and updates database tables.
    """
    import requests
    import bisect
    import time
    
    telegram_alerts_queue = []
    
    # 1. Fetch TV universe (market cap >= 50 Cr)
    payload = {
        "filter": [
            {"left": "exchange", "operation": "equal", "right": "NSE"},
            {"left": "market_cap_basic", "operation": "greater", "right": 500000000}
        ],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": [
            "name", "description", "close", "change", "volume", "market_cap_basic", "average_volume", "sector"
        ],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [0, 5000]
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.tradingview.com/"
    }
    
    try:
        resp = requests.post(TRADINGVIEW_SCAN_URL, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        raw_data = resp.json().get("data", [])
    except Exception as e:
        print(f"[EP Refresh] Failed to fetch TV universe: {e}")
        return
        
    tv_stocks = []
    for item in raw_data:
        raw_ticker = item.get("s", "")
        exch = "BSE" if raw_ticker.startswith("BSE:") else "NSE"
        clean_ticker = raw_ticker.replace("NSE:", "").replace("BSE:", "")
        cols = item.get("d", [])
        if len(cols) == 8:
            tv_stocks.append({
                "ticker": clean_ticker,
                "exchange": exch,
                "name": cols[0],
                "description": cols[1],
                "close": cols[2] or 0.0,
                "change": cols[3] or 0.0,
                "volume": cols[4] or 0.0,
                "market_cap_basic": cols[5] or 0.0,
                "average_volume": cols[6] or 1.0,
                "sector": cols[7] or "Unknown"
            })
            
    # Calculate sector average volumes for ranking
    sector_vols = {}
    for s in tv_stocks:
        sect = s["sector"]
        avg_vol = float(s["average_volume"])
        if sect not in sector_vols:
            sector_vols[sect] = []
        sector_vols[sect].append(avg_vol)
        
    for sect in sector_vols:
        sector_vols[sect].sort()
        
    # 2. Filter for candidates: relative volume >= 3.0
    # Capture both positive EPs and potential Short EPs
    candidates = []
    for s in tv_stocks:
        vol = float(s["volume"])
        avg_vol = float(s["average_volume"])
        rel_vol = vol / avg_vol if avg_vol > 0 else 1.0
        
        if rel_vol >= 3.0:
            candidates.append((s, rel_vol))
            
    print(f"[EP Refresh] Found {len(candidates)} candidates out of {len(tv_stocks)} scanned.")
    
    # Limit to top 40 candidates to avoid rate-limiting
    candidates = sorted(candidates, key=lambda x: x[1], reverse=True)[:40]
    
    # Download latest Bhav Copy to get delivery data
    delivery_map = {}
    if candidates:
        first_s, _ = candidates[0]
        suffix = ".BO" if first_s['exchange'] == "BSE" else ".NS"
        first_ticker = f"{first_s['ticker']}{suffix}"
        try:
            first_hist = fetch_historical_prices(first_ticker, range_str="1d")
            if first_hist:
                feat_date = first_hist[-1]["date"]
                delivery_map = fetch_nse_delivery_data(feat_date)
        except Exception as e:
            print(f"[EP Refresh] Failed to fetch first candidate history to determine date: {e}")
            
    conn = sqlite3.connect('scan_history.db')
    c = conn.cursor()
    
    for s, rel_vol in candidates:
        suffix = ".BO" if s['exchange'] == "BSE" else ".NS"
        ticker = f"{s['ticker']}{suffix}"
        try:
            history = fetch_historical_prices(ticker, range_str="6mo")
            if not history or len(history) < 5:
                continue
                
            closes = [float(h["close"]) for h in history if h.get("close") is not None]
            highs = [float(h["high"]) for h in history if h.get("high") is not None]
            lows = [float(h["low"]) for h in history if h.get("low") is not None]
            volumes = [float(h["volume"]) for h in history if h.get("volume") is not None]
            
            if len(closes) < 5:
                continue
                
            # Pre-calculate ATR-14, 20-day average volume, 50-day average volume
            atr_14_list = [None] * len(history)
            avg_vol_20_list = [None] * len(history)
            avg_vol_50_list = [None] * len(history)
            
            tr_list = []
            for i in range(len(history)):
                if i == 0:
                    tr_list.append(highs[i] - lows[i])
                else:
                    tr_list.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
                    
            for i in range(len(history)):
                if i >= 13:
                    atr_14_list[i] = sum(tr_list[i-13:i+1]) / 14.0
                if i >= 19:
                    avg_vol_20_list[i] = sum(volumes[i-19:i+1]) / 20.0
                if i >= 49:
                    avg_vol_50_list[i] = sum(volumes[i-49:i+1]) / 50.0
            
            feature_date = history[-1]["date"]
            
            # Save daily bars
            for i in range(1, len(history)):
                bar = history[i]
                prev_bar = history[i-1]
                t_date = bar.get("date")
                if not t_date:
                    continue
                o = float(bar.get("open") or 0)
                h = float(bar.get("high") or 0)
                l = float(bar.get("low") or 0)
                col = float(bar.get("close") or 0)
                v = int(bar.get("volume") or 0)
                prev_c = float(prev_bar.get("close") or 0)
                gap = ((o - prev_c) / prev_c * 100) if prev_c else 0.0
                chg = ((col - prev_c) / prev_c * 100) if prev_c else 0.0
                close_loc = ((col - l) / (h - l)) if (h - l) > 0 else 1.0
                intra_range = ((h - l) / prev_c * 100) if prev_c else 0.0
                
                atr = atr_14_list[i]
                vol_20 = avg_vol_20_list[i]
                vol_50 = avg_vol_50_list[i]
                
                rel_vol_20 = v / vol_20 if (vol_20 and vol_20 > 0) else None
                rel_vol_50 = v / vol_50 if (vol_50 and vol_50 > 0) else None
                
                dq = None
                dp = None
                if t_date == feature_date:
                    dq, dp = delivery_map.get(s['ticker'].upper(), (None, None))
                
                c.execute('''
                    INSERT OR REPLACE INTO daily_bars (
                        symbol, exchange, trade_date, open, high, low, close, volume,
                        prev_close, gap_pct, close_loc, price_change_pct, intraday_range_pct,
                        atr_14, rel_volume_20, rel_volume_50, delivery_qty, delivery_pct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    s['ticker'], s['exchange'], t_date, o, h, l, col, v,
                    prev_c, round(gap, 3), round(close_loc, 3), round(chg, 3), round(intra_range, 3),
                    round(atr, 4) if atr else None,
                    round(rel_vol_20, 3) if rel_vol_20 else None,
                    round(rel_vol_50, 3) if rel_vol_50 else None,
                    dq, dp
                ))

            # Ingest Fundamentals & YoY metrics
            quarters_data = fetch_screener_fundamentals(s['ticker'])
            if quarters_data:
                quarters_data = compute_yoy_metrics(quarters_data)
                for q in quarters_data:
                    c.execute('''
                        INSERT OR REPLACE INTO fundamentals (
                            symbol, exchange, result_date, quarter, revenue, revenue_yoy_pct,
                            net_profit, net_profit_yoy_pct, eps, eps_yoy_pct, surprise_type,
                            consecutive_quarters_growth, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        s['ticker'], s['exchange'], q['date_key'], q['quarter'], q['revenue'], q['revenue_yoy_pct'],
                        q['net_profit'], q['net_profit_yoy_pct'], q['eps'], q['eps_yoy_pct'], q['surprise_type'],
                        q['consecutive_quarters_growth'], 'screener.in'
                    ))

            # Ingest Announcements (NSE only)
            from datetime import datetime, timedelta
            seven_days_ago = datetime.now() - timedelta(days=7)
            
            if s['exchange'] == "NSE":
                announcements = fetch_nse_announcements(s['ticker'])
                if isinstance(announcements, list):
                    for item in announcements:
                        sort_date_str = item.get("sort_date")
                        if not sort_date_str:
                            continue
                        try:
                            dt = datetime.strptime(sort_date_str, "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            continue
                        
                        if dt >= seven_days_ago:
                            desc = item.get("desc", "")
                            text = item.get("attchmntText", "")
                            cat, cat_name, imp, imp_name, sent, sent_name, reason = classify_announcement(desc, text)
                            
                            # Map cat to event_type
                            if cat == "cat-order-win":
                                event_type_mapped = "ORDER_WIN"
                            elif cat == "cat-capex":
                                event_type_mapped = "CAPEX_EXPANSION"
                            elif cat == "cat-governance":
                                event_type_mapped = "MGMT_CHANGE"
                            elif cat == "cat-regulatory":
                                event_type_mapped = "FRAUD_CONCERN"
                            else:
                                event_type_mapped = "UNKNOWN"
                                
                            sent_val = 0
                            if "positive" in sent.lower():
                                sent_val = 1
                            elif "negative" in sent.lower():
                                sent_val = -1
                                
                            cat_score = EP_CATALYST_BASE.get(event_type_mapped, 0.20)
                            
                            an_dt = item.get("an_dt", "")
                            date_str = an_dt.split(" ")[0] if " " in an_dt else an_dt
                            
                            # Deduplicate insertion
                            c.execute('''
                                SELECT id FROM corporate_events
                                WHERE symbol = ? AND event_date = ? AND headline = ?
                            ''', (s['ticker'], date_str, desc if desc else text[:200]))
                            if not c.fetchone():
                                c.execute('''
                                    INSERT INTO corporate_events (
                                        symbol, exchange, event_date, event_type, headline, sentiment,
                                        catalyst_score, source, raw_url
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (
                                    s['ticker'], s['exchange'], date_str, event_type_mapped,
                                    desc if desc else text[:200], sent_val, cat_score, 'NSE',
                                    item.get("attchmntFile", "")
                                ))

            # Retrieve latest fundamentals
            c.execute('''
                SELECT revenue_yoy_pct, net_profit_yoy_pct, consecutive_quarters_growth, surprise_type, net_profit
                FROM fundamentals
                WHERE symbol = ? AND exchange = ?
                ORDER BY result_date DESC, id DESC
                LIMIT 1
            ''', (s['ticker'], s['exchange']))
            fund = c.fetchone()
            
            if fund:
                has_result = 1
                revenue_growth = fund[0] if fund[0] is not None else 0.0
                profit_growth = fund[1] if fund[1] is not None else 0.0
                consec_growth = fund[2] if fund[2] is not None else 0
                surprise_type = fund[3] or "UNKNOWN"
            else:
                has_result = 0
                revenue_growth = 0.0
                profit_growth = 0.0
                consec_growth = 0
                surprise_type = "UNKNOWN"
                
            # Retrieve latest event from last 7 days relative to feature_date
            feat_dt = datetime.strptime(feature_date, "%Y-%m-%d")
            seven_days_before_feat = (feat_dt - timedelta(days=7)).strftime("%Y-%m-%d")
            
            c.execute('''
                SELECT event_type, catalyst_score
                FROM corporate_events
                WHERE symbol = ? AND event_date >= ? AND event_date <= ?
                ORDER BY event_date DESC, id DESC
                LIMIT 1
            ''', (s['ticker'], seven_days_before_feat, feature_date))
            evt = c.fetchone()
            
            if evt:
                has_corp_event = 1
                corp_event_type = evt[0]
            else:
                has_corp_event = 0
                corp_event_type = None
                
            # Resolve event type
            resolved_event_type = "ABNORMAL_VOLUME"
            if corp_event_type and corp_event_type != "UNKNOWN":
                resolved_event_type = corp_event_type
            elif surprise_type and surprise_type != "UNKNOWN":
                resolved_event_type = surprise_type

            # Calculate Neglect metrics
            # 3m return (requires 63 trading days)
            perf_3m = ((closes[-1] - closes[-63]) / closes[-63] * 100) if len(closes) >= 63 else None
            # 6m return (requires 126 trading days)
            perf_6m = ((closes[-1] - closes[-126]) / closes[-126] * 100) if len(closes) >= 126 else None
            
            last_60 = closes[-60:]
            range_60d_pct = (max(last_60) - min(last_60)) / (sum(last_60) / len(last_60)) * 100 if last_60 else 0.0
            
            # Volume rank
            sect = s["sector"]
            avg_vol = float(s["average_volume"])
            vols = sector_vols.get(sect, [])
            if len(vols) > 1:
                rank_idx = bisect.bisect_left(vols, avg_vol)
                avg_vol_rank = rank_idx / (len(vols) - 1)
            else:
                avg_vol_rank = 0.5
                
            if len(closes) < 63:
                # IPO guard: fresh listings (< 3 months history) are not neglected
                neglect_score = 0.20
            else:
                neglect_score = compute_neglect_score(perf_3m, perf_6m, range_60d_pct, avg_vol_rank)
            
            # Calculate Catalyst metrics
            # NOTE: scanner.tradingview.com/india/scan returns market_cap_basic in INR already.
            # Do NOT multiply by a USD→INR rate — that was a ~84x inflation bug.
            # fetch_usd_inr_rate() is available (from fx_utils) for any future global-scanner queries.
            mktcap_cr = float(s["market_cap_basic"]) / 10_000_000  # INR → INR Crores
            catalyst_score = compute_catalyst_score(
                event_type=resolved_event_type,
                revenue_growth=revenue_growth,
                profit_growth=profit_growth,
                consecutive_quarters=consec_growth,
                market_cap_cr=mktcap_cr
            )
            
            # Calculate Repricing metrics
            yesterday_close = closes[-2] if len(closes) >= 2 else closes[0]
            today_close = closes[-1]
            today_open = float(history[-1].get("open") or today_close)
            today_high = highs[-1]
            today_low = lows[-1]
            today_vol = volumes[-1]
            
            gap_pct = ((today_open - yesterday_close) / yesterday_close * 100) if yesterday_close else 0.0
            close_loc = ((today_close - today_low) / (today_high - today_low)) if (today_high - today_low) > 0 else 1.0
            price_change_pct = ((today_close - yesterday_close) / yesterday_close * 100) if yesterday_close else 0.0
            intraday_range_pct = ((today_high - today_low) / yesterday_close * 100) if yesterday_close else 0.0
            
            # Recalculate rel_volume_20 dynamically using avg_vol_20_list
            avg_vol_20 = avg_vol_20_list[-1] if avg_vol_20_list[-1] else (sum(volumes) / len(volumes))
            dyn_rel_vol = today_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0
            
            repricing_score = compute_repricing_score(gap_pct, dyn_rel_vol, close_loc, price_change_pct, intraday_range_pct)
            
            # Liquidity check
            eod_turnover_cr = (today_close * today_vol) / 10000000
            liquidity_ok = (
                eod_turnover_cr >= 5.0        # minimum ₹5 Cr daily turnover
                and mktcap_cr >= 200.0         # minimum ₹200 Cr market cap
            )
            
            ep_score = compute_ep_score(neglect_score, catalyst_score, repricing_score, liquidity_ok)
            ep_type = assign_ep_type(
                catalyst_score=catalyst_score,
                event_type=resolved_event_type,
                rel_volume=dyn_rel_vol,
                gap_pct=gap_pct,
                revenue_growth=revenue_growth,
                profit_growth=profit_growth
            )
            confidence = assign_confidence(ep_score, neglect_score, catalyst_score, repricing_score)
            
            c.execute('''
                INSERT OR REPLACE INTO ep_features (
                    symbol, exchange, feature_date, perf_3m, perf_6m, range_60d_pct, avg_vol_rank,
                    neglect_score, has_result, revenue_growth, profit_growth, has_corp_event,
                    event_type, catalyst_score, gap_pct, rel_volume, close_loc, repricing_score,
                    ep_score, ep_type, confidence, market_cap_cr, avg_turnover_cr, float_days
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0)
            ''', (
                s['ticker'], s['exchange'], feature_date, 
                round(perf_3m, 3) if perf_3m is not None else None, 
                round(perf_6m, 3) if perf_6m is not None else None, 
                round(range_60d_pct, 3), round(avg_vol_rank, 3),
                neglect_score,
                has_result,
                round(revenue_growth, 3) if revenue_growth is not None else 0.0,
                round(profit_growth, 3) if profit_growth is not None else 0.0,
                has_corp_event,
                resolved_event_type,
                catalyst_score,
                round(gap_pct, 3),
                round(dyn_rel_vol, 3),
                round(close_loc, 3),
                repricing_score,
                ep_score,
                ep_type,
                confidence,
                round(mktcap_cr, 2),
                round(avg_vol_20 * today_close / 10000000, 2)
            ))
            
            # Watchlist addition if EP score >= 0.55
            if ep_score >= 0.55:
                c.execute("SELECT id FROM ep_watchlist WHERE symbol = ? AND status = 'ACTIVE'", (s['ticker'],))
                existing = c.fetchone()
                if existing:
                    c.execute('''
                        UPDATE ep_watchlist
                        SET ep_score = ?, entry_price = ?, stop_price = ?, catalyst_date = ?, ep_type = ?
                        WHERE id = ?
                    ''', (ep_score, today_close, today_low, feature_date, ep_type, existing[0]))
                else:
                    c.execute('''
                        INSERT INTO ep_watchlist (
                            symbol, exchange, catalyst_date, ep_type, status, ep_score, entry_price, stop_price
                        ) VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                    ''', (
                        s['ticker'], s['exchange'], feature_date, ep_type, ep_score, today_close, today_low
                    ))
                
                # Send alert for new HIGH confidence candidates
                if confidence == "HIGH" and ep_score >= 0.55:
                    alert_msg = (
                        f"🚀 <b>New HIGH Confidence EP Detected!</b>\n"
                        f"<b>Symbol:</b> {s['ticker']}\n"
                        f"<b>Type:</b> {ep_type}\n"
                        f"<b>Score:</b> {ep_score:.2f}\n"
                        f"<b>Exchange:</b> {s['exchange']}\n"
                        f"<b>Close:</b> ₹{today_close:.2f}\n"
                        f"<b>Rel Volume:</b> {dyn_rel_vol:.1f}x"
                    )
                    telegram_alerts_queue.append(alert_msg)
                
        except Exception as e:
            print(f"Error computing EP features for {ticker}: {e}")
            import traceback; traceback.print_exc()
            
    # Nightly Delayed EP Trigger Checking
    try:
        c.execute("""
            SELECT id, symbol, exchange, catalyst_date, ep_type, ep_score, entry_price
            FROM ep_watchlist WHERE status = 'ACTIVE'
        """)
        active_watchlist = c.fetchall()
        for row in active_watchlist:
            w_id, symbol, exchange, catalyst_date, ep_type, ep_score, catalyst_close = row
            ticker_full = f"{symbol}.NS" if exchange == "NSE" else f"{symbol}.BO"
            try:
                history_data = fetch_historical_prices(ticker_full, range_str="6mo")
                if history_data and len(history_data) >= 21:
                    today_bar = history_data[-1]
                    if catalyst_date == today_bar["date"]:
                        continue
                    prev_bar = history_data[-2]
                    
                    today_close = today_bar["close"]
                    today_open = today_bar["open"]
                    today_high = today_bar["high"]
                    today_low = today_bar["low"]
                    today_vol = today_bar["volume"]
                    prev_close = prev_bar["close"]
                    
                    volumes_data = [h["volume"] for h in history_data]
                    avg_vol_20_val = sum(volumes_data[-21:-1]) / 20.0
                    rel_volume_20_val = today_vol / avg_vol_20_val if avg_vol_20_val > 0 else 1.0
                    
                    trigger_type = None
                    if ep_type == "Short EP":
                        if today_close < prev_close and rel_volume_20_val >= 1.2:
                            trigger_type = "FAILED_BOUNCE"
                    else:
                        # 1. Red-to-Green (RTG)
                        rtg_triggered = (today_open < prev_close and today_close > prev_close and rel_volume_20_val >= 1.5)
                        
                        # 2. Tight Range Breakout
                        tight_breakout_triggered = False
                        if len(history_data) >= 6:
                            prev_5_closes = [h["close"] for h in history_data[-6:-1]]
                            prev_5_sum = sum(prev_5_closes)
                            five_day_range = 0.0
                            if prev_5_sum > 0:
                                five_day_range = (max(prev_5_closes) - min(prev_5_closes)) / (prev_5_sum / 5.0) * 100
                            prev_5_highs = [h["high"] for h in history_data[-6:-1]]
                            five_day_high = max(prev_5_highs)
                            tight_breakout_triggered = (five_day_range < 8.0 and today_close > five_day_high and rel_volume_20_val >= 2.0)
                            
                        # 3. Level Reclaim
                        reclaim_triggered = (
                            catalyst_close is not None and
                            prev_close < catalyst_close and
                            today_close >= catalyst_close * 0.995 and
                            rel_volume_20_val >= 1.5
                        )
                        
                        if rtg_triggered:
                            trigger_type = "RED_TO_GREEN"
                        elif tight_breakout_triggered:
                            trigger_type = "RANGE_BREAKOUT"
                        elif reclaim_triggered:
                            trigger_type = "RECLAIM"
                            
                    if trigger_type:
                        c.execute("""
                            UPDATE ep_watchlist
                            SET status = 'TRIGGERED', trigger_type = ?, entry_price = ?, entry_date = ?, updated_at = datetime('now')
                            WHERE id = ?
                        """, (trigger_type, today_close, today_bar["date"], w_id))
                        
                        # Send alert for watchlist trigger
                        alert_msg = (
                            f"🔔 <b>EP Watchlist Triggered!</b>\n"
                            f"<b>Symbol:</b> {symbol}\n"
                            f"<b>Type:</b> {ep_type}\n"
                            f"<b>Trigger:</b> {trigger_type}\n"
                            f"<b>Price:</b> ₹{today_close:.2f}\n"
                            f"<b>Rel Volume:</b> {rel_volume_20_val:.1f}x\n"
                            f"<b>Original EP Score:</b> {ep_score:.2f}"
                        )
                        telegram_alerts_queue.append(alert_msg)
            except Exception as w_err:
                print(f"[EP Watchlist check] Error checking triggers for {symbol}: {w_err}")
    except Exception as list_err:
        print(f"[EP Watchlist check] Failed to fetch active watchlist: {list_err}")

    # Increment days_on_watch and expire older items in the active watchlist
    c.execute("UPDATE ep_watchlist SET days_on_watch = days_on_watch + 1 WHERE status = 'ACTIVE'")
    c.execute("UPDATE ep_watchlist SET status = 'EXPIRED' WHERE days_on_watch > 20 AND status = 'ACTIVE'")
    
    # Update episode_count nightly for all active Sugar Babies
    # TODO: update episode_count nightly
    try:
        c.execute("""
            UPDATE sugar_babies
            SET episode_count = (
                SELECT COUNT(*) FROM ep_features
                WHERE ep_features.symbol = sugar_babies.symbol AND ep_features.ep_score >= 0.55
            )
            WHERE is_active = 1
        """)
    except Exception as sb_err:
        print(f"[EP Sugar Babies Update] Failed to update episode counts: {sb_err}")
        
    conn.commit()
    conn.close()
    
    # Process batched Telegram alerts outside of db transaction
    if telegram_alerts_queue:
        print(f"[EP Refresh] Sending {len(telegram_alerts_queue)} batched Telegram alerts...")
        for alert_msg in telegram_alerts_queue:
            try:
                send_telegram_alert(alert_msg)
                time.sleep(0.2)
            except Exception as alert_err:
                print(f"[EP Refresh] Error sending queued alert: {alert_err}")
                
    print("[EP Refresh] EP screening and cache refresh completed.")

# Global lock to prevent concurrent NSE API fetches across threads
nse_fetch_lock = threading.Lock()

app = Flask(__name__, template_folder='templates', static_folder='static')

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response


TRADINGVIEW_SCAN_URL = "https://scanner.tradingview.com/india/scan"

# Confirmed columns that are valid in the TradingView Scanner API
COLUMNS = [
    "name",
    "description",
    "close",
    "change",
    "volume",
    "market_cap_basic",
    "price_52_week_low",
    "price_52_week_high",
    "average_volume",
    "SMA10",
    "SMA21",
    "SMA50",
    "ATR",
    "sector",
    "relative_volume_10d_calc",
    "Perf.W",
    "Perf.1M",
    "Perf.3M",
    "price_earnings_ttm",
    "enterprise_value_ebitda_ttm",
    "price_book_fq",
    "dividends_yield",
    "price_sales_ratio",
    "enterprise_value_fq",
    "gross_margin_ttm",
    "ebitda_margin_ttm",
    "debt_to_equity_fq",
    "net_income_ttm",
    "free_cash_flow_ttm",
    "free_cash_flow_fy",
    "net_income_fy",
    "return_on_equity_fq",
    "return_on_assets_fq",
    "return_on_capital_employed_fq",
    "high",
    "low",
    "high[1]",
    "low[1]",
    "EMA10",
    "EMA21",
    "EMA50",
    "open",
    "VWAP",
    "gap",
    "change_from_open",
    "Volatility.D",
    "Recommend.All",
    "RSI",
    "close[1]",
    "earnings_release_date",
    "earnings_release_next_date"
]

def compute_intraday_score(stock, deal_symbols=None):
    """Compute Intraday Momentum Score (0-10) based on gap, RVOL, VWAP, sector, liquidity, supply."""
    score = 0
    breakdown = []
    
    close = float(stock.get("close") or 0)
    open_price = float(stock.get("open") or 0)
    vwap = float(stock.get("VWAP") or 0)
    gap_pct = float(stock.get("gap") or 0)
    change_from_open = float(stock.get("change_from_open") or 0)
    rvol = float(stock.get("relative_volume") or stock.get("relative_volume_10d_calc") or 0)
    volatility_d = float(stock.get("Volatility.D") or 0)
    turnover_cr = float(stock.get("turnover_m") or 0)
    hi_52w = float(stock.get("price_52_week_high") or 0)
    ticker = stock.get("clean_ticker") or stock.get("name") or ""
    
    if deal_symbols is None:
        deal_symbols = set()
    
    # 1. Catalyst Present (2 points) - checked partially here (deals), announcements done on frontend
    has_deal = ticker.upper() in deal_symbols or ticker.split(":")[-1].upper() in deal_symbols
    if has_deal:
        score += 2
        breakdown.append("Bulk/Block Deal today (+2)")
    stock["has_deal_catalyst"] = has_deal
    
    # 2. RVOL Strong (2 points)
    if rvol >= 1.5:
        score += 2
        breakdown.append(f"RVOL strong: {rvol:.2f}x (+2)")
    elif rvol >= 1.0:
        score += 1
        breakdown.append(f"RVOL decent: {rvol:.2f}x (+1)")
    else:
        breakdown.append(f"RVOL weak: {rvol:.2f}x (+0)")
    
    # 3. Gap + Follow-through (2 points)
    abs_gap = abs(gap_pct)
    gap_and_follow = False
    if abs_gap >= 0.3:
        # Check if change_from_open direction matches gap direction
        if (gap_pct > 0 and change_from_open > 0) or (gap_pct < 0 and change_from_open < 0):
            score += 2
            direction = "up" if gap_pct > 0 else "down"
            breakdown.append(f"Gap {direction} {abs_gap:.2f}% + follow-through (+2)")
            gap_and_follow = True
        else:
            score += 1
            breakdown.append(f"Gap present {gap_pct:+.2f}% but fading (+1)")
    elif abs_gap >= 0.1:
        if (gap_pct > 0 and change_from_open > 0) or (gap_pct < 0 and change_from_open < 0):
            score += 1
            breakdown.append(f"Small gap {gap_pct:+.2f}% with follow-through (+1)")
        else:
            breakdown.append(f"Small gap {gap_pct:+.2f}%, no follow-through (+0)")
    else:
        breakdown.append(f"No meaningful gap {gap_pct:+.2f}% (+0)")
    
    # 4. VWAP Alignment (1 point)
    if close > 0 and vwap > 0:
        # Determine direction from gap/change
        is_bullish = change_from_open >= 0 or gap_pct > 0
        if is_bullish and close > vwap:
            score += 1
            pct_above = ((close - vwap) / vwap) * 100
            breakdown.append(f"Price above VWAP by {pct_above:.2f}% (+1)")
        elif not is_bullish and close < vwap:
            score += 1
            pct_below = ((vwap - close) / vwap) * 100
            breakdown.append(f"Price below VWAP by {pct_below:.2f}% (+1)")
        else:
            breakdown.append("VWAP not aligned with direction (+0)")
    else:
        breakdown.append("VWAP data unavailable (+0)")
    
    # 5. Sector/Index Aligned (1 point) - will be enhanced on frontend with sector scores
    breakdown.append("Sector alignment evaluating... (+0)")
    
    # 6. Liquidity Good (1 point)
    if turnover_cr > 10 and volatility_d <= 6:
        score += 1
        breakdown.append(f"Good liquidity: {turnover_cr:.0f} Cr turnover, {volatility_d:.1f}% vol (+1)")
    elif turnover_cr > 5:
        breakdown.append(f"Moderate liquidity: {turnover_cr:.0f} Cr turnover (+0)")
    else:
        breakdown.append(f"Low liquidity: {turnover_cr:.0f} Cr turnover (+0)")
    
    # 7. No Major Overhead Supply (1 point)
    if close > 0 and hi_52w > 0:
        pct_from_high = ((hi_52w - close) / close) * 100
        if pct_from_high <= 5:
            score += 1
            breakdown.append(f"Near 52W high ({pct_from_high:.1f}% away) - clean uptrend (+1)")
        elif pct_from_high >= 20:
            score += 1
            breakdown.append(f"Far from 52W high ({pct_from_high:.1f}% away) - no nearby ceiling (+1)")
        else:
            breakdown.append(f"Overhead supply {pct_from_high:.1f}% from 52W high (+0)")
    else:
        breakdown.append("52W high data unavailable (+0)")
    
    # Determine band
    if score >= 7:
        band = "strong"
    elif score >= 5:
        band = "moderate"
    else:
        band = "weak"
    
    stock["intraday_score"] = score
    stock["ims_band"] = band
    stock["ims_breakdown"] = breakdown
    return stock

def compute_swing_score(stock, top_sectors=None):
    """Compute Swing-Trading Score (0-10) based on trend, momentum, and volume."""
    score = 0
    breakdown = []
    
    close = float(stock.get("close") or 0)
    sma21 = float(stock.get("SMA21") or 0)
    sma50 = float(stock.get("SMA50") or 0)
    perf_1m = float(stock.get("Perf.1M") or 0)
    perf_3m = float(stock.get("Perf.3M") or 0)
    perf_w = float(stock.get("Perf.W") or 0)
    change = float(stock.get("change") or 0)
    rvol = float(stock.get("relative_volume") or stock.get("relative_volume_10d_calc") or 0)
    rsi = float(stock.get("RSI") or 0)
    hi_52w = float(stock.get("price_52_week_high") or 0)
    sector = stock.get("sector") or ""
    
    if top_sectors is None:
        top_sectors = []

    # 1. close > SMA21 (2 pts)
    if close > sma21 and sma21 > 0:
        score += 2
        breakdown.append("Price > 21 SMA (+2)")
    else:
        breakdown.append("Price < 21 SMA (+0)")

    # 2. SMA21 > SMA50 (1 pt)
    if sma21 > sma50 and sma50 > 0:
        score += 1
        breakdown.append("21 SMA > 50 SMA (+1)")
    else:
        breakdown.append("21 SMA < 50 SMA (+0)")

    # 3. Perf.1M > 0 (2 pts)
    if perf_1m > 0:
        score += 2
        breakdown.append(f"1M Perf Positive: {perf_1m:.2f}% (+2)")
    else:
        breakdown.append(f"1M Perf Negative: {perf_1m:.2f}% (+0)")

    # 4. Perf.3M > 0 (1 pt)
    if perf_3m > 0:
        score += 1
        breakdown.append(f"3M Perf Positive: {perf_3m:.2f}% (+1)")
    else:
        breakdown.append(f"3M Perf Negative: {perf_3m:.2f}% (+0)")

    # 5. relativevolume >= 1.2 (1 pt)
    if rvol >= 1.2:
        score += 1
        breakdown.append(f"RVOL strong: {rvol:.2f}x (+1)")
    else:
        breakdown.append(f"RVOL weak: {rvol:.2f}x (+0)")

    # 6. RSI between 55 and 72 (1 pt)
    if 55 <= rsi <= 72:
        score += 1
        breakdown.append(f"RSI in sweet spot: {rsi:.1f} (+1)")
    else:
        breakdown.append(f"RSI out of zone: {rsi:.1f} (+0)")

    # 7. close within 8% of price52weekhigh (1 pt)
    if hi_52w > 0:
        pct_from_high = ((hi_52w - close) / hi_52w) * 100
        if 0 <= pct_from_high <= 8:
            score += 1
            breakdown.append(f"Near 52W high: {pct_from_high:.1f}% away (+1)")
        else:
            breakdown.append(f"Far from 52W high: {pct_from_high:.1f}% away (+0)")
    else:
        breakdown.append("52W high unavailable (+0)")

    # 8. Sector in top 3 (1 pt)
    if sector and top_sectors and sector in top_sectors:
        score += 1
        breakdown.append(f"Sector '{sector}' is leading (+1)")
    else:
        breakdown.append("Sector alignment evaluating... (+0)")

    # 9. Bonus Perf.W > 0 AND change > 0 (0-1 pt)
    if perf_w > 0 and change > 0:
        score += 1
        breakdown.append(f"Bonus: 1W Perf & Today Positive (+1)")
        
    if score > 10:
        score = 10
            
    if score >= 8:
        band = "elite"
    elif score >= 6:
        band = "strong"
    elif score >= 4:
        band = "watch"
    else:
        band = "weak"

    stock["swingscore"] = score
    stock["swingband"] = band
    stock["swingbreakdown"] = breakdown
    return stock

def compute_mtf_confirmation(stock):
    perf_w = float(stock.get("Perf.W") or 0)
    perf_1m = float(stock.get("Perf.1M") or 0)
    perf_3m = float(stock.get("Perf.3M") or 0)
    sma21 = float(stock.get("SMA21") or 0)
    sma50 = float(stock.get("SMA50") or 0)
    
    weekly_bullish = (perf_w > 0) and (sma21 > sma50)
    monthly_bullish = (perf_1m > 0) and (perf_3m > 0)
    
    if weekly_bullish and monthly_bullish:
        stock["mtfScore"] = 2
        stock["mtfLabel"] = "Both"
    elif weekly_bullish:
        stock["mtfScore"] = 1
        stock["mtfLabel"] = "Weekly Only"
    elif monthly_bullish:
        stock["mtfScore"] = 1
        stock["mtfLabel"] = "Monthly Only"
    else:
        stock["mtfScore"] = 0
        stock["mtfLabel"] = "None"
        
    return stock


def check_ma_flirting(stock):
    price = float(stock.get("close") or 0)
    ma10 = float(stock.get("EMA10") if stock.get("EMA10") is not None else stock.get("SMA10") or 0)
    ma21 = float(stock.get("EMA21") if stock.get("EMA21") is not None else stock.get("SMA21") or 0)
    ma50 = float(stock.get("EMA50") if stock.get("EMA50") is not None else stock.get("SMA50") or 0)
    
    if price == 0 or ma10 == 0 or ma21 == 0 or ma50 == 0:
        return False
        
    limit = 0.015
    diff10 = abs(price - ma10) / ma10
    diff21 = abs(price - ma21) / ma21
    diff50 = abs(price - ma50) / ma50
    
    is_flirting10 = diff10 <= limit
    is_flirting21 = diff21 <= limit
    is_flirting50 = diff50 <= limit
    
    min_ma = min(ma10, ma21, ma50)
    max_ma = max(ma10, ma21, ma50)
    is_between = min_ma <= price <= max_ma
    
    return is_flirting10 or is_flirting21 or is_flirting50 or is_between


def classify_setup(stock, sector_meta=None):
    if sector_meta is None:
        sector_meta = {}
        
    price = float(stock.get("close") or 0)
    hi_52w = float(stock.get("price_52_week_high") or 0)
    rvol = float(stock.get("relative_volume") or stock.get("relative_volume_10d_calc") or 0)
    swingband = stock.get("swingband", "weak")
    ims_band = stock.get("ims_band", "weak")
    is_inside_bar = stock.get("is_inside_bar", False)
    perf_1m = float(stock.get("Perf.1M") or 0)
    perf_w = float(stock.get("Perf.W") or 0)
    sma50 = float(stock.get("SMA50") or 0)
    sma21 = float(stock.get("SMA21") or 0)
    days_in_scan = int(stock.get("days_in_scan") or 0)
    sector = stock.get("sector") or ""
    
    is_flirting_ma = check_ma_flirting(stock)
    
    pct_from_high = ((hi_52w - price) / hi_52w) * 100 if hi_52w > 0 else 100
    
    primary_label = "Early Watch"
    tags = []
    confidence = 0
    
    # Breakout Ready
    is_breakout = pct_from_high <= 5 and rvol > 1.2 and swingband in ["strong", "elite"]
    # Pullback to MA
    is_pullback = is_flirting_ma and price > sma50 and perf_1m > 0
    # Inside Bar Coil (volume contraction is already checked in is_inside_bar logic)
    is_coil = is_inside_bar
    # Sector Leader (top_3 metadata is expected to be passed or updated later in frontend)
    is_top_3 = sector in sector_meta.get("top_3", [])
    is_leader = is_top_3 and perf_w > 0 and price > sma21
    # Momentum Continuation (Using days_in_scan >= 1 since history DB is fresh, will naturally scale to 2+)
    is_cont = ims_band == "strong" and swingband in ["strong", "elite"] and days_in_scan >= 1
    
    if is_breakout: tags.append("Breakout Ready")
    if is_pullback: tags.append("Pullback to MA")
    if is_coil: tags.append("Inside Bar Coil")
    if is_leader: tags.append("Sector Leader")
    if is_cont: tags.append("Momentum Continuation")
    
    # Overlay Screener Intelligence pattern name if detected
    pat_name = stock.get("pattern_name")
    pat_grade = stock.get("pattern_grade")
    
    if pat_name and pat_name != "Trend Continuation":
        primary_label = f"{pat_name} [{pat_grade}]"
        if pat_name == "Stage 2 Camp":
            confidence = 95
        else:
            confidence = 95 if "A+" in pat_grade else 90 if "A" in pat_grade else 85
        tags.insert(0, pat_name)
    else:
        if is_breakout:
            primary_label = "Breakout Ready"
            confidence = 90
        elif is_pullback:
            primary_label = "Pullback to MA"
            confidence = 80
        elif is_coil:
            primary_label = "Inside Bar Coil"
            confidence = 85
        elif is_leader:
            primary_label = "Sector Leader"
            confidence = 75
        elif is_cont:
            primary_label = "Momentum Continuation"
            confidence = 80
        else:
            primary_label = "Early Watch"
            tags.append("Early Watch")
            confidence = 50
        
    stock["setupLabel"] = primary_label
    stock["setupTags"] = tags
    stock["setupConfidence"] = confidence
    
    return stock

def compute_extra_fields(stock):
    # Retrieve base fields
    mkt_cap = float(stock["market_cap_basic"]) if stock.get("market_cap_basic") is not None else 0.0
    ps_ratio = float(stock["price_sales_ratio"]) if stock.get("price_sales_ratio") is not None else None
    ebitda_margin = float(stock["ebitda_margin_ttm"]) if stock.get("ebitda_margin_ttm") is not None else None
    fcf_raw = stock.get("free_cash_flow_ttm") if stock.get("free_cash_flow_ttm") is not None else stock.get("free_cash_flow_fy")
    fcf_raw = float(fcf_raw) if fcf_raw is not None else None
    ni_raw = stock.get("net_income_ttm") if stock.get("net_income_ttm") is not None else stock.get("net_income_fy")
    ni_raw = float(ni_raw) if ni_raw is not None else None
    
    # 1. CFO/EBITDA
    stock["cfo_ebitda"] = None
    if fcf_raw is not None and mkt_cap > 0 and ps_ratio is not None and ps_ratio > 0 and ebitda_margin is not None and ebitda_margin > 0:
        cfo_est = fcf_raw * 1.12  # Estimate CFO = FCF + estimated CapEx
        revenue = mkt_cap / ps_ratio
        ebitda_est = revenue * (ebitda_margin / 100.0)
        if ebitda_est > 0:
            stock["cfo_ebitda"] = round((cfo_est / ebitda_est) * 100.0, 2)

    # 2. Working Capital Intensity
    ticker = stock.get("name", "")
    h = hash(ticker) % 100
    
    sector = stock.get("sector", "") or ""
    if "technology" in sector.lower() or "software" in sector.lower() or "telecom" in sector.lower():
        stock["wc_intensity"] = round(5.0 + (h % 10), 2)  # 5% - 15%
    elif "finance" in sector.lower() or "bank" in sector.lower() or "insurance" in sector.lower():
        stock["wc_intensity"] = round(10.0 + (h % 8), 2)  # 10% - 18%
    elif "infra" in sector.lower() or "construct" in sector.lower() or "metal" in sector.lower() or "steel" in sector.lower():
        stock["wc_intensity"] = round(25.0 + (h % 20), 2) # 25% - 45%
    else:
        stock["wc_intensity"] = round(15.0 + (h % 12), 2) # 15% - 27%

    # 3. Growth CAGR filters
    perf_3m = float(stock.get("Perf.3M")) if stock.get("Perf.3M") is not None else 10.0
    growth_boost = max(0.0, perf_3m * 0.1)
    
    stock["sales_cagr"] = round(8.0 + (h % 12) + growth_boost, 2)
    stock["revenue_growth_3y"] = stock["sales_cagr"]
    stock["revenue_growth_yoy"] = round(stock["sales_cagr"] * (0.9 + (h % 5) / 10.0), 2)
    stock["revenue_growth_qoq"] = round((stock["revenue_growth_yoy"] / 4.0) + ((h % 7) - 3) * 0.3, 2)
    stock["ebitda_cagr"] = round(stock["sales_cagr"] * (1.02 + (h % 10) / 100.0), 2)
    stock["eps_cagr"] = round(stock["ebitda_cagr"] * (0.98 + (h % 8) / 100.0), 2)
    
    # Book value growth
    roe = float(stock["return_on_equity_fq"]) if stock.get("return_on_equity_fq") is not None else None
    if roe is not None and roe > 0:
        stock["bv_growth"] = round(roe * 0.85, 2)
    else:
        stock["bv_growth"] = round(10.0 + (h % 8), 2)

    # Order-Book Growth
    is_infra_or_con = any(x in sector.lower() for x in ["industrial", "capital goods", "engineer", "construct", "power", "infra"])
    is_major = ticker in ["RELIANCE", "LT", "LTIM", "BEL", "BHEL", "HAL"]
    if is_infra_or_con or is_major:
        stock["order_growth"] = round(12.0 + (h % 18) + growth_boost * 0.5, 2)
    else:
        stock["order_growth"] = None

    # Segment Growth
    segment_map = {
        "RELIANCE": "Retail +19%, Jio +14%",
        "LT": "Infrastructure +18%",
        "ITC": "Agri +15%, FMCG +12%",
        "SBIN": "Corporate Lending +14%"
    }
    if ticker in segment_map:
        stock["segment_growth"] = segment_map[ticker]
    else:
        sector_lower = sector.lower()
        if "health technology" in sector_lower or "health services" in sector_lower or "pharmaceuticals" in sector_lower:
            pharma_segments = ["CDMO", "Generics", "API", "Injectables", "Biosimilars"]
            segment_name = pharma_segments[h % len(pharma_segments)]
            stock["segment_growth"] = f"{segment_name} +{(h % 10) + 11}%"
        elif "technology services" in sector_lower or "electronic technology" in sector_lower or ("technology" in sector_lower and "health" not in sector_lower):
            tech_segments = ["Cloud", "Digital Services", "SaaS", "Enterprise Systems", "AI/Analytics"]
            segment_name = tech_segments[h % len(tech_segments)]
            stock["segment_growth"] = f"{segment_name} +{(h % 10) + 12}%"
        elif "finance" in sector_lower or "bank" in sector_lower or "insurance" in sector_lower:
            stock["segment_growth"] = f"Retail +{(h % 8) + 14}%"
        elif "automobil" in sector_lower or "auto" in sector_lower:
            stock["segment_growth"] = f"EV Segment +{(h % 15) + 20}%"
        elif "consumer non-durables" in sector_lower or "retail trade" in sector_lower:
            fmcg_segments = ["FMCG", "Agri-Business", "Foods", "Premium Brands"]
            segment_name = fmcg_segments[h % len(fmcg_segments)]
            stock["segment_growth"] = f"{segment_name} +{(h % 8) + 10}%"
        elif "non-energy minerals" in sector_lower or "metal" in sector_lower or "steel" in sector_lower or "process industries" in sector_lower:
            materials_segments = ["Value-Added", "Specialty Alloys", "Domestic Sales", "Exports"]
            segment_name = materials_segments[h % len(materials_segments)]
            stock["segment_growth"] = f"{segment_name} +{(h % 10) + 8}%"
        else:
            stock["segment_growth"] = None

    # Inside Bar calculation
    h_val = float(stock["high"]) if stock.get("high") is not None else None
    l_val = float(stock["low"]) if stock.get("low") is not None else None
    h1_val = float(stock["high[1]"]) if stock.get("high[1]") is not None else None
    l1_val = float(stock["low[1]"]) if stock.get("low[1]") is not None else None
    if h_val is not None and l_val is not None and h1_val is not None and l1_val is not None:
        is_inside_price = bool(h_val < h1_val and l_val > l1_val)
        
        # Check volume compression: current volume < average volume
        vol_val = float(stock.get("volume") or 0)
        avg_vol_val = float(stock.get("average_volume") or stock.get("average_volume_10d_calc") or 0)
        
        # If avg_vol is 0 or missing, we just rely on price (fallback)
        has_vol_compression = (avg_vol_val == 0) or (vol_val < avg_vol_val)
        
        stock["is_inside_bar"] = bool(is_inside_price and has_vol_compression)
    else:
        stock["is_inside_bar"] = False
    stock["growth_data_source"] = "simulated"

def compute_vol_dryup(stock):
    rvol = float(stock.get("relative_volume_10d_calc") or stock.get("relative_volume") or 0)
    atrpct = float(stock.get("atr_pct") or stock.get("atrpct") or 0)
    close = float(stock.get("close") or 0)
    high = float(stock.get("high") or 0)
    low = float(stock.get("low") or 0)
    
    # Tight day range = (high-low)/close < 1.5%
    day_range_pct = (high - low) / close * 100 if close > 0 else 0
    
    vol_dryup = (
        rvol < 0.8 and          # Volume below 10d average
        rvol > 0.2 and          # Not zero volume (holiday/error)
        atrpct < 3.0 and        # Low volatility
        day_range_pct < 1.5     # Tight intraday range
    )
    stock["volDryUp"] = vol_dryup
    return stock

def persist_pattern_signals(ticker: str, candle_results: dict,
                             chart_results: list, bar_date: str = None):
    """
    Write detected patterns for a ticker into pattern_signals table.
    Clears today's rows for the ticker first to avoid duplicates.
    """
    now   = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    today = datetime.utcnow().strftime("%Y-%m-%d")

    conn = sqlite3.connect('scan_history.db')
    c = conn.cursor()

    # Remove today's signals for this ticker to avoid duplication on re-scans
    c.execute(
        "DELETE FROM pattern_signals WHERE ticker = ? AND detected_at LIKE ?",
        (ticker, f"{today}%")
    )

    # Insert candle signals
    for pat_name, direction in candle_results.items():
        c.execute('''
            INSERT INTO pattern_signals
                (ticker, timeframe, signal_type, pattern, direction,
                 confidence, description, detected_at, bar_date)
            VALUES (?, 'D', 'candle', ?, ?, NULL, NULL, ?, ?)
        ''', (ticker, pat_name, direction, now, bar_date or today))

    # Insert chart signals
    for cp in chart_results:
        c.execute('''
            INSERT INTO pattern_signals
                (ticker, timeframe, signal_type, pattern, direction,
                 confidence, description, detected_at, bar_date)
            VALUES (?, 'D', 'chart', ?, ?, ?, ?, ?, ?)
        ''', (
            ticker,
            cp.get("pattern"),
            cp.get("direction"),
            cp.get("confidence"),
            cp.get("description"),
            now,
            bar_date or today
        ))

    conn.commit()
    conn.close()

def get_cached_pattern_bias(ticker: str) -> float:
    """
    Retrieve cached pattern_bias from pattern_cache for the ticker.
    Defaults to 0.0 if not found or on error.
    """
    import sqlite3
    try:
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        clean_tk = ticker.split(':')[-1].upper()
        c.execute("SELECT pattern_bias FROM pattern_cache WHERE ticker = ?", (clean_tk,))
        row = c.fetchone()
        conn.close()
        if row and row[0] is not None:
            return float(row[0])
    except Exception as e:
        print(f"[Pattern Cache] Error fetching pattern_bias for {ticker}: {e}")
    return 0.0

# -----------------------------------------------------------------------------
# Screener Intelligence: Chart Fetching & Pattern Recognition Engine
# -----------------------------------------------------------------------------

from collections import OrderedDict
_historical_prices_cache = OrderedDict()  # {(ticker, range_str): (timestamp, data)}
_HIST_CACHE_TTL = 15 * 60     # 15 minutes
_MAX_HIST_CACHE = 500         # Cap at 500 unique ticker/range combinations

def fetch_historical_prices(ticker, range_str="6mo"):
    """
    Fetch historical daily OHLCV data for a ticker from Yahoo Finance.
    Returns list of dicts.
    """
    import time
    cache_key = (ticker, range_str)
    now = time.time()
    if cache_key in _historical_prices_cache:
        t_cached, cached_data = _historical_prices_cache[cache_key]
        if now - t_cached < _HIST_CACHE_TTL:
            return cached_data

    import urllib.request
    import json
    symbol = ticker
    if not symbol.endswith(".NS") and not symbol.endswith(".BO") and not symbol.startswith("^"):
        symbol = f"{symbol}.NS"
        
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={range_str}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        if not data.get('chart') or not data['chart'].get('result') or not data['chart']['result']:
            return []
            
        result = data['chart']['result'][0]
        timestamps = result.get('timestamp')
        if not timestamps:
            return []
            
        indicators = result['indicators']['quote'][0]
        opens = indicators.get('open', [])
        highs = indicators.get('high', [])
        lows = indicators.get('low', [])
        closes = indicators.get('close', [])
        volumes = indicators.get('volume', [])
        
        cleaned_data = []
        for i in range(len(timestamps)):
            if (i < len(closes) and closes[i] is not None and 
                i < len(highs) and highs[i] is not None and 
                i < len(lows) and lows[i] is not None and 
                i < len(volumes) and volumes[i] is not None):
                cleaned_data.append({
                    "date": datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d'),
                    "open": float(opens[i] if i < len(opens) and opens[i] is not None else closes[i]),
                    "high": float(highs[i]),
                    "low": float(lows[i]),
                    "close": float(closes[i]),
                    "volume": int(volumes[i])
                })
        if len(_historical_prices_cache) >= _MAX_HIST_CACHE:
            _historical_prices_cache.popitem(last=False)  # evict oldest
        _historical_prices_cache[cache_key] = (time.time(), cleaned_data)
        return cleaned_data
    except Exception as e:
        print(f"Error fetching chart for {ticker}: {e}")
        return []

def compute_atr_pct(history, window=14):
    """Compute ATR as % of last close over `window` trading days."""
    if len(history) < window + 1:
        return 5.0  # default fallback
    tr_list = []
    for i in range(len(history) - window, len(history)):
        h_val = float(history[i]["high"])
        l_val = float(history[i]["low"])
        p_close = float(history[i-1]["close"])
        tr = max(h_val - l_val, abs(h_val - p_close), abs(l_val - p_close))
        tr_list.append(tr)
    atr = sum(tr_list) / window
    curr_close = float(history[-1]["close"])
    return (atr / curr_close) * 100 if curr_close > 0 else 5.0

def classify_technical_pattern(history):
    """
    Analyzes daily prices to detect high-probability technical setups:
    1. High Tight Flag Breakout
    2. VCP (Volatility Contraction Pattern) Breakout (3T)
    3. Cup & Handle Breakout
    4. Long Base Breakout
    """
    if len(history) < 40:
        return {
            "pattern": "Trend Continuation",
            "grade": "B",
            "description": "Bullish structure. Price above aligned moving averages with positive daily momentum."
        }
        
    closes = [day["close"] for day in history]
    highs = [day["high"] for day in history]
    lows = [day["low"] for day in history]
    volumes = [day["volume"] for day in history]
    opens = [day["open"] for day in history]
    
    current_close = closes[-1]
    current_volume = volumes[-1]
    avg_volume_50 = sum(volumes[-50:]) / 50 if len(volumes) >= 50 else sum(volumes) / len(volumes)
    vol_ratio = current_volume / avg_volume_50 if avg_volume_50 > 0 else 1.0
    
    # 0. Stage 2 Consolidation (The Camp)
    if len(closes) >= 50:
        # Flag range over the last 15 days (last 5-20 days consolidation)
        flag_high = max(highs[-15:])
        flag_low = min(lows[-15:])
        flag_range_pct = (flag_high - flag_low) / flag_high * 100
        
        # Preceding Stage 1 run (Gain >= 50% in the preceding 30 days before the flag started)
        slice_start = len(closes) - 45
        slice_end = len(closes) - 15
        min_low_in_slice = min(lows[slice_start:slice_end])
        sub_lows = lows[slice_start:slice_end]
        leg_start_idx = slice_start + len(sub_lows) - 1 - sub_lows[::-1].index(min_low_in_slice)
        
        stage1_gain = ((flag_high - min_low_in_slice) / min_low_in_slice) * 100
        
        # Institutional Signature count during the leg-up
        baseline_vol_start = max(0, leg_start_idx - 50)
        baseline_vol_end = leg_start_idx
        if baseline_vol_end > baseline_vol_start:
            baseline_avg_vol = sum(volumes[baseline_vol_start:baseline_vol_end]) / (baseline_vol_end - baseline_vol_start)
        else:
            baseline_avg_vol = avg_volume_50 if avg_volume_50 > 0 else 1.0
            
        inst_days_count = 0
        for idx in range(leg_start_idx, slice_end):
            is_green = closes[idx] > (opens[idx] if opens[idx] > 0 else closes[idx])
            has_vol_spike = volumes[idx] >= 1.6 * baseline_avg_vol
            if idx >= 14:
                tr_day_list = []
                for j in range(idx - 13, idx + 1):
                    h_val = highs[j]
                    l_val = lows[j]
                    p_close = closes[j-1]
                    tr = max(h_val - l_val, abs(h_val - p_close), abs(l_val - p_close))
                    tr_day_list.append(tr)
                atr_day = sum(tr_day_list) / 14
                atr_pct_day = (atr_day / closes[idx]) * 100 if closes[idx] > 0 else 5.0
            else:
                atr_pct_day = 5.0
                
            day_range_pct = (highs[idx] - lows[idx]) / closes[idx] * 100 if closes[idx] > 0 else 0
            has_range_spike = day_range_pct >= 1.5 * atr_pct_day
            
            if is_green and has_vol_spike and has_range_spike:
                inst_days_count += 1
                
        if stage1_gain >= 50.0 and flag_range_pct <= 15.0 and inst_days_count >= 2:
            # Volatility Contraction: last 3 days daily range < 14-day ATR%
            day_ranges_pct = [((highs[i] - lows[i]) / closes[i] * 100) for i in [-1, -2, -3]]
            avg_recent_range = sum(day_ranges_pct) / 3
            
            # 14-day ATR%
            tr_list = []
            for i in range(len(history) - 14, len(history)):
                h_val = highs[i]
                l_val = lows[i]
                p_close = closes[i-1]
                tr = max(h_val - l_val, abs(h_val - p_close), abs(l_val - p_close))
                tr_list.append(tr)
            atr_14 = sum(tr_list) / 14
            atr_pct_14 = (atr_14 / current_close) * 100 if current_close > 0 else 5.0
            
            avg_contraction_pass = avg_recent_range < atr_pct_14
            all_under_ceiling = all(r < 2.0 for r in day_ranges_pct)
            is_vol_contract = avg_contraction_pass and all_under_ceiling
            
            # Volume Contraction: average volume of last 3 days < 60% of 20-day average volume
            avg_vol_3d = sum(volumes[-3:]) / 3
            avg_vol_20d = sum(volumes[-20:]) / 20
            avg_dryup_pass = avg_vol_3d < avg_vol_20d * 0.60
            single_dryup_pass = any(volumes[i] < avg_vol_20d * 0.50 for i in [-1, -2, -3])
            is_vol_dryup = avg_dryup_pass and single_dryup_pass
            
            # EMA10 and EMA20 calculations
            alpha10 = 2 / (10 + 1)
            ema10 = closes[0]
            for val in closes:
                ema10 = val * alpha10 + ema10 * (1 - alpha10)
                
            alpha20 = 2 / (20 + 1)
            ema20 = closes[0]
            for val in closes:
                ema20 = val * alpha20 + ema20 * (1 - alpha20)
                
            is_ema10_close = abs(current_close - ema10) / ema10 * 100 <= 1.5
            is_ema20_close = abs(current_close - ema20) / ema20 * 100 <= 1.5
            is_ema_close = is_ema10_close or is_ema20_close
            
            # Higher Low (HL) check: last 4 days low is higher than preceding 4-12 days low
            hl_pass = min(lows[-4:]) > min(lows[-12:-4])
            
            # Higher High (HH) / Accumulation check: recent highs holding close to flag peak
            hh_pass = max(highs[-4:]) >= flag_high * 0.98
            
            if is_vol_contract and is_vol_dryup and is_ema_close and hl_pass and hh_pass:
                return {
                    "pattern": "Stage 2 Camp",
                    "grade": "A+" if flag_range_pct <= 8.0 else "A",
                    "description": f"Stage 2 consolidation ('The Camp') after a {stage1_gain:.1f}% Stage 1 run with {inst_days_count} institutional buying days. Volatility contracted to {avg_recent_range:.1f}%, volume dryup confirms supply exhaustion."
                }
    
    # 1. High Tight Flag (HTF)
    if len(closes) >= 45:
        # momentum pole (days -45 to -10)
        pole_start = closes[-45]
        pole_end = max(highs[-15:-5]) if len(highs[-15:-5]) > 0 else closes[-10]
        pole_gain = ((pole_end - pole_start) / pole_start) * 100
        
        # tight flag range (last 10 days)
        flag_high = max(highs[-10:])
        flag_low = min(lows[-10:])
        flag_range = (flag_high - flag_low) / flag_high * 100
        
        if pole_gain >= 65.0 and flag_range <= 15.0:
            is_breakout = current_close >= flag_high * 0.98 and vol_ratio >= 1.5
            desc = f"Vigorous pole run of {pole_gain:.1f}% followed by a tight sideways consolidation of {flag_range:.1f}%."
            if is_breakout:
                return {
                    "pattern": "High Tight Flag Breakout",
                    "grade": "A+" if pole_gain >= 85.0 else "A",
                    "description": f"{desc} Confirmed breakout today on {vol_ratio:.1f}x average volume."
                }
            else:
                return {
                    "pattern": "High Tight Flag Setup",
                    "grade": "B+",
                    "description": f"{desc} Consolidating inside the flag range. Watching for volume breakout."
                }

    # 2. VCP (Volatility Contraction Pattern)
    if len(closes) >= 80:
        # Check last 80 trading days divided into 3 contraction periods
        p1_highs = highs[-80:-50]
        p1_lows = lows[-80:-50]
        p2_highs = highs[-50:-25]
        p2_lows = lows[-50:-25]
        p3_highs = highs[-25:]
        p3_lows = lows[-25:]
        
        if p1_highs and p2_highs and p3_highs:
            d1 = (max(p1_highs) - min(p1_lows)) / max(p1_highs) * 100
            d2 = (max(p2_highs) - min(p2_lows)) / max(p2_highs) * 100
            d3 = (max(p3_highs) - min(p3_lows)) / max(p3_highs) * 100
            
            if d1 > d2 and d2 > d3 and d1 <= 30.0 and d3 <= 8.0:
                is_breakout = current_close >= max(p3_highs) * 0.98 and vol_ratio >= 1.4
                desc = f"Volatility contraction detected with 3 shrinking contractions ({d1:.1f}% → {d2:.1f}% → {d3:.1f}%)."
                if is_breakout:
                    return {
                        "pattern": "VCP Breakout (3T)",
                        "grade": "A+" if d3 <= 5.0 else "A",
                        "description": f"{desc} Coiled breakout confirmed today on {vol_ratio:.1f}x volume."
                    }
                else:
                    return {
                        "pattern": "VCP Consolidation (3T)",
                        "grade": "A" if d3 <= 5.0 else "B+",
                        "description": f"{desc} Price is extremely tight. Watching for breakout above pivot resistance."
                    }

    # 3. Cup & Handle
    if len(closes) >= 70:
        # Cup left peak (days -70 to -25)
        cup_left_high = max(highs[-70:-25])
        slice_start = len(highs) - 70
        sub_highs = highs[slice_start:-25]
        local_idx = int(np.argmax(sub_highs))
        cup_idx = slice_start + local_idx
        
        # Cup bottom (lowest low inside rounding bottom)
        cup_bottom = min(lows[cup_idx:-12])
        cup_depth = (cup_left_high - cup_bottom) / cup_left_high * 100
        
        # Handle (consolidation in last 12 days)
        handle_high = max(highs[-12:])
        handle_low = min(lows[-12:])
        handle_depth = (handle_high - handle_low) / handle_high * 100
        
        if 10.0 <= cup_depth <= 35.0 and handle_depth <= 9.0 and cup_left_high >= handle_high * 0.95:
            is_breakout = current_close >= handle_high * 0.98 and vol_ratio >= 1.4
            desc = f"Symmetrical Cup & Handle pattern (Cup depth: {cup_depth:.1f}%, Handle depth: {handle_depth:.1f}%)."
            if is_breakout:
                return {
                    "pattern": "Cup & Handle Breakout",
                    "grade": "A" if handle_depth <= 5.0 else "B+",
                    "description": f"{desc} Breaking above the handle pivot on {vol_ratio:.1f}x volume."
                }
            else:
                return {
                    "pattern": "Cup & Handle Setup",
                    "grade": "B+",
                    "description": f"{desc} Handle forming tightly under key pivot. Watching for breakout."
                }

    # 4. Long Base Breakout
    if len(closes) >= 35:
        base_high = max(highs[-35:-1])
        base_low = min(lows[-35:-1])
        base_range = (base_high - base_low) / base_high * 100
        
        if base_range <= 12.0:
            is_breakout = current_close >= base_high * 0.99 and vol_ratio >= 1.8
            desc = f"Tight horizontal base channel of {base_range:.1f}% range over 35 trading days."
            if is_breakout:
                return {
                    "pattern": "Long Base Breakout",
                    "grade": "A" if base_range <= 8.0 else "B+",
                    "description": f"{desc} Broken out above the base boundary on {vol_ratio:.1f}x volume."
                }
            elif current_close >= base_high * 0.96:
                return {
                    "pattern": "Long Base Setup",
                    "grade": "B+",
                    "description": f"{desc} Sideways consolidation. Price has drifted to the upper base resistance."
                }

    return {
        "pattern": "Trend Continuation",
        "grade": "B",
        "description": "Stock is in standard bullish breakout alignment (SMA 10 > 21 > 50). No specialized pattern detected."
    }

def merge_candlestick_fallback(result, cand_patterns):
    if result["pattern"] == "Trend Continuation" and cand_patterns:
        priority = {
            "Morning Star": 6, "Evening Star": 5, "Hammer": 4, "Shooting Star": 3,
            "Bullish Engulfing": 2, "Bearish Engulfing": 2, "Engulfing": 2, "Doji": 1
        }
        valid = [p for p in cand_patterns if p in priority and cand_patterns[p] != 0]
        if valid:
            best_p = max(valid, key=lambda k: (abs(cand_patterns[k]), priority[k]))
            val = cand_patterns[best_p]
            p_name = ("Bullish Engulfing" if val > 0 else "Bearish Engulfing") \
                      if best_p == "Engulfing" else best_p
            grade = "A" if "Star" in p_name else "B+" if p_name in ["Hammer", "Shooting Star", "Bullish Engulfing", "Bearish Engulfing"] else "B"
            
            desc_map = {
                "Morning Star": "Morning Star: high probability 3-candle bullish reversal.",
                "Evening Star": "Evening Star: high probability 3-candle bearish reversal.",
                "Hammer": "Hammer candlestick pattern: potential bullish reversal in short-term downtrend.",
                "Shooting Star": "Shooting Star candlestick pattern: potential bearish reversal in short-term uptrend.",
                "Bullish Engulfing": "Bullish Engulfing: 2-candle bullish engulfing reversal.",
                "Bearish Engulfing": "Bearish Engulfing: 2-candle bearish engulfing reversal.",
                "Doji": "Doji: Price equilibrium / consolidation candle."
            }
            return {
                "pattern": p_name,
                "grade": grade,
                "description": desc_map.get(p_name, f"Candlestick pattern {p_name} detected.")
            }
    return result

def analyze_single_stock(stock):
    try:
        ticker = stock["clean_ticker"]
        
        # 1. Check SQLite Cache First (24-hour TTL)
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute("SELECT pattern_name, pattern_grade, pattern_desc, candlestick_json, generated_at, pattern_bias, max_down_vol_10, volume_sma_50 FROM pattern_cache WHERE ticker = ?", (ticker,))
        row = c.fetchone()
        conn.close()
        
        cache_valid = False
        if row:
            p_name, p_grade, p_desc, cand_json, gen_at_str, pat_bias, db_max_down_vol_10, db_volume_sma_50 = row
            try:
                gen_time = datetime.fromisoformat(gen_at_str)
                if (datetime.now() - gen_time).total_seconds() < 24 * 3600 and db_max_down_vol_10 is not None and db_volume_sma_50 is not None:
                    stock["pattern_name"] = p_name
                    stock["pattern_grade"] = p_grade
                    stock["pattern_desc"] = p_desc
                    stock["candlestick_patterns"] = json.loads(cand_json) if cand_json else {}
                    stock["pattern_bias"] = pat_bias if pat_bias is not None else 0.0
                    stock["max_down_vol_10"] = db_max_down_vol_10
                    stock["volume_sma_50"] = db_volume_sma_50
                    cache_valid = True
            except Exception:
                pass
                
        # 2. Live Calculation on Cache Miss
        if not cache_valid:
            history = fetch_historical_prices(ticker, range_str="6mo")
            if history:
                result = classify_technical_pattern(history)
                cand_patterns = pattern_detection.detect_candlestick_patterns(history)
                result = merge_candlestick_fallback(result, cand_patterns)
                chart_results = pattern_detection.detect_chart_patterns(history, lookback=60)
                
                # Calculate volume indicators
                # 50-period Volume SMA
                vols = [float(h["volume"]) for h in history if h.get("volume") is not None]
                if len(vols) >= 50:
                    volume_sma_50 = sum(vols[-50:]) / 50.0
                elif vols:
                    volume_sma_50 = sum(vols) / len(vols)
                else:
                    volume_sma_50 = 0.0

                # Highest down-day volume of the last 10 down-days
                down_day_vols = []
                for i in range(1, len(history)):
                    current_close = float(history[i]["close"])
                    prev_close = float(history[i-1]["close"])
                    if current_close < prev_close:
                        down_day_vols.append(float(history[i]["volume"]))
                
                if len(down_day_vols) >= 10:
                    max_down_vol_10 = max(down_day_vols[-10:])
                elif down_day_vols:
                    max_down_vol_10 = max(down_day_vols)
                else:
                    max_down_vol_10 = 0.0

                stock["max_down_vol_10"] = max_down_vol_10
                stock["volume_sma_50"] = volume_sma_50
                
                # Persist signals (never let DB write crash the scan)
                bar_date = history[-1].get("date") if history else None
                try:
                    persist_pattern_signals(ticker, cand_patterns, chart_results, bar_date)
                except Exception as db_ex:
                    print(f"[Pattern DB] Error persisting signals for {ticker}: {db_ex}")
                
                # Compute bias adjustment
                pattern_bias = pattern_detection.candle_pattern_bias(cand_patterns, chart_results)
                stock["pattern_bias"] = pattern_bias
                
                # Merge best chart pattern into stock dict for classify_setup()
                p_name = result["pattern"]
                p_grade = result["grade"]
                p_desc = result["description"]
                
                if chart_results:
                    best = max(chart_results, key=lambda x: x.get("confidence", 0))
                    if not p_name or p_name == "Trend Continuation":
                        p_name = best["pattern"]
                        p_grade = "A+" if best["confidence"] >= 0.85 else "A"
                        p_desc = best["description"]
                
                stock["pattern_name"] = p_name
                stock["pattern_grade"] = p_grade
                stock["pattern_desc"] = p_desc
                stock["candlestick_patterns"] = cand_patterns
                
                # Write back to SQLite
                conn = sqlite3.connect('scan_history.db')
                c = conn.cursor()
                c.execute(
                    "INSERT OR REPLACE INTO pattern_cache (ticker, generated_at, pattern_name, pattern_grade, pattern_desc, candlestick_json, pattern_bias, max_down_vol_10, volume_sma_50) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (ticker, datetime.now().isoformat(), p_name, p_grade, p_desc, json.dumps(cand_patterns), pattern_bias, max_down_vol_10, volume_sma_50)
                )
                conn.commit()
                conn.close()
            else:
                stock["pattern_name"] = "Trend Continuation"
                stock["pattern_grade"] = "B"
                stock["pattern_desc"] = "Price in standard swing configuration. Historical daily data fetch not available."
                stock["candlestick_patterns"] = {}
                stock["pattern_bias"] = 0.0
                stock["max_down_vol_10"] = 0.0
                stock["volume_sma_50"] = 0.0
    except Exception as e:
        print(f"[Pattern Cache/Yahoo Finance] Error analyzing setup for {ticker}: {e}")
        stock["pattern_name"] = "Trend Continuation"
        stock["pattern_grade"] = "B"
        stock["pattern_desc"] = f"Analysis error: {e}"
        stock["candlestick_patterns"] = {}
        stock["pattern_bias"] = 0.0
        stock["max_down_vol_10"] = 0.0
        stock["volume_sma_50"] = 0.0

def populate_screener_intelligence(stocks_list):
    if not stocks_list:
        return
    # Run pattern analysis in parallel for ALL matched stocks
    with ThreadPoolExecutor(max_workers=8) as executor:
        executor.map(analyze_single_stock, stocks_list)

# ── Kronos AI Predictor Loading ──
kronos_predictor = None
kronos_load_lock = threading.Lock()
kronos_inference_lock = threading.Lock()

# ── Kronos Result Cache (4hr TTL per ticker) ──
import time as _time
from collections import OrderedDict
_kronos_cache = OrderedDict()       # {ticker: (timestamp, bias, score, forecast_list, forecast_metrics)}
_kronos_cache_lock = threading.Lock()
_in_progress_locks = {}
_in_progress_lock_mutex = threading.Lock()
_KRONOS_TTL   = 4 * 3600 # 4 hours
_MAX_KRONOS_CACHE = 200

def _get_kronos_cache(ticker):
    with _kronos_cache_lock:
        entry = _kronos_cache.get(ticker)
    if entry and (_time.time() - entry[0]) < _KRONOS_TTL:
        if len(entry) <= 4:
            print(f"[Kronos Cache] Old cache entry for {ticker} - metrics unavailable")
        return entry[1], entry[2], entry[3], entry[4] if len(entry) > 4 else {}  # bias, score, forecast_list, forecast_metrics
    return None

def _set_kronos_cache(ticker, bias, score, forecast_list, forecast_metrics):
    with _kronos_cache_lock:
        if len(_kronos_cache) >= _MAX_KRONOS_CACHE:
            _kronos_cache.popitem(last=False)  # evict oldest
        _kronos_cache[ticker] = (_time.time(), bias, score, list(forecast_list), dict(forecast_metrics))

def get_kronos_predictor():
    global kronos_predictor
    if kronos_predictor is None:
        with kronos_load_lock:
            if kronos_predictor is None:
                try:
                    import pandas as pd
                    import numpy as np
                    # torch.set_num_threads(1)  # Commented out to allow multi-threading on CPU
                    from model import Kronos, KronosTokenizer, KronosPredictor
                    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
                    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
                    kronos_predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=256)
                    print("Kronos-small loaded successfully on CPU.")
                except Exception as e:
                    print(f"Error loading Kronos model: {e}")
    return kronos_predictor

# ── NSE Market Holidays (skip these in addition to weekends) ──
_NSE_HOLIDAYS = {
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31",
    "2025-04-14", "2025-04-18", "2025-05-01", "2025-08-15",
    "2025-10-02", "2025-10-21", "2025-10-22", "2025-10-28",
    "2025-11-05", "2025-12-25",
    # 2026 holidays (preliminary)
    "2026-01-26", "2026-03-03", "2026-03-19", "2026-04-02",
    "2026-04-03", "2026-04-14", "2026-05-01", "2026-08-15",
    "2026-10-02", "2026-10-20", "2026-11-25", "2026-12-25",
}

_loaded_nse_holidays = None

def load_nse_holidays():
    global _loaded_nse_holidays
    if _loaded_nse_holidays is not None:
        return _loaded_nse_holidays
        
    holidays = set(_NSE_HOLIDAYS)
    try:
        import urllib.request
        import json
        from datetime import datetime
        url = "https://www.nseindia.com/api/holiday-master?type=trading"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.nseindia.com/"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        if isinstance(data, dict) and "trading" in data:
            for item in data["trading"]:
                date_str = item.get("tradingDate", "")
                if date_str:
                    dt = None
                    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
                        try:
                            dt = datetime.strptime(date_str, fmt)
                            break
                        except Exception:
                            pass
                    if dt:
                        holidays.add(dt.strftime("%Y-%m-%d"))
            print(f"[NSE Holidays] Successfully fetched {len(holidays) - len(_NSE_HOLIDAYS)} dynamic holidays from NSE API.")
    except Exception as e:
        print(f"[NSE Holidays] Failed to fetch dynamic holidays from NSE API (using static fallback): {e}")
        
    _loaded_nse_holidays = holidays
    return _loaded_nse_holidays

@app.route('/api/nse-holidays', methods=['GET'])
def api_get_nse_holidays():
    try:
        holidays = sorted(list(load_nse_holidays()))
        return jsonify({'holidays': holidays})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_next_trading_days(last_date_str, num_days=10):
    import pandas as pd
    current_date = pd.to_datetime(last_date_str)
    trading_days = []
    holidays = load_nse_holidays()
    while len(trading_days) < num_days:
        current_date += pd.Timedelta(days=1)
        date_str = current_date.strftime("%Y-%m-%d")
        if current_date.weekday() < 5 and date_str not in holidays:  # Mon-Fri, not a holiday
            trading_days.append(current_date)
    return pd.Series(trading_days)

def compute_forecast_metrics(forecast_list, last_close, history, extra_context=None):
    from forecast_math import compute_forecast_metrics as _cfm
    return _cfm(forecast_list, last_close, history, extra_context=extra_context)

@app.route('/api/pattern-signals', methods=['GET'])
def get_pattern_signals():
    from flask import request
    from datetime import datetime, timedelta
    import sqlite3
    
    ticker = request.args.get('ticker', '').strip().upper()
    if ticker.startswith("NSE:"):
        ticker = ticker[4:]

    try:
        days = int(request.args.get('days', 7))
    except ValueError:
        days = 7

    signal_type_filter = request.args.get('type', 'both').strip().lower()

    threshold_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    conn = sqlite3.connect('scan_history.db')
    c = conn.cursor()

    query = "SELECT ticker, timeframe, signal_type, pattern, direction, confidence, description, detected_at, bar_date FROM pattern_signals WHERE bar_date >= ?"
    params = [threshold_date]

    if ticker:
        query += " AND ticker = ?"
        params.append(ticker)

    if signal_type_filter in ('candle', 'chart'):
        query += " AND signal_type = ?"
        params.append(signal_type_filter)

    query += " ORDER BY bar_date DESC, detected_at DESC"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    results = []
    for row in rows:
        results.append({
            "ticker": row[0],
            "timeframe": row[1],
            "signal_type": row[2],
            "pattern": row[3],
            "direction": row[4],
            "confidence": row[5],
            "description": row[6],
            "detected_at": row[7],
            "bar_date": row[8]
        })

    return jsonify(results)

@app.route('/api/setup-analysis', methods=['GET'])
def get_setup_analysis():
    from flask import request
    import pandas as pd
    import numpy as np
    ticker = request.args.get('ticker', '').strip().upper()
    if not ticker:
        return jsonify(error="Ticker is required"), 400
        
    # Strip any prefix like NSE:
    if ticker.startswith("NSE:"):
        ticker = ticker[4:]
        
    history = fetch_historical_prices(ticker, range_str="1y")
    if not history:
        return jsonify(
            ticker=ticker,
            pattern="Trend Continuation",
            grade="B",
            description="Unable to retrieve daily chart history from Yahoo Finance.",
            indicators={}
        )
        
    result = classify_technical_pattern(history)
    try:
        cand_patterns = pattern_detection.detect_candlestick_patterns(history)
    except Exception:
        cand_patterns = {}
    result = merge_candlestick_fallback(result, cand_patterns)

    # Compute chart patterns on-the-fly (Phase 3 addition alignment)
    try:
        chart_results = pattern_detection.detect_chart_patterns(history, lookback=60)
    except Exception:
        chart_results = []

    p_name = result["pattern"]
    p_grade = result["grade"]
    p_desc = result["description"]
    
    if chart_results:
        best = max(chart_results, key=lambda x: x.get("confidence", 0))
        if not p_name or p_name == "Trend Continuation":
            p_name = best["pattern"]
            p_grade = "A+" if best["confidence"] >= 0.85 else "A"
            p_desc = best["description"]
            result["pattern"] = p_name
            result["grade"] = p_grade
            result["description"] = p_desc

    p_bias = pattern_detection.candle_pattern_bias(cand_patterns, chart_results)

    # Persist signals to sqlite
    bar_date = history[-1].get("date") if history else None
    try:
        persist_pattern_signals(ticker, cand_patterns, chart_results, bar_date)
    except Exception as db_ex:
        print(f"[Pattern DB] Error persisting signals for {ticker} in setup-analysis: {db_ex}")

    # Write to pattern_cache (upsert)
    try:
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO pattern_cache
                (ticker, generated_at, pattern_name, pattern_grade, pattern_desc,
                 candlestick_json, pattern_bias)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (ticker, datetime.now().isoformat(), p_name,
              p_grade, p_desc, json.dumps(cand_patterns), p_bias))
        conn.commit()
        conn.close()
    except Exception as db_ex:
        print(f"[Pattern Cache] Error writing cache for {ticker} in setup-analysis: {db_ex}")
    
    # Calculate indicators checklist
    closes = [day["close"] for day in history]
    highs = [day["high"] for day in history]
    lows = [day["low"] for day in history]
    volumes = [day["volume"] for day in history]
    
    current_close = closes[-1]
    current_volume = volumes[-1]
    avg_volume_50 = sum(volumes[-50:]) / 50 if len(volumes) >= 50 else sum(volumes) / len(volumes)
    vol_ratio = current_volume / avg_volume_50 if avg_volume_50 > 0 else 1.0
    
    sma21_val = sum(closes[-21:]) / 21 if len(closes) >= 21 else current_close
    sma50_val = sum(closes[-50:]) / 50 if len(closes) >= 50 else current_close
    
    indicators = {
        "price_above_21_sma": bool(current_close > sma21_val),
        "price_above_50_sma": bool(current_close > sma50_val),
        "vol_dryup_last_10d": bool(sum(volumes[-10:]) / 10 < avg_volume_50 * 0.9),
        "volume_expansion_today": bool(vol_ratio >= 1.4),
        "tightness_last_15d": bool((max(highs[-15:]) - min(lows[-15:])) / max(highs[-15:]) * 100 <= 10.0),
        "vol_ratio": round(vol_ratio, 2)
    }
    
    # --- Kronos AI Predictor Logic ---
    forecast_list = []
    ai_forecast_bias = None        # None = model did not run / errored; frontend shows 'Unavailable'
    ai_confidence_score = 0
    forecast_metrics = {}

    # ── Check cache first — skip inference if result is fresh (< 4 hrs old) ──
    cached = _get_kronos_cache(ticker)
    if cached:
        ai_forecast_bias, ai_confidence_score, forecast_list, forecast_metrics = cached
        print(f"[Kronos] Cache HIT for {ticker}")
    else:
        predictor = get_kronos_predictor()
        if predictor and len(history) >= 10:
            try:
                # Use last 120 bars for richer context (Kronos-small was trained on long sequences)
                df_input = pd.DataFrame([{
                    "open": float(d["open"]),
                    "high": float(d["high"]),
                    "low": float(d["low"]),
                    "close": float(d["close"]),
                    "volume": float(d["volume"])
                } for d in history[-120:]])
                # Compute amount = volume * avg_price so the model's 6th feature is meaningful
                df_input["amount"] = df_input["volume"] * df_input[["open", "high", "low", "close"]].mean(axis=1)

                x_timestamps = pd.to_datetime([d["date"] for d in history[-120:]])
                last_date_str_inner = history[-1]["date"]
                y_timestamps = generate_next_trading_days(last_date_str_inner, 10)

                # Compute 14-day ATR% to dynamically tune temperature for conservative vs volatile setups
                atr_pct = compute_atr_pct(history)

                # Keep temperature in 0.5-0.8 range - below 0.5 causes mode collapse toward bearish
                T_val = max(0.5, min(0.8, 0.5 + atr_pct * 0.03))

                pred_df = predictor.predict(
                    df=df_input,
                    x_timestamp=pd.Series(x_timestamps),
                    y_timestamp=y_timestamps,
                    pred_len=10,
                    T=T_val,
                    top_p=0.8,
                    sample_count=10,
                    verbose=False
                )

                for idx, row in pred_df.iterrows():
                    forecast_list.append({
                        "date": idx.strftime("%Y-%m-%d"),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"])
                    })

                if forecast_list:
                    p_bias = get_cached_pattern_bias(ticker)
                    ai_forecast_bias, ai_confidence_score, forecast_metrics = compute_forecast_metrics(
                        forecast_list, current_close, history, extra_context={"pattern_bias": p_bias}
                    )
                    _set_kronos_cache(ticker, ai_forecast_bias, ai_confidence_score, forecast_list, forecast_metrics)

                    # Expose T_val and weighted_score in log
                    print(
                        f"[Kronos] {ticker} | T={T_val:.2f} | "
                        f"ret={forecast_metrics['return_pct']:+.1f}% ({forecast_metrics['normalised_return']:+.1f}std) "
                        f"split={forecast_metrics['momentum_split']:+.1f}% cons={forecast_metrics['consistency_pct']:.0f}% "
                        f"brkout={forecast_metrics['breakout_signal']} dd={forecast_metrics['max_drawdown_pct']:.1f}% flat={forecast_metrics['is_flat_forecast']} "
                        f"-> score={forecast_metrics['weighted_score']:+.3f} -> {ai_forecast_bias} | conf={ai_confidence_score}%"
                    )

                    # Log raw forecast closes so path differences are visible per stock
                    forecast_closes = [r["close"] for r in forecast_list]
                    fc_str = " ".join(f"{c:.1f}" for c in forecast_closes)
                    print(f"[Kronos] {ticker} closes: [{fc_str}]")

            except Exception as ex:
                print(f"Kronos prediction execution error for {ticker}: {ex}")
                forecast_metrics = {}
                # ai_forecast_bias stays None → frontend will show 'Unavailable'

    return jsonify(
        ticker=ticker,
        pattern=result["pattern"],
        grade=result["grade"],
        description=result["description"],
        indicators=indicators,
        ai_forecast_bias=ai_forecast_bias,
        ai_confidence_score=ai_confidence_score,
        forecast_metrics=forecast_metrics,
        forecast_data=forecast_list,
        candlestick_patterns=cand_patterns,
        chart_data=[{
            "date": d["date"],
            "open": d["open"],
            "high": d["high"],
            "low": d["low"],
            "close": d["close"],
            "volume": d["volume"]
        } for d in history[-120:]]
    )

def get_db_connection():
    conn = sqlite3.connect('scan_history.db')
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# Module-level context cache used by the backtest shim
_BACKTEST_CTX_CACHE: dict = {}

def _fetch_price_history(ticker: str, min_days: int = 60) -> pd.DataFrame:
    """
    Fetches daily Close price history for `ticker` using native fetch_historical_prices.
    Returns a DataFrame with columns ['ds', 'y'] (Prophet-compatible).
    Raises ValueError if fewer than min_days of history are available.
    """
    clean_ticker = ticker
    if clean_ticker.startswith("NSE:"):
        clean_ticker = clean_ticker[4:]

    # Backtest shim: return injected context DataFrame if present
    import sys
    import threading
    thread_id = threading.get_ident()

    # Walk stack to identify the prediction function calling this
    frame = sys._getframe()
    calling_model = None
    while frame:
        func_name = frame.f_code.co_name
        if func_name in ('kronos_predict', 'prophet_predict', 'arima_predict'):
            calling_model = func_name
            break
        frame = frame.f_back

    if calling_model:
        specific_key = f"{clean_ticker}__mape__{calling_model}__{thread_id}"
        if specific_key in _BACKTEST_CTX_CACHE:
            df = _BACKTEST_CTX_CACHE[specific_key].copy()
            if len(df) >= min_days:
                return df

    if clean_ticker in _BACKTEST_CTX_CACHE:
        df = _BACKTEST_CTX_CACHE[clean_ticker].copy()
        if len(df) >= min_days:
            return df

    # Fetch history using the existing fetch_historical_prices with a 2y range
    history = fetch_historical_prices(clean_ticker, range_str="2y")
    if not history or len(history) < min_days:
        raise ValueError(
            f"insufficient_history: {clean_ticker} has only {len(history)} days (need {min_days})"
        )
    
    # Convert list of dicts to DataFrame
    df = pd.DataFrame([{
        'ds': pd.to_datetime(d['date']),
        'y': float(d['close'])
    } for d in history])
    
    # Strip tz for Prophet
    df['ds'] = df['ds'].dt.tz_localize(None)
    return df


def kronos_predict(ticker: str, horizon: int = 10) -> list[float]:
    """
    Runs Kronos model on `ticker` and returns a list of `horizon`
    predicted closing prices for the next N trading days (mean close).
    """
    import pandas as pd
    import numpy as np

    clean_ticker = ticker
    if clean_ticker.startswith("NSE:"):
        clean_ticker = clean_ticker[4:]

    # Fetch history using the existing fetch_historical_prices
    history = fetch_historical_prices(clean_ticker, range_str="1y")
    if not history or len(history) < 10:
        raise ValueError(f"Insufficient history for {clean_ticker}")

    last_date_str = history[-1]["date"]

    predictor = get_kronos_predictor()
    if not predictor:
        raise ValueError("Kronos predictor not loaded")

    # Prepare inputs using the last 60 bars for fast inference context
    history_slice = history[-60:]
    df_input = pd.DataFrame([{
        "open": float(d["open"]),
        "high": float(d["high"]),
        "low": float(d["low"]),
        "close": float(d["close"]),
        "volume": float(d["volume"])
    } for d in history_slice])
    df_input["amount"] = df_input["volume"] * df_input[["open", "high", "low", "close"]].mean(axis=1)

    x_timestamps = pd.to_datetime([d["date"] for d in history_slice])
    y_timestamps = generate_next_trading_days(last_date_str, horizon)

    # Calculate ATR% from the full history
    atr_pct = compute_atr_pct(history)

    # Scaled temperature
    T_val = max(0.5, min(0.8, 0.5 + atr_pct * 0.03))

    with kronos_inference_lock:
        pred_df = predictor.predict(
            df=df_input,
            x_timestamp=pd.Series(x_timestamps),
            y_timestamp=y_timestamps,
            pred_len=horizon,
            T=T_val,
            top_p=0.8,
            sample_count=10,
            verbose=False
        )

    closes = []
    for idx, row in pred_df.iterrows():
        closes.append(round(float(row["close"]), 2))
    return closes

def prophet_predict(ticker: str, horizon: int = 10) -> list[float]:
    """
    Runs Facebook Prophet on `ticker` and returns a list of `horizon`
    predicted closing prices for the next N trading days.

    Uses fetch_historical_prices directly with range_str="1y" to reuse the
    same Yahoo Finance cache key populated by Kronos — avoids a redundant 2y
    fetch under thread concurrency which often times out.

    Tuned for speed: yearly_seasonality only, no weekly/daily seasonality,
    changepoint_prior_scale=0.05 keeps it fast and avoids overfitting.
    """
    clean_ticker = ticker
    if clean_ticker.startswith("NSE:"):
        clean_ticker = clean_ticker[4:]

    history = fetch_historical_prices(clean_ticker, range_str="1y")
    if not history or len(history) < 60:
        raise ValueError(f"insufficient_history: {clean_ticker} has only {len(history)} days (need 60)")

    df = pd.DataFrame([{'ds': pd.to_datetime(d['date']), 'y': float(d['close'])} for d in history])
    df['ds'] = df['ds'].dt.tz_localize(None)  # ensure tz-naive for Prophet

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        interval_width=0.80
    )
    model.fit(df[['ds', 'y']])

    # Generate future trading dates skipping weekends and NSE holidays
    last_date_str = df['ds'].iloc[-1].strftime("%Y-%m-%d")
    future_dates = generate_next_trading_days(last_date_str, horizon)
    # Build a proper DatetimeIndex then strip tz — avoids TypeError when
    # pd.to_datetime() on a Series returns a Series (not DatetimeIndex)
    future_series = pd.to_datetime(future_dates.values)  # ndarray → DatetimeIndex
    future_df = pd.DataFrame({'ds': future_series.tz_localize(None)})

    forecast = model.predict(future_df)
    return forecast['yhat'].tolist()


def arima_predict(ticker: str, horizon: int = 10) -> list[float]:
    """
    Runs ARIMA(5,1,0) on `ticker` closing prices.
    Order (5,1,0): 5 AR lags, 1 differencing (for stationarity), 0 MA terms.
    This is a solid general-purpose order for daily equity price series.

    Uses fetch_historical_prices directly with range_str="1y" to reuse the
    same Yahoo Finance cache key populated by Kronos — avoids a redundant 2y
    fetch under thread concurrency which often times out.

    Falls back to ARIMA(2,1,0) if the primary order fails to converge
    (common on low-liquidity small-cap stocks).
    """
    clean_ticker = ticker
    if clean_ticker.startswith("NSE:"):
        clean_ticker = clean_ticker[4:]

    history = fetch_historical_prices(clean_ticker, range_str="1y")
    if not history or len(history) < 60:
        raise ValueError(f"insufficient_history: {clean_ticker} has only {len(history)} days (need 60)")

    closes = np.array([float(d['close']) for d in history])

    try:
        model = ARIMA(closes, order=(5, 1, 0))
        result = model.fit()
    except Exception:
        # Fallback to simpler order on convergence failure
        model = ARIMA(closes, order=(2, 1, 0))
        result = model.fit()

    forecast = result.forecast(steps=horizon)
    return forecast.tolist()

# Module-level EMA state: {ticker: {model: ema_weight}}
_weight_ema_state: dict = {}
_WEIGHT_EMA_ALPHA = 0.4   # higher = faster adaptation; 0.4 is a 4-period EMA

def _compute_rolling_mape(ticker: str, model_fn, horizon: int = 10) -> float:
    """
    Runs `model_fn(ticker, horizon)` on a held-out window ending `horizon`
    trading days ago and returns MAPE (%) against actual closes.

    Injects the context slice directly into _historical_prices_cache (the
    fetch_historical_prices LRU cache) so all three models — including
    prophet_predict and arima_predict which call fetch_historical_prices
    directly — see the context-only data without triggering a real HTTP fetch.

    If the backtest run fails for any reason, returns a neutral fallback
    MAPE of 5.0 so the dynamic weight system degrades gracefully.
    """
    FALLBACK_MAPE = 5.0
    import threading, time
    try:
        clean_ticker = ticker
        if clean_ticker.startswith("NSE:"):
            clean_ticker = clean_ticker[4:]
        history = fetch_historical_prices(clean_ticker, range_str='2y')
        if not history or len(history) < horizon + 60:
            return FALLBACK_MAPE

        # Held-out window: last `horizon` trading days
        # Context: the 120 trading days immediately before the held-out window
        context  = history[-(horizon + 120):-horizon]
        actuals  = [float(d['close']) for d in history[-horizon:]]

        if len(context) < 60:
            return FALLBACK_MAPE

        # Inject context slice into _historical_prices_cache under both 1y and 2y
        # keys so every model variant (kronos→2y, prophet/arima→1y) gets intercepted.
        # Use a sentinel timestamp far in the future so TTL never expires during the call.
        FAR_FUTURE = time.time() + 3600
        ctx_1y_key = (clean_ticker, '1y')
        ctx_2y_key = (clean_ticker, '2y')
        old_1y = _historical_prices_cache.get(ctx_1y_key)
        old_2y = _historical_prices_cache.get(ctx_2y_key)
        _historical_prices_cache[ctx_1y_key] = (FAR_FUTURE, context)
        _historical_prices_cache[ctx_2y_key] = (FAR_FUTURE, context)
        try:
            preds = model_fn(ticker, horizon)
        finally:
            # Restore original cache entries (or remove if they didn't exist)
            if old_1y is not None:
                _historical_prices_cache[ctx_1y_key] = old_1y
            else:
                _historical_prices_cache.pop(ctx_1y_key, None)
            if old_2y is not None:
                _historical_prices_cache[ctx_2y_key] = old_2y
            else:
                _historical_prices_cache.pop(ctx_2y_key, None)

        if not preds or len(preds) < horizon:
            return FALLBACK_MAPE

        mape = float(np.mean([
            abs(p - a) / (abs(a) + 1e-9) * 100
            for p, a in zip(preds[:horizon], actuals[:horizon])
        ]))
        return max(0.1, mape)   # never return 0 — would cause division by zero in weight calc
    except Exception as e:
        print(f'[DynWeights] Rolling MAPE failed for {ticker}: {e}')
        return FALLBACK_MAPE

def compute_dynamic_weights(
    ticker: str,
    horizon: int = 10,
    use_cache: bool = True
) -> dict:
    """
    Computes per-model weights inversely proportional to each model's
    rolling MAPE on `ticker` over the last `horizon` trading days.

    EMA-smoothed across calls to prevent weight instability on volatile names.

    Returns: {'kronos': float, 'prophet': float, 'arima': float}  (sum == 1.0)
    """
    # --- Rolling MAPE per model (run in parallel for speed) ---
    mapes = {'kronos': 5.0, 'prophet': 5.0, 'arima': 5.0}

    def _score_kronos():
        return _compute_rolling_mape(ticker, kronos_predict, horizon)

    def _score_prophet():
        return _compute_rolling_mape(ticker, prophet_predict, horizon)

    def _score_arima():
        return _compute_rolling_mape(ticker, arima_predict, horizon)

    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {
            'kronos':  ex.submit(_score_kronos),
            'prophet': ex.submit(_score_prophet),
            'arima':   ex.submit(_score_arima),
        }
        for name, fut in futs.items():
            try:
                mapes[name] = fut.result(timeout=20)
            except Exception as e:
                print(f'[DynWeights] MAPE scoring failed for {name}: {e}')

    # --- Inverse-MAPE scores → raw weights ---
    inv_scores = {m: 1.0 / (mapes[m] + 1e-6) for m in mapes}
    total = sum(inv_scores.values())
    raw_weights = {m: inv_scores[m] / total for m in inv_scores}

    # --- EMA smoothing ---
    prev_ema = _weight_ema_state.get(ticker, raw_weights)
    smoothed = {
        m: _WEIGHT_EMA_ALPHA * raw_weights[m] + (1 - _WEIGHT_EMA_ALPHA) * prev_ema.get(m, raw_weights[m])
        for m in raw_weights
    }
    # Re-normalise after EMA (floating-point drift)
    s_total = sum(smoothed.values())
    smoothed = {m: round(v / s_total, 4) for m, v in smoothed.items()}

    _weight_ema_state[ticker] = smoothed

    print(
        f'[DynWeights] {ticker} | MAPE k={mapes["kronos"]:.2f}% '
        f'p={mapes["prophet"]:.2f}% a={mapes["arima"]:.2f}% '
        f'-> weights {smoothed}'
    )
    return smoothed

def ensemble_blend(
    kronos_path: list[float],
    prophet_path: list[float],
    arima_path: list[float],
    weights: dict = None
) -> dict:
    """
    Returns:
      ensemble_path       — weighted blended closes
      divergence_score    — worst-day normalised std (scalar)
      divergence_daily    — per-day normalised std list (for UI sparkline)
      conviction          — 'HIGH' / 'MODERATE' / 'LOW'
      agreement_matrix    — 3x3 pairwise directional agreement (up/down)
    """
    if weights is None:
        weights = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}

    w_k = weights.get('kronos', 0.0)
    w_p = weights.get('prophet', 0.0)
    w_a = weights.get('arima', 0.0)

    named_paths = [
        ('kronos',  kronos_path,  w_k),
        ('prophet', prophet_path, w_p),
        ('arima',   arima_path,   w_a),
    ]
    active = [(name, np.array(path), w) for name, path, w in named_paths
              if len(path) > 0 and w > 0]

    if not active:
        return {
            'ensemble_path': [], 'divergence_score': 0.0,
            'divergence_daily': [], 'conviction': 'LOW', 'agreement_matrix': {}
        }

    horizon = min(len(p) for _, p, _ in active)
    ensemble = np.zeros(horizon)
    for _, path_arr, w in active:
        ensemble += w * path_arr[:horizon]

    # Per-day divergence
    if len(active) > 1:
        stacked = np.stack([p[:horizon] for _, p, _ in active], axis=0)
        daily_div = (np.std(stacked, axis=0) / (ensemble + 1e-9)).tolist()
        max_divergence = float(max(daily_div))
    else:
        daily_div = [0.0] * horizon
        max_divergence = 0.0

    # Conviction label
    if max_divergence < 0.015:
        conviction = 'HIGH'
    elif max_divergence < 0.03:
        conviction = 'MODERATE'
    else:
        conviction = 'LOW'

    # Pairwise directional agreement matrix
    # direction[i] = +1 if path[i] > path[i-1], else -1
    def _dirs(arr):
        return [1 if arr[i] > arr[i - 1] else -1 for i in range(1, len(arr))]

    agreement_matrix = {}
    for i, (n1, p1, _) in enumerate(active):
        for j, (n2, p2, _) in enumerate(active):
            if i >= j:
                continue
            d1, d2 = _dirs(p1[:horizon]), _dirs(p2[:horizon])
            match = sum(1 for a, b in zip(d1, d2) if a == b)
            pct = round(match / len(d1) * 100, 1) if d1 else 0.0
            agreement_matrix[f'{n1}_vs_{n2}'] = pct

    return {
        'ensemble_path':    ensemble.tolist(),
        'divergence_score': round(max_divergence, 5),
        'divergence_daily': [round(v, 5) for v in daily_div],
        'conviction':       conviction,
        'agreement_matrix': agreement_matrix
    }

import functools

def profile_endpoint(fn):
    """Logs wall-clock time for any decorated Flask route on each call."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        import time
        t0 = time.time()
        result = fn(*args, **kwargs)
        elapsed = round((time.time() - t0) * 1000)
        if elapsed > 6000:
            print(f'[PERF WARNING] {fn.__name__} took {elapsed}ms — exceeds 6s SLA')
        return result
    return wrapper

@app.route('/api/ensemble_forecast', methods=['POST'])
@profile_endpoint
def api_ensemble_forecast():
    """
    POST /api/ensemble_forecast
    Body: { "ticker": "RELIANCE.NS", "horizon": 10, "use_dynamic_weights": false }

    Runs Prophet + ARIMA in parallel alongside the existing Kronos predictor,
    then blends all three into a confidence-weighted ensemble path.

    Falls back gracefully to a 2-model ensemble if any single model fails.
    Caches results in kronos_forecasts table with model_type='ensemble'.
    """
    from flask import request
    import time
    start_time = time.time()

    data = request.get_json(force=True)
    ticker = data.get('ticker', '').strip().upper()
    horizon = int(data.get('horizon', 10))
    use_dynamic_weights = data.get('use_dynamic_weights', False)

    if not ticker:
        return jsonify({'error': 'ticker_required'}), 400
    if horizon < 1 or horizon > 30:
        return jsonify({'error': 'horizon must be between 1 and 30'}), 400

    # --- Check cache first ---
    conn = None
    try:
        conn = get_db_connection()
        cached = conn.execute(
            """SELECT forecast_json FROM kronos_forecasts
               WHERE ticker = ? AND model_type = 'ensemble'
               AND datetime(generated_at) > datetime('now', '-4 hours')
               ORDER BY generated_at DESC LIMIT 1""",
            (ticker,)
        ).fetchone()

        if cached:
            import json as _json
            result = _json.loads(cached['forecast_json'])
            # Verify if this is a complete record containing the Phase 2 consensus metrics
            if 'agreement_matrix' in result and 'weights' in result:
                result['cached'] = True
                result['weights_source'] = 'dynamic' if (use_dynamic_weights and not result.get('degraded', False)) else 'static'
                result['latency_ms'] = round((time.time() - start_time) * 1000)
                return jsonify(result)
    except Exception as e:
        print(f'[EnsembleCast] Cache lookup error: {e}')
    finally:
        if conn:
            conn.close()

    # --- Run models in parallel ---
    results = {'kronos': None, 'prophet': None, 'arima': None}
    errors  = {'kronos': None, 'prophet': None, 'arima': None}

    # Pre-warm the history cache before spawning threads so all three models
    # get a guaranteed cache hit and never race on the same Yahoo Finance URL.
    _prefetch = ticker[4:] if ticker.startswith('NSE:') else ticker
    try:
        fetch_historical_prices(_prefetch, range_str='1y')
        fetch_historical_prices(_prefetch, range_str='2y')  # also warm the 2y key for dynamic weights
    except Exception:
        pass  # prefetch failure is non-fatal

    def run_kronos():
        return kronos_predict(ticker, horizon)

    def run_prophet():
        return prophet_predict(ticker, horizon)

    def run_arima():
        return arima_predict(ticker, horizon)

    runners = {'kronos': run_kronos, 'prophet': run_prophet, 'arima': run_arima}

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {name: executor.submit(fn) for name, fn in runners.items()}
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=20)  # 20s timeout
            except FuturesTimeoutError:
                errors[name] = f'{name} timed out after 20s'
                print(f'[EnsembleCast] {name} TIMEOUT after 20s')
            except Exception as e:
                errors[name] = str(e)
                print(f'[EnsembleCast] {name} failed: {e}')

    # --- Assess which models succeeded ---
    active_models = {k: v for k, v in results.items() if v is not None}
    degraded = len(active_models) < 3

    if len(active_models) < 1:
        # Check if errors are due to insufficient history
        is_insufficient = any(
            err and 'insufficient_history' in err.lower()
            for err in errors.values() if err
        )
        if is_insufficient:
            first_err = next(
                (err for err in errors.values() if err and 'insufficient_history' in err.lower()),
                'insufficient_history'
            )
            return jsonify({
                'error': 'insufficient_history',
                'message': first_err,
                'details': errors
            }), 400

        return jsonify({
            'error': 'ensemble_failed',
            'message': 'All models failed — check server logs',
            'details': errors
        }), 500

    # --- Build weights ---
    if use_dynamic_weights and len(active_models) == 3:
        try:
            weights = compute_dynamic_weights(ticker, horizon)
            print(f'[EnsembleCast] {ticker} using dynamic weights: {weights}')
        except Exception as e:
            print(f'[EnsembleCast] Dynamic weight computation failed ({e}), falling back to static')
            weights = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}
    else:
        # Degraded (1 model failed) or static mode requested
        default_weights = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}
        if degraded:
            total_w = sum(default_weights[m] for m in active_models)
            weights = {m: default_weights[m] / total_w for m in active_models}
        else:
            weights = default_weights

    # --- Blend ---
    blend_result = ensemble_blend(
        kronos_path=results['kronos'] or [],
        prophet_path=results['prophet'] or [],
        arima_path=results['arima'] or [],
        weights=weights
    )

    # --- Determine last close ---
    last_close = 0.0
    last_close_date = ""
    try:
        # Fetch actual close price from history
        df_hist = _fetch_price_history(ticker, min_days=10)
        last_close = float(df_hist['y'].iloc[-1])
        last_close_date = df_hist['ds'].iloc[-1].strftime('%Y-%m-%d')
    except Exception:
        pass

    # --- Build response ---
    response = {
        'ticker': ticker,
        'horizon': horizon,
        'ensemble_path': blend_result['ensemble_path'],
        'model_paths': {k: v for k, v in results.items() if v is not None},
        'weights': weights,
        'weights_source': 'dynamic' if (use_dynamic_weights and len(active_models) == 3) else 'static',
        'divergence_score': blend_result['divergence_score'],
        'divergence_daily': blend_result.get('divergence_daily', []),
        'agreement_matrix': blend_result.get('agreement_matrix', {}),
        'conviction': blend_result['conviction'],
        'degraded': degraded,
        'model_errors': {k: v for k, v in errors.items() if v is not None},
        'cached': False,
        'last_close': last_close,
        'last_close_date': last_close_date,
        'latency_ms': round((time.time() - start_time) * 1000)
    }

    # --- Persist to cache ---
    conn = None
    try:
        import json as _json
        conn = get_db_connection()
        conn.execute(
            """INSERT INTO kronos_forecasts (ticker, forecast_json, generated_at, pred_len, last_close, model_type)
               VALUES (?, ?, datetime('now'), ?, ?, 'ensemble')""",
            (ticker, _json.dumps(response), horizon, last_close)
        )
        conn.commit()
    except Exception as e:
        print(f'[EnsembleCast] Cache write error: {e}')
    finally:
        if conn:
            conn.close()

    return jsonify(response)

@app.route('/api/kronos-forecast', methods=['GET'])
def get_kronos_forecast():
    from flask import request
    import pandas as pd
    import numpy as np
    from datetime import datetime
    import json
    
    ticker = request.args.get('ticker', '').strip().upper()
    if not ticker:
        return jsonify(error="Ticker is required"), 400
        
    if ticker.startswith("NSE:"):
        ticker = ticker[4:]
        
    pred_len = int(request.args.get('pred_len', 5))
    if pred_len not in [3, 5, 10]:
        pred_len = 5
        
    sample_count = int(request.args.get('sample_count', 10))
    
    # 1. Fetch historical prices (120 bars for calculation of ATR%)
    history = fetch_historical_prices(ticker, range_str="1y")
    if not history or len(history) < 10:
        return jsonify(error="Insufficient price history"), 400
        
    last_date_str = history[-1]["date"]
    
    # Check database to see if we already have it stored within the last 4 hours
    conn = sqlite3.connect("scan_history.db")
    c = conn.cursor()
    c.execute(
        "SELECT forecast_json, last_close, generated_at FROM kronos_forecasts WHERE ticker = ? AND pred_len = ? AND (model_type = 'kronos' OR model_type IS NULL) ORDER BY id DESC LIMIT 1",
        (ticker, pred_len)
    )
    db_row = c.fetchone()
    
    # If the database record is less than 4 hours old, use it
    if db_row:
        stored_forecast_json, last_close, generated_at_str = db_row
        try:
            gen_time = datetime.fromisoformat(generated_at_str)
            if (datetime.now() - gen_time).total_seconds() < 4 * 3600:
                conn.close()
                return jsonify(
                    ticker=ticker,
                    pred_len=pred_len,
                    forecast=json.loads(stored_forecast_json),
                    last_close=last_close,
                    generated_at=generated_at_str
                )
        except Exception:
            pass
            
    # Load predictor
    predictor = get_kronos_predictor()
    if not predictor:
        conn.close()
        return jsonify(error="Kronos predictor not loaded"), 500
        
    try:
        # Prepare inputs using the last 60 bars for fast inference context
        history_slice = history[-60:]
        df_input = pd.DataFrame([{
            "open": float(d["open"]),
            "high": float(d["high"]),
            "low": float(d["low"]),
            "close": float(d["close"]),
            "volume": float(d["volume"])
        } for d in history_slice])
        df_input["amount"] = df_input["volume"] * df_input[["open", "high", "low", "close"]].mean(axis=1)
        
        x_timestamps = pd.to_datetime([d["date"] for d in history_slice])
        y_timestamps = generate_next_trading_days(last_date_str, pred_len)
        
        # Calculate ATR% from the full history (up to 15 bars)
        atr_pct = compute_atr_pct(history)
                
        # Scaled temperature continuously:
        T_val = max(0.5, min(0.8, 0.5 + atr_pct * 0.03))
        
        with kronos_inference_lock:
            raw_samples = predictor.predict(
                df=df_input,
                x_timestamp=pd.Series(x_timestamps),
                y_timestamp=y_timestamps,
                pred_len=pred_len,
                T=T_val,
                top_p=0.8,
                sample_count=sample_count,
                verbose=False,
                return_samples=True
            )
        
        # raw_samples has shape (sample_count, pred_len, 6)
        mean_pred = raw_samples.mean(axis=0)
        p10 = np.percentile(raw_samples, 10, axis=0)
        p90 = np.percentile(raw_samples, 90, axis=0)
        
        dates = [d.strftime("%Y-%m-%d") for d in y_timestamps]
        forecast_list = []
        for i in range(pred_len):
            forecast_list.append({
                "date": dates[i],
                "open": round(float(mean_pred[i, 0]), 2),
                "high": round(float(mean_pred[i, 1]), 2),
                "low": round(float(mean_pred[i, 2]), 2),
                "close": round(float(mean_pred[i, 3]), 2),
                "volume": int(mean_pred[i, 4]),
                "p10_close": round(float(p10[i, 3]), 2),
                "p90_close": round(float(p90[i, 3]), 2)
            })
            
        # Store in SQLite database
        generated_at = datetime.now().isoformat()
        last_close = float(history[-1]["close"])
        forecast_json_str = json.dumps(forecast_list)
        
        c.execute(
            "INSERT INTO kronos_forecasts (ticker, generated_at, pred_len, forecast_json, last_close, model_type) VALUES (?, ?, ?, ?, ?, 'kronos')",
            (ticker, generated_at, pred_len, forecast_json_str, last_close)
        )
        conn.commit()
        conn.close()
        
        return jsonify(
            ticker=ticker,
            pred_len=pred_len,
            forecast=forecast_list,
            last_close=last_close,
            generated_at=generated_at
        )
    except Exception as e:
        conn.close()
        print(f"Error generating Kronos forecast: {e}")
        return jsonify(error=f"Prediction error: {str(e)}"), 500

@app.route('/api/kronos-backtest', methods=['GET'])
def get_kronos_backtest():
    from flask import request
    import sqlite3
    import json
    
    ticker = request.args.get('ticker', '').strip().upper()
    if not ticker:
        return jsonify(error="Ticker is required"), 400
        
    if ticker.startswith("NSE:"):
        ticker = ticker[4:]
        
    # Fetch historical prices to match against forecasts (2 years history to cover older forecasts)
    history = fetch_historical_prices(ticker, range_str="2y")
    if not history:
        return jsonify(error="No historical data found to run backtest"), 404
        
    actual_closes = {}
    for i, d in enumerate(history):
        actual_closes[d["date"]] = {
            "close": float(d["close"]),
            "prev_close": float(history[i-1]["close"]) if i > 0 else None
        }
        
    # Retrieve all stored forecasts for this ticker
    conn = sqlite3.connect("scan_history.db")
    c = conn.cursor()
    c.execute(
        "SELECT id, generated_at, pred_len, forecast_json, last_close FROM kronos_forecasts WHERE ticker = ? AND (model_type = 'kronos' OR model_type IS NULL) ORDER BY id DESC",
        (ticker,)
    )
    rows = c.fetchall()
    conn.close()
    
    backtest_runs = []
    
    for row in rows:
        fid, generated_at_str, pred_len, forecast_json_str, last_close = row
        forecast_data = json.loads(forecast_json_str)
        
        comparison_points = []
        abs_errors = []
        pct_errors = []
        direction_correct = 0
        band_hits = 0
        
        for idx, item in enumerate(forecast_data):
            f_date = item["date"]
            f_close = float(item["close"])
            p10 = float(item["p10_close"])
            p90 = float(item["p90_close"])
            
            if f_date in actual_closes:
                act = actual_closes[f_date]
                act_close = act["close"]
                
                # Accuracy metrics
                err = abs(f_close - act_close)
                abs_errors.append(err)
                pct_errors.append(err / (act_close + 1e-5))
                
                # Band check
                if p10 <= act_close <= p90:
                    band_hits += 1
                    
                # Direction check
                if idx == 0:
                    f_dir = f_close > last_close
                    prev_act_close = act["prev_close"] if act["prev_close"] is not None else last_close
                    a_dir = act_close > prev_act_close
                else:
                    prev_f_close = float(forecast_data[idx-1]["close"])
                    f_dir = f_close > prev_f_close
                    prev_act_close = actual_closes[forecast_data[idx-1]["date"]]["close"] if forecast_data[idx-1]["date"] in actual_closes else act["prev_close"]
                    a_dir = act_close > (prev_act_close if prev_act_close is not None else last_close)
                    
                if f_dir == a_dir:
                    direction_correct += 1
                    
                comparison_points.append({
                    "date": f_date,
                    "forecast_close": f_close,
                    "actual_close": act_close,
                    "p10_close": p10,
                    "p90_close": p90,
                    "in_band": p10 <= act_close <= p90
                })
                
        total_days = len(comparison_points)
        if total_days > 0:
            mae = sum(abs_errors) / total_days
            mape = (sum(pct_errors) / total_days) * 100
            dir_acc = (direction_correct / total_days) * 100
            hit_rate = (band_hits / total_days) * 100
            
            backtest_runs.append({
                "id": fid,
                "generated_at": generated_at_str,
                "pred_len": pred_len,
                "last_close": last_close,
                "mae": round(mae, 2),
                "mape": round(mape, 2),
                "direction_accuracy": round(dir_acc, 1),
                "band_hit_rate": round(hit_rate, 1),
                "total_comparisons": total_days,
                "comparison_points": comparison_points
            })
            
    # If no stored forecasts yielded backtest runs, run an on-the-fly historical backtest
    if len(backtest_runs) == 0 and len(history) >= 20:
        try:
            import pandas as pd
            import numpy as np
            from datetime import datetime
            
            # Context period: up to 60 daily bars prior to the last 10 days
            target_history = history[-10:]
            context_history = history[:-10][-60:]
            
            df_input = pd.DataFrame([{
                "open": float(d["open"]),
                "high": float(d["high"]),
                "low": float(d["low"]),
                "close": float(d["close"]),
                "volume": float(d["volume"])
            } for d in context_history])
            df_input["amount"] = df_input["volume"] * df_input[["open", "high", "low", "close"]].mean(axis=1)
            
            x_timestamps = pd.to_datetime([d["date"] for d in context_history])
            y_timestamps = pd.Series(pd.to_datetime([d["date"] for d in target_history]))
            
            # Adaptive temperature using ATR% over context
            atr_pct = compute_atr_pct(context_history)
            
            T_val = max(0.5, min(0.8, 0.5 + atr_pct * 0.03))
            
            predictor = get_kronos_predictor()
            if predictor:
                raw_samples = predictor.predict(
                    df=df_input,
                    x_timestamp=pd.Series(x_timestamps),
                    y_timestamp=y_timestamps,
                    pred_len=10,
                    T=T_val,
                    top_p=0.8,
                    sample_count=20,
                    verbose=False,
                    return_samples=True
                )
                
                mean_pred = raw_samples.mean(axis=0)
                p10 = np.percentile(raw_samples, 10, axis=0)
                p90 = np.percentile(raw_samples, 90, axis=0)
                
                dates = [d["date"] for d in target_history]
                forecast_list = []
                for i in range(10):
                    forecast_list.append({
                        "date": dates[i],
                        "open": round(float(mean_pred[i, 0]), 2),
                        "high": round(float(mean_pred[i, 1]), 2),
                        "low": round(float(mean_pred[i, 2]), 2),
                        "close": round(float(mean_pred[i, 3]), 2),
                        "volume": int(mean_pred[i, 4]),
                        "p10_close": round(float(p10[i, 3]), 2),
                        "p90_close": round(float(p90[i, 3]), 2)
                    })
                
                last_close = float(context_history[-1]["close"])
                
                comparison_points = []
                abs_errors = []
                pct_errors = []
                direction_correct = 0
                band_hits = 0
                
                for idx, item in enumerate(forecast_list):
                    f_date = item["date"]
                    f_close = float(item["close"])
                    p10_val = float(item["p10_close"])
                    p90_val = float(item["p90_close"])
                    
                    act_day = target_history[idx]
                    act_close = float(act_day["close"])
                    
                    err = abs(f_close - act_close)
                    abs_errors.append(err)
                    pct_errors.append(err / (act_close + 1e-5))
                    
                    if p10_val <= act_close <= p90_val:
                        band_hits += 1
                        
                    if idx == 0:
                        f_dir = f_close > last_close
                        prev_act_close = float(context_history[-1]["close"])
                        a_dir = act_close > prev_act_close
                    else:
                        prev_f_close = float(forecast_list[idx-1]["close"])
                        f_dir = f_close > prev_f_close
                        prev_act_close = float(target_history[idx-1]["close"])
                        a_dir = act_close > prev_act_close
                        
                    if f_dir == a_dir:
                        direction_correct += 1
                        
                    comparison_points.append({
                        "date": f_date,
                        "forecast_close": f_close,
                        "actual_close": act_close,
                        "p10_close": p10_val,
                        "p90_close": p90_val,
                        "in_band": p10_val <= act_close <= p90_val
                    })
                    
                total_days = len(comparison_points)
                if total_days > 0:
                    mae = sum(abs_errors) / total_days
                    mape = (sum(pct_errors) / total_days) * 100
                    dir_acc = (direction_correct / total_days) * 100
                    hit_rate = (band_hits / total_days) * 100
                    
                    otf_run = {
                        "id": "otf_backtest",
                        "generated_at": datetime.now().isoformat(),
                        "pred_len": 10,
                        "last_close": last_close,
                        "mae": round(mae, 2),
                        "mape": round(mape, 2),
                        "direction_accuracy": round(dir_acc, 1),
                        "band_hit_rate": round(hit_rate, 1),
                        "total_comparisons": total_days,
                        "comparison_points": comparison_points
                    }
                    backtest_runs.append(otf_run)
        except Exception as e:
            print(f"Error generating on-the-fly backtest fallback: {e}")
            
    return jsonify(
        ticker=ticker,
        backtest_runs=backtest_runs[:5]
    )

@app.route('/api/ensemble-backtest', methods=['GET'])
@profile_endpoint
def get_ensemble_backtest():
    """
    GET /api/ensemble-backtest?ticker=RELIANCE&horizon=10

    Runs a walk-forward backtest over the last `horizon` trading days,
    comparing Kronos, Prophet, ARIMA, and the blended Ensemble path
    against actual closes.

    Returns per-model MAE, MAPE, directional accuracy, and band hit rate
    alongside the blended ensemble metrics.
    """
    from flask import request
    import time
    t0 = time.time()

    ticker  = request.args.get('ticker', '').strip().upper().replace('NSE:', '')
    horizon = int(request.args.get('horizon', 10))

    if not ticker:
        return jsonify({'error': 'ticker_required'}), 400
    if horizon < 3 or horizon > 20:
        return jsonify({'error': 'horizon must be between 3 and 20'}), 400

    history = fetch_historical_prices(ticker, range_str='2y')
    if not history or len(history) < horizon + 80:
        return jsonify({'error': 'insufficient_history'}), 400

    # Split history: context window vs held-out actuals
    context = history[-(horizon + 120):-horizon]
    actuals = [float(d['close']) for d in history[-horizon:]]
    actual_dates = [d['date'] for d in history[-horizon:]]
    last_context_close = float(context[-1]['close'])

    # Set up thread-safe context caching for model predictors
    model_preds = {'kronos': None, 'prophet': None, 'arima': None}
    model_errors_bt = {}

    def _run(name, fn):
        import time
        clean_t = ticker[4:] if ticker.startswith("NSE:") else ticker
        FAR_FUTURE = time.time() + 3600
        ctx_1y_key = (clean_t, '1y')
        ctx_2y_key = (clean_t, '2y')
        old_1y = _historical_prices_cache.get(ctx_1y_key)
        old_2y = _historical_prices_cache.get(ctx_2y_key)
        _historical_prices_cache[ctx_1y_key] = (FAR_FUTURE, context)
        _historical_prices_cache[ctx_2y_key] = (FAR_FUTURE, context)
        try:
            return name, fn(ticker, horizon)
        except Exception as e:
            return name, e
        finally:
            if old_1y is not None:
                _historical_prices_cache[ctx_1y_key] = old_1y
            else:
                _historical_prices_cache.pop(ctx_1y_key, None)
            if old_2y is not None:
                _historical_prices_cache[ctx_2y_key] = old_2y
            else:
                _historical_prices_cache.pop(ctx_2y_key, None)

    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [
            ex.submit(_run, 'kronos',  kronos_predict),
            ex.submit(_run, 'prophet', prophet_predict),
            ex.submit(_run, 'arima',   arima_predict),
        ]
        for fut in futs:
            name, result = fut.result(timeout=30)
            if isinstance(result, Exception):
                model_errors_bt[name] = str(result)
            else:
                model_preds[name] = result

    active = {k: v for k, v in model_preds.items() if v is not None}
    if len(active) < 2:
        return jsonify({'error': 'backtest_failed', 'details': model_errors_bt}), 500

    # Build ensemble path using current dynamic weights if available
    default_w = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}
    total_w   = sum(default_w[m] for m in active)
    weights   = {m: default_w[m] / total_w for m in active}
    blend     = ensemble_blend(
        kronos_path=model_preds.get('kronos') or [],
        prophet_path=model_preds.get('prophet') or [],
        arima_path=model_preds.get('arima') or [],
        weights=weights
    )
    active['ensemble'] = blend['ensemble_path']

    def _metrics(preds, actuals, prev_close):
        n = min(len(preds), len(actuals))
        if n == 0:
            return {}
        abs_err = [abs(preds[i] - actuals[i]) for i in range(n)]
        pct_err = [abs_err[i] / (actuals[i] + 1e-9) * 100 for i in range(n)]
        dir_hits = 0
        for i in range(n):
            p_ref = preds[i-1] if i > 0 else prev_close
            a_ref = actuals[i-1] if i > 0 else prev_close
            if (preds[i] > p_ref) == (actuals[i] > a_ref):
                dir_hits += 1
        return {
            'mae':                round(sum(abs_err) / n, 2),
            'mape':               round(sum(pct_err) / n, 2),
            'direction_accuracy': round(dir_hits / n * 100, 1),
            'n_days':             n
        }

    per_model = {
        name: _metrics(preds, actuals, last_context_close)
        for name, preds in active.items()
    }

    comparison_points = []
    for i, (date, actual) in enumerate(zip(actual_dates, actuals)):
        pt = {'date': date, 'actual': actual}
        for name, preds in active.items():
            pt[name] = round(preds[i], 2) if i < len(preds) else None
        comparison_points.append(pt)

    return jsonify({
        'ticker':             ticker,
        'horizon':            horizon,
        'per_model_metrics':  per_model,
        'comparison_points':  comparison_points,
        'model_errors':       model_errors_bt,
        'latency_ms':         round((time.time() - t0) * 1000)
    })

import statistics
import math

def calculate_backend_sector_scores(universe_stocks):
    # Group stocks by sector
    sectors_map = {}
    for s in universe_stocks:
        sec = s.get("sector")
        if not sec:
            continue
        if sec not in sectors_map:
            sectors_map[sec] = []
        sectors_map[sec].append(s)
        
    # Get all valid perf_w, perf_m, perf_3m
    universe_w = [s["perf_w"] for s in universe_stocks if s.get("perf_w") is not None]
    universe_m = [s["perf_m"] for s in universe_stocks if s.get("perf_m") is not None]
    universe_3m = [s["perf_3m"] for s in universe_stocks if s.get("perf_3m") is not None]
    
    uni_median_w = statistics.median(universe_w) if universe_w else 0.0
    uni_median_m = statistics.median(universe_m) if universe_m else 0.0
    uni_median_3m = statistics.median(universe_3m) if universe_3m else 0.0
    
    sector_scores = {}
    for sector, sector_stocks in sectors_map.items():
        count = len(sector_stocks)
        
        # 1. Relative Strength vs Universe/Market (40 points)
        w_vals = [s["perf_w"] for s in sector_stocks if s.get("perf_w") is not None]
        m_vals = [s["perf_m"] for s in sector_stocks if s.get("perf_m") is not None]
        m3_vals = [s["perf_3m"] for s in sector_stocks if s.get("perf_3m") is not None]
        
        avg_sector_w = statistics.median(w_vals) if w_vals else 0.0
        avg_sector_m = statistics.median(m_vals) if m_vals else 0.0
        avg_sector_3m = statistics.median(m3_vals) if m3_vals else 0.0
        
        diff_w = avg_sector_w - uni_median_w
        diff_m = avg_sector_m - uni_median_m
        diff_3m = avg_sector_3m - uni_median_3m
        
        combined_rs = (diff_m * 1.5) + (diff_3m * 1.0)
        rs_score = max(0.0, min(40.0, 20.0 + (combined_rs * 2.0)))
        
        # 2. Breadth: Advances vs Declines (25 points)
        advances = sum(1 for s in sector_stocks if s.get("change", 0.0) > 0.0)
        breadth_pct = (advances / count) if count > 0 else 0.5
        breadth_score = breadth_pct * 25.0
        
        # 3. Trend: close above SMA21 and SMA50 (20 points)
        in_trend = sum(1 for s in sector_stocks if s.get("close", 0.0) > s.get("SMA21", 0.0) and s.get("close", 0.0) > s.get("SMA50", 0.0))
        trend_pct = (in_trend / count) if count > 0 else 0.5
        trend_score = trend_pct * 20.0
        
        # 4. Leadership: stocks near 52W high (15 points)
        leaders = sum(1 for s in sector_stocks if s.get("price52weekhigh", 0.0) > 0.0 and s.get("close", 0.0) >= (s.get("price52weekhigh", 0.0) * 0.96))
        leadership_pct = (leaders / count) if count > 0 else 0.2
        leadership_score = leadership_pct * 15.0
        
        total_score = round(rs_score + breadth_score + trend_score + leadership_score)
        
        # Quadrant
        if diff_m > 0 and diff_w > 0:
            quadrant = 'Leading'
        elif diff_m <= 0 and diff_w > 0:
            quadrant = 'Improving'
        elif diff_m > 0 and diff_w <= 0:
            quadrant = 'Weakening'
        else:
            quadrant = 'Lagging'
            
        sector_scores[sector] = {
            "score": total_score,
            "advances": advances,
            "declines": count - advances,
            "count": count,
            "avg1W": avg_sector_w,
            "avg1M": avg_sector_m,
            "avg3M": avg_sector_3m,
            "delta1W": diff_w,
            "delta1M": diff_m,
            "quadrant": quadrant
        }
        
    return sector_scores, uni_median_w, uni_median_m, uni_median_3m

# NOTE: _rrg_snapped_today is in-memory only. App restarts will trigger
# a re-snap, but the DB INSERT uses ON CONFLICT DO UPDATE so data is safe.
_rrg_snapped_today = None
_last_snapshot_time = 0

def snapshot_rrg_week(sector_scores_dict, universe_stocks):
    global _rrg_snapped_today
    today = datetime.now().strftime('%Y-%m-%d')
    if _rrg_snapped_today == today:
        return
        
    iso_week = datetime.now().strftime('%Y-W%W')
    
    # Universe 4-week median return (benchmark)
    universe_4w = [s.get('perf_m', 0) or 0 for s in universe_stocks]
    uni_median = statistics.median(universe_4w) if universe_4w else 0.0
    
    conn = sqlite3.connect('scan_history.db')
    cursor = conn.cursor()
    
    for sector, data in sector_scores_dict.items():
        if data.get('count', 0) < 2:
            continue
            
        sector_4w = data.get('avg1M', 0) or 0.0
        
        # Use stable relative strength formula to support negative returns safely
        jdk_rs = compute_jdk_rs(sector_4w, uni_median)
        
        # Fetch last week's jdk_rs (excluding this week) to compute robust momentum
        cursor.execute(
            'SELECT jdk_rs FROM rrg_history WHERE sector = ? AND week != ? ORDER BY snapped_at DESC LIMIT 1',
            (sector, iso_week)
        )
        row = cursor.fetchone()
        prev_rs = row[0] if row else jdk_rs
        rs_momentum = jdk_rs - prev_rs
        
        # Quadrant mapping
        quadrant = compute_quadrant(jdk_rs, rs_momentum)
            
        cursor.execute('''
            INSERT INTO rrg_history (week, sector, jdk_rs, jdk_rs_momentum, score, quadrant, snapped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(week, sector) DO UPDATE SET
                jdk_rs           = excluded.jdk_rs,
                jdk_rs_momentum  = excluded.jdk_rs_momentum,
                score            = excluded.score,
                quadrant         = excluded.quadrant,
                snapped_at       = excluded.snapped_at
        ''', (iso_week, sector, jdk_rs, rs_momentum, data.get('score', 0), quadrant,
              datetime.utcnow().isoformat()))
              
    conn.commit()
    conn.close()
    _rrg_snapped_today = today


@app.route('/api/rrg/history', methods=['GET'])
def get_rrg_history_timeline():
    from flask import request
    weeks = min(int(request.args.get('weeks', 12)), 52)
    sectors_param = request.args.get('sectors', '').strip()
    sectors = [s.strip() for s in sectors_param.split(',') if s.strip()] if sectors_param else None
    
    conn = sqlite3.connect('scan_history.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cutoff = (datetime.utcnow() - timedelta(weeks=weeks)).isoformat()
    query = '''
        SELECT week, sector, jdk_rs, jdk_rs_momentum, score, quadrant
        FROM rrg_history
        WHERE snapped_at >= ?
        ORDER BY week ASC, sector ASC
    '''
    cursor.execute(query, (cutoff,))

    rows = cursor.fetchall()
    conn.close()
    
    from collections import defaultdict
    frame_map = defaultdict(list)
    for r in rows:
        if sectors and r['sector'] not in sectors:
            continue
        frame_map[r['week']].append({
            'sector': r['sector'],
            'jdk_rs': r['jdk_rs'],
            'jdk_rs_momentum': r['jdk_rs_momentum'],
            'score': r['score'],
            'quadrant': r['quadrant']
        })
        
    frames = [{'week': w, 'sectors': s} for w, s in sorted(frame_map.items())]
    return jsonify({
        'weeks': weeks,
        'generated_at': datetime.utcnow().isoformat(),
        'frames': frames
    })

@app.route('/api/rrg/snapshot', methods=['POST'])
def manual_rrg_snapshot():
    global _rrg_snapped_today, _last_snapshot_time
    now_time = time.time()
    if now_time - _last_snapshot_time < 60:
        return jsonify(error="Snapshot cooldown active. Try again in a moment."), 429
    # Set cooldown BEFORE the attempt so concurrent requests are blocked,
    # but reset to 0 on any failure so the user can retry immediately.
    _last_snapshot_time = now_time
    _rrg_snapped_today = None
    try:
        res = scan_stocks()
        res_data = res.get_json()
        if "error" in res_data:
            _last_snapshot_time = 0   # allow immediate retry on scan error
            return jsonify(error=res_data["error"]), 500
            
        universe = res_data.get("universe", [])
        if not universe:
            _last_snapshot_time = 0   # allow immediate retry on empty universe
            return jsonify(error="No universe stocks found to snap"), 500
            
        sector_scores, _, _, _ = calculate_backend_sector_scores(universe)
        snapshot_rrg_week(sector_scores, universe)
        # Invalidate the RRG response cache so the next /api/rrg-history call
        # returns fresh data instead of stale cached results (Fix #8).
        _rrg_response_cache.clear()
        return jsonify(success=True, message="RRG Snapshot saved successfully")
    except Exception as e:
        _last_snapshot_time = 0   # allow immediate retry on exception (Fix #6)
        return jsonify(error=str(e)), 500

@app.route('/api/rrg/backfill', methods=['POST'])
def rrg_backfill():
    try:
        res = scan_stocks()
        res_data = res.get_json()
        if "error" in res_data:
            return jsonify(error=res_data["error"]), 500
            
        universe = res_data.get("universe", [])
        if not universe:
            return jsonify(error="No universe stocks found to backfill"), 500
            
        # We need to map sectors to their scores
        sector_scores, _, _, _ = calculate_backend_sector_scores(universe)
        
        # 1. Fetch benchmark ^NSEI history for last 6 months
        bench_ticker = "^NSEI"
        bench_history = fetch_historical_prices(bench_ticker, "6mo")
        if not bench_history or len(bench_history) < 30:
            return jsonify(error="Unable to fetch benchmark Nifty 50 history"), 500
            
        bench_dates = [d["date"] for d in bench_history]
        bench_closes = [d["close"] for d in bench_history]
        
        # Identify weekly boundary trading days from benchmark
        # Since the loop is chronological, this overwrites and keeps the last trading day of each ISO week (i.e. Friday close)
        weeks_dates = {}
        for idx, entry in enumerate(bench_history):
            dt = datetime.strptime(entry["date"], "%Y-%m-%d")
            week_str = dt.strftime("%Y-W%W")
            weeks_dates[week_str] = (entry["date"], idx)
            
        sorted_weeks = sorted(weeks_dates.keys())
        if len(sorted_weeks) < 2:
            return jsonify(error="Insufficient benchmark history for backfill (need ≥ 2 weeks)"), 400
            
        target_weeks = sorted_weeks[-14:] # last 14 weeks to get 13 intervals
        
        # 2. Fetch sector index histories in parallel
        unique_tickers = list(set(SECTOR_INDEX_MAP.values()))
        sector_histories = {}
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(fetch_historical_prices, ticker, "6mo"): ticker for ticker in unique_tickers}
            for fut in futures:
                ticker = futures[fut]
                try:
                    sector_histories[ticker] = fut.result()
                except Exception as e:
                    print(f"[RRG Backfill] Failed for {ticker}: {e}")
                    sector_histories[ticker] = []
                
        conn = sqlite3.connect('scan_history.db')
        conn.execute('BEGIN')
        c = conn.cursor()
        
        try:
            # Clear existing history first to ensure clean backfill
            c.execute('DELETE FROM rrg_history')
            
            for sector, data in sector_scores.items():
                if data["count"] < 2:
                    continue
                    
                ticker = SECTOR_INDEX_MAP.get(sector)
                if not ticker:
                    continue
                    
                history = sector_histories.get(ticker, [])
                if not history:
                    continue
                    
                history_map = {d["date"]: d["close"] for d in history}
                
                jdk_rs_list = []
                for w_str in target_weeks:
                    if w_str not in weeks_dates:
                        continue
                    date, idx = weeks_dates[w_str]
                    if idx < 20:
                        continue
                    
                    # Prices at current week-end
                    close_now = history_map.get(date)
                    bench_now = bench_closes[idx]
                    
                    # Prices 20 trading days prior
                    prior_date = bench_dates[idx - 20]
                    close_prior = history_map.get(prior_date)
                    bench_prior = bench_closes[idx - 20]
                    
                    if close_now is not None and close_prior is not None:
                        sector_R = (close_now - close_prior) / close_prior * 100.0
                        bench_R = (bench_now - bench_prior) / bench_prior * 100.0
                        jdk_rs = compute_jdk_rs(sector_R, bench_R)
                        jdk_rs_list.append((w_str, jdk_rs, date))
                        
                # Calculate weekly momentum and upsert to DB
                for i in range(1, len(jdk_rs_list)):
                    w_str, val, date = jdk_rs_list[i]
                    prev_w_str, prev_val, prev_date = jdk_rs_list[i - 1]
                    rs_momentum = val - prev_val
                    
                    # Quadrant mapping
                    quadrant = compute_quadrant(val, rs_momentum)
                        
                    # Use UTC time equivalent of IST 16:00 close (16:00 IST = 10:30 UTC).
                    # This keeps snap_time consistent with the cutoff in get_rrg_history_timeline()
                    # which also uses datetime.utcnow().isoformat() — both are naive UTC strings.
                    # NOTE: If deploying on a UTC server this stays correct; on a local IST machine
                    # both sides are naive-UTC so ordering is preserved.
                    snap_time = (datetime.strptime(date, "%Y-%m-%d") + timedelta(hours=10, minutes=30)).isoformat()
                    
                    c.execute('''
                        INSERT OR REPLACE INTO rrg_history (week, sector, jdk_rs, jdk_rs_momentum, score, quadrant, snapped_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (w_str, sector, val, rs_momentum, data["score"], quadrant, snap_time))
                    
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
            
        # Re-snap current week to ensure today's snapshot is preserved after the backfill clear
        global _rrg_snapped_today
        _rrg_snapped_today = None
        snapshot_rrg_week(sector_scores, universe)
            
        return jsonify(success=True, message="RRG history backfilled successfully with real weekly data")
    except Exception as e:
        return jsonify(error=str(e)), 500


SECTOR_INDEX_MAP = {
    "Health Technology": "NIFTY_HLTHCARE.NS",
    "Health Services": "NIFTY_HLTHCARE.NS",
    "Finance": "NIFTY_FIN_SERVICE.NS",
    "Technology Services": "^CNXIT",
    "Electronic Technology": "^CNXIT",
    "Communications": "^CNXIT",
    "Retail Trade": "^CNXCONSUM",
    "Consumer Services": "^CNXCONSUM",
    "Consumer Durables": "^CNXCONSUM",
    "Consumer Non-Durables": "^CNXFMCG",
    "Process Industries": "^CNXMETAL",
    "Producer Manufacturing": "^CNXMETAL",
    "Non-Energy Minerals": "^CNXMETAL",
    "Utilities": "^CNXENERGY",
    "Energy Minerals": "^CNXENERGY",
    "Transportation": "^CNXINFRA",
    "Commercial Services": "^CNXINFRA",
    "Industrial Services": "^CNXINFRA"
}

_rrg_response_cache = {}
_RRG_RESPONSE_TTL = 10 * 60  # 10 minutes

@app.route('/api/rrg-history', methods=['GET'])
def get_rrg_history():
    import time
    from flask import request
    view = request.args.get('view', 'sectors').strip().lower()
    tickers_str = request.args.get('tickers', '').strip()
    
    cache_key = f"{view}:{tickers_str}"
    now = time.time()
    
    if cache_key in _rrg_response_cache:
        t_cached, cached_data = _rrg_response_cache[cache_key]
        if now - t_cached < _RRG_RESPONSE_TTL:
            return jsonify(cached_data)
            
    # Define benchmark index (Nifty 50)
    bench_ticker = "^NSEI"
    bench_history = fetch_historical_prices(bench_ticker)
    if not bench_history or len(bench_history) < 30:
        return jsonify(error="Unable to fetch benchmark Nifty 50 history"), 500
        
    bench_closes = [d["close"] for d in bench_history]
    bench_dates = [d["date"] for d in bench_history]
    
    # Identify tickers to scan
    assets = []
    if view == 'sectors':
        for sec_name, ticker in SECTOR_INDEX_MAP.items():
            # Keep unique sector-index pairs
            if not any(a["label"] == sec_name for a in assets):
                assets.append({"label": sec_name, "ticker": ticker})
    else:
        # Load tickers from query param
        tickers_str = request.args.get('tickers', '').strip()
        if tickers_str:
            tickers = [t.strip().upper() for t in tickers_str.split(',') if t.strip()]
        else:
            tickers = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "LT", "ITC"]
            
        for t in tickers:
            assets.append({"label": t, "ticker": t})
            
    # Calculate 20-day trail points relative to Benchmark
    def calculate_asset_trail(asset):
        ticker = asset["ticker"]
        label = asset["label"]
        history = fetch_historical_prices(ticker)
        if not history or len(history) < 30:
            return None
            
        history_map = {d["date"]: d["close"] for d in history}
        
        # Match dates against benchmark
        valid_indices = []
        for idx in range(len(bench_dates)):
            if idx >= 21:
                date = bench_dates[idx]
                if date in history_map:
                    valid_indices.append(idx)
                    
        # Grab last 21 matching dates (20 points + 1 prior point for momentum diff)
        target_indices = valid_indices[-21:]
        if len(target_indices) < 2:
            return None
            
        jdk_rs_list = []
        for idx in target_indices:
            date = bench_dates[idx]
            close = history_map[date]
            bench_close = bench_closes[idx]
            
            # Monthly performance (21 days ago)
            prev_date_m = bench_dates[idx - 21]
            close_m = history_map.get(prev_date_m, close)
            bench_close_m = bench_closes[idx - 21]
            
            stock_m = (close - close_m) / close_m * 100 if close_m > 0 else 0
            bench_m = (bench_close - bench_close_m) / bench_close_m * 100 if bench_close_m > 0 else 0
            
            jdk_rs = compute_jdk_rs(stock_m, bench_m)
            jdk_rs_list.append({"date": date, "rs": jdk_rs})
            
        trail_points = []
        for i in range(1, len(jdk_rs_list)):
            date = jdk_rs_list[i]["date"]
            rs = jdk_rs_list[i]["rs"]
            prev_rs = jdk_rs_list[i - 1]["rs"]
            momentum = rs - prev_rs
            
            trail_points.append({
                "date": date,
                "x": round(rs, 2),
                "y": round(momentum, 2)
            })
            
        return {
            "label": label,
            "ticker": ticker,
            "trail": trail_points
        }
        
    results = []
    # Calculate in parallel to keep scan fast
    with ThreadPoolExecutor(max_workers=8) as executor:
        for res in executor.map(calculate_asset_trail, assets):
            if res:
                results.append(res)
                
    dates_timeline = [bench_dates[i] for i in range(len(bench_dates)) if i >= 21][-20:]
    
    resp_data = {
        "view": view,
        "dates": dates_timeline,
        "data": results
    }
    
    _rrg_response_cache[cache_key] = (time.time(), resp_data)
    
    return jsonify(resp_data)


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/scan", methods=["GET"])
def scan_stocks():
    # Constructing the TradingView API payload
    # Filter for exchange == NSE and market_cap_basic >= 10B INR
    payload = {
        "filter": [
            {"left": "exchange", "operation": "equal", "right": "NSE"},
            {"left": "market_cap_basic", "operation": "greater", "right": 10000000000}
        ],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": COLUMNS,
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [0, 5000] # Set range large enough to fetch all matching NSE stocks
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.tradingview.com/"
    }
    
    try:
        response = requests.post(TRADINGVIEW_SCAN_URL, json=payload, headers=headers, timeout=15)
        if response.status_code != 200:
            return jsonify({"error": f"Failed to fetch data from TradingView. Status: {response.status_code}"}), 500
        
        result_json = response.json()
        raw_stocks = result_json.get("data", [])
        
        filtered_stocks = []
        universe_stocks = []
        total_scanned = len(raw_stocks)
        
        for stock_data in raw_stocks:
            ticker_symbol = stock_data.get("s")
            data_values = stock_data.get("d", [])
            
            if len(data_values) != len(COLUMNS):
                continue
                
            stock = dict(zip(COLUMNS, data_values))
            stock["ticker"] = ticker_symbol
            
            # Populate universe array with lightweight items for sector scoring
            try:
                universe_stocks.append({
                    "ticker": stock["clean_ticker"] if "clean_ticker" in stock else ticker_symbol.replace("NSE:", "").replace("BSE:", ""),
                    "sector": stock.get("sector"),
                    "perf_w": float(stock.get("Perf.W")) if stock.get("Perf.W") is not None else None,
                    "perf_m": float(stock.get("Perf.1M")) if stock.get("Perf.1M") is not None else None,
                    "perf_3m": float(stock.get("Perf.3M")) if stock.get("Perf.3M") is not None else None,
                    "change": float(stock.get("change")) if stock.get("change") is not None else 0.0,
                    "close": float(stock.get("close")) if stock.get("close") is not None else 0.0,
                    "SMA21": float(stock.get("SMA21")) if stock.get("SMA21") is not None else 0.0,
                    "SMA50": float(stock.get("SMA50")) if stock.get("SMA50") is not None else 0.0,
                    "price52weekhigh": float(stock.get("price_52_week_high") or 0.0),
                    "price52weeklow": float(stock.get("price_52_week_low") or 0.0),
                    "Recommend.All": float(stock.get("Recommend.All") or 0.0)
                })
            except (ValueError, TypeError):
                pass
            
            # Check for null values in fields we need for calculation
            # If any indicator is missing (None), skip
            required_calc_fields = [
                "close", "SMA10", "SMA21", "SMA50", "ATR", 
                "price_52_week_low", "average_volume", "market_cap_basic"
            ]
            if any(stock[field] is None for field in required_calc_fields):
                continue
                
            # Convert values to float/int to prevent type errors
            close = float(stock["close"])
            sma10 = float(stock["SMA10"])
            sma21 = float(stock["SMA21"])
            sma50 = float(stock["SMA50"])
            atr = float(stock["ATR"])
            low_52w = float(stock["price_52_week_low"])
            avg_vol = float(stock["average_volume"])
            mkt_cap = float(stock["market_cap_basic"])
            
            # Apply momentum filters:
            # 1. SMA(10) > SMA(21)
            if not (sma10 > sma21):
                continue
                
            # 2. SMA(21) > SMA(50)
            if not (sma21 > sma50):
                continue
                
            # 3. ATR(14) > 3% of close
            atr_pct = (atr / close) * 100
            if not (atr_pct > 3.0):
                continue
                
            # 4. Price above 52W Low by 50% or more (i.e. close >= 1.5 * low_52w)
            pct_above_low = ((close - low_52w) / low_52w) * 100
            if not (pct_above_low >= 50.0):
                continue
                
            # 5. Liquidity: Price * 30D Average Volume > 100M INR (10 Crores)
            turnover = close * avg_vol
            if not (turnover > 100000000):
                continue
                
            # Calculate additional fields for frontend
            stock["atr_pct"] = round(atr_pct, 2)
            stock["pct_above_low"] = round(pct_above_low, 2)
            stock["turnover_m"] = round(turnover / 10000000, 2) # in Crores (10 Million INR)
            stock["mkt_cap_cr"] = round(mkt_cap / 10000000, 2) # in Crores
            stock["relative_volume"] = round(float(stock["relative_volume_10d_calc"]), 2) if stock["relative_volume_10d_calc"] is not None else 0.0
            stock["perf_w"] = round(float(stock["Perf.W"]), 2) if stock["Perf.W"] is not None else 0.0
            stock["perf_m"] = round(float(stock["Perf.1M"]), 2) if stock["Perf.1M"] is not None else 0.0
            stock["perf_3m"] = round(float(stock["Perf.3M"]), 2) if stock["Perf.3M"] is not None else 0.0
            
            # Extract simple name (e.g. "RELIANCE" from "NSE:RELIANCE")
            stock["clean_ticker"] = stock["name"]
            
            # Fundamental derived fields
            stock["pe_ratio"] = round(float(stock["price_earnings_ttm"]), 2) if stock.get("price_earnings_ttm") is not None else None
            stock["ev_ebitda"] = round(float(stock["enterprise_value_ebitda_ttm"]), 2) if stock.get("enterprise_value_ebitda_ttm") is not None else None
            stock["pb_ratio"] = round(float(stock["price_book_fq"]), 2) if stock.get("price_book_fq") is not None else None
            stock["div_yield"] = round(float(stock["dividends_yield"]), 2) if stock.get("dividends_yield") is not None else None
            stock["ps_ratio"] = round(float(stock["price_sales_ratio"]), 2) if stock.get("price_sales_ratio") is not None else None
            ev_raw = float(stock["enterprise_value_fq"]) if stock.get("enterprise_value_fq") is not None else None
            stock["ev_cr"] = round(ev_raw / 10000000, 2) if ev_raw is not None else None
            fcf_raw = stock.get("free_cash_flow_ttm") if stock.get("free_cash_flow_ttm") is not None else stock.get("free_cash_flow_fy")
            fcf_raw = float(fcf_raw) if fcf_raw is not None else None
            stock["fcf_yield"] = round((fcf_raw / mkt_cap) * 100, 2) if (fcf_raw is not None and mkt_cap > 0) else None
            stock["mkt_cap_to_sales"] = stock["ps_ratio"]  # Same metric
            stock["gross_margin"] = round(float(stock["gross_margin_ttm"]), 2) if stock.get("gross_margin_ttm") is not None else None
            stock["ebitda_margin"] = round(float(stock["ebitda_margin_ttm"]), 2) if stock.get("ebitda_margin_ttm") is not None else None
            stock["roe"] = round(float(stock["return_on_equity_fq"]), 2) if stock.get("return_on_equity_fq") is not None else None
            stock["roce"] = round(float(stock["return_on_capital_employed_fq"]), 2) if stock.get("return_on_capital_employed_fq") is not None else None
            stock["roa"] = round(float(stock["return_on_assets_fq"]), 2) if stock.get("return_on_assets_fq") is not None else None
            stock["debt_to_equity"] = round(float(stock["debt_to_equity_fq"]), 2) if stock.get("debt_to_equity_fq") is not None else None
            ni_raw = stock.get("net_income_ttm") if stock.get("net_income_ttm") is not None else stock.get("net_income_fy")
            ni_raw = float(ni_raw) if ni_raw is not None else None
            stock["net_income_cr"] = round(ni_raw / 10000000, 2) if ni_raw is not None else None
            stock["fcf_cr"] = round(fcf_raw / 10000000, 2) if fcf_raw is not None else None
            # Derived Quality ratios
            stock["cfo_pat"] = round((fcf_raw * 1.15) / ni_raw * 100, 2) if (fcf_raw is not None and ni_raw is not None and ni_raw != 0) else None
            # Interest coverage - approximate using EBITDA margin and debt ratio
            if stock["ebitda_margin"] is not None and stock["debt_to_equity"] is not None and stock["debt_to_equity"] > 0:
                stock["interest_coverage"] = round(stock["ebitda_margin"] / (stock["debt_to_equity"] * 0.08) if stock["debt_to_equity"] > 0 else 99.0, 2)
            else:
                stock["interest_coverage"] = None
            
            # Earnings Date Processing
            now_ts = time.time()
            e1 = stock.get("earnings_release_date")
            e2 = stock.get("earnings_release_next_date")
            upcoming_ts = None
            
            if e1 and e1 > now_ts:
                upcoming_ts = e1
            if e2 and e2 > now_ts:
                if not upcoming_ts or e2 < upcoming_ts:
                    upcoming_ts = e2
                    
            if upcoming_ts:
                stock["upcoming_earnings"] = datetime.fromtimestamp(upcoming_ts).strftime('%Y-%m-%d')
            else:
                stock["upcoming_earnings"] = None
                
            # Compute extra fundamental and growth metrics
            compute_extra_fields(stock)
            
            filtered_stocks.append(stock)
        
        # Fetch deal symbols for catalyst scoring
        deal_symbols = set()
        try:
            raw_deals = fetch_nse_block_deals()
            for d in raw_deals.get("BLOCK_DEALS_DATA", []):
                sym = d.get("symbol", "").upper().strip()
                if sym:
                    deal_symbols.add(sym)
            for d in raw_deals.get("BULK_DEALS_DATA", []):
                sym = d.get("symbol", "").upper().strip()
                if sym:
                    deal_symbols.add(sym)
        except Exception:
            pass
        
        # Compute intraday scores for all matched stocks
        for stock in filtered_stocks:
            compute_intraday_score(stock, deal_symbols)
            compute_swing_score(stock)
            compute_mtf_confirmation(stock)
            
        # Compute historical scan metrics
        try:
            conn = sqlite3.connect('scan_history.db')
            c = conn.cursor()
            
            c.execute('SELECT DISTINCT date FROM scan_history ORDER BY date DESC')
            all_dates = [row[0] for row in c.fetchall()]
            
            history_by_ticker = {}
            c.execute('SELECT ticker, date FROM scan_history ORDER BY date DESC')
            for row in c.fetchall():
                ticker, date = row[0], row[1]
                if ticker not in history_by_ticker:
                    history_by_ticker[ticker] = []
                history_by_ticker[ticker].append(date)
                
            conn.close()
            
            twenty_days_ago = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
            
            for stock in filtered_stocks:
                ticker = stock["clean_ticker"]
                dates = history_by_ticker.get(ticker, [])
                
                if not dates:
                    stock["first_seen"] = "New"
                    stock["times_seen_20d"] = 0
                    stock["days_in_scan"] = 0
                    stock["re_entry"] = False
                else:
                    stock["first_seen"] = dates[-1]
                    stock["times_seen_20d"] = len([d for d in dates if d >= twenty_days_ago])
                    
                    consecutive = 0
                    for i, d in enumerate(all_dates):
                        if i < len(dates) and dates[i] == d:
                            consecutive += 1
                        else:
                            break
                    stock["days_in_scan"] = consecutive
                    
                    was_in_last_snapshot = (dates[0] == all_dates[0]) if all_dates else False
                    stock["re_entry"] = (len(dates) > 0) and not was_in_last_snapshot
        except Exception as db_e:
            print(f"Error computing history: {db_e}")
            for stock in filtered_stocks:
                stock["first_seen"] = "Error"
                stock["times_seen_20d"] = 0
                stock["days_in_scan"] = 0
                stock["re_entry"] = False
                
        # Run parallel Screener Intelligence setup pattern scanning
        populate_screener_intelligence(filtered_stocks)
        
        # Run setup classification and volume compression analysis
        for stock in filtered_stocks:
            classify_setup(stock)
            compute_vol_dryup(stock)
            
        # Run real-time volume alert flags evaluation
        for stock in filtered_stocks:
            try:
                close = float(stock.get("close") or 0)
                prev_close = float(stock.get("close[1]") or 0)
                volume = float(stock.get("volume") or 0)
                max_down_vol = float(stock.get("max_down_vol_10") or 0)
                vol_sma = float(stock.get("volume_sma_50") or 0)
                
                is_up_day = close > prev_close
                is_blue = bool(is_up_day and max_down_vol > 0 and volume > max_down_vol)
                stock["is_blue_bar"] = is_blue
                stock["is_green_bar"] = bool(is_up_day and vol_sma > 0 and volume > vol_sma and not is_blue)
                stock["is_orange_bar"] = bool(vol_sma > 0 and volume <= vol_sma / 5.0)
            except Exception as e_alert:
                print(f"[Volume Alerts Backend] Error evaluating alert flags for {stock.get('clean_ticker')}: {e_alert}")
                stock["is_blue_bar"] = False
                stock["is_green_bar"] = False
                stock["is_orange_bar"] = False
            
        # Hook weekly RRG snapping here
        if universe_stocks:
            try:
                sector_scores, _, _, _ = calculate_backend_sector_scores(universe_stocks)
                snapshot_rrg_week(sector_scores, universe_stocks)
            except Exception as snap_e:
                print(f"Error snapping weekly RRG during scan: {snap_e}")
                
        return jsonify({
            "total_scanned": total_scanned,
            "total_matched": len(filtered_stocks),
            "stocks": filtered_stocks,
            "deal_symbols": list(deal_symbols),
            "universe": universe_stocks
        })
        
    except Exception as e:
        print(f"TradingView live scan failed ({e}) — attempting fallback to scan_result.txt...")
        try:
            if os.path.exists("scan_result.txt"):
                for enc in ("utf-16", "utf-8"):
                    try:
                        with open("scan_result.txt", "r", encoding=enc) as f:
                            cached_data = json.load(f)
                            print("Successfully loaded scan fallback from scan_result.txt")
                            return jsonify(cached_data)
                    except Exception:
                        continue
            print("Fallback file scan_result.txt not found or failed to parse.")
        except Exception as fallback_e:
            print(f"Fallback failed: {fallback_e}")
        return jsonify({"error": f"An error occurred during scanning: {str(e)}"}), 500

@app.route("/api/save_snapshot", methods=["POST"])
def save_snapshot():
    from flask import request
    try:
        data = request.get_json() or {}
        tickers_legacy = data.get("tickers", [])
        items = data.get("items", [])
        
        # Backward compatibility if items not provided
        if not items and tickers_legacy:
            items = [{"ticker": t} for t in tickers_legacy]
            
        if not items:
            return jsonify({"error": "No items provided for snapshot"}), 400
            
        today = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        
        saved_count = 0
        for item in items:
            ticker = item.get("ticker")
            if not ticker: continue
            
            # Save legacy history
            try:
                c.execute('INSERT INTO scan_history (date, ticker) VALUES (?, ?)', (today, ticker))
            except sqlite3.IntegrityError:
                pass
                
            # Save to scan_price_log
            try:
                c.execute('''
                    INSERT INTO scan_price_log (date, ticker, close, swingband, setupLabel) 
                    VALUES (?, ?, ?, ?, ?)
                ''', (today, ticker, item.get("close", 0), item.get("swingband", ""), item.get("setupLabel", "")))
                saved_count += 1
            except sqlite3.IntegrityError:
                pass
                
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "saved_count": saved_count, "total_found": len(items), "date": today})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/backtest-summary', methods=['GET'])
def backtest_summary():
    from flask import request
    ticker = request.args.get('ticker')
    if not ticker:
        return jsonify({"error": "No ticker provided"}), 400
        
    try:
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        
        c.execute('''
            SELECT date, close 
            FROM scan_price_log 
            WHERE ticker = ? 
            ORDER BY date ASC
        ''', (ticker,))
        
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            return jsonify({"first_seen": None, "appearance_count": 0})
            
        first_date = rows[0][0]
        first_close = rows[0][1] or 0
        latest_close = rows[-1][1] or 0
        appearance_count = len(rows)
        
        max_close = max(r[1] or 0 for r in rows)
        
        return_since_first = ((latest_close - first_close) / first_close * 100) if first_close > 0 else 0
        max_gain = ((max_close - first_close) / first_close * 100) if first_close > 0 else 0
        
        return jsonify({
            "first_seen": first_date,
            "appearance_count": appearance_count,
            "latest_close": latest_close,
            "first_close": first_close,
            "return_since_first": round(return_since_first, 2),
            "max_close": max_close,
            "max_gain": round(max_gain, 2)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/fetch_symbols", methods=["POST"])
def fetch_symbols():
    from flask import request
    try:
        req_data = request.get_json() or {}
        symbols = req_data.get("symbols", [])
        if not symbols:
            return jsonify({"stocks": []})
            
        tv_tickers = [f"NSE:{s}" if not s.startswith("NSE:") else s for s in symbols]
        
        payload = {
            "filter": [],
            "options": {"lang": "en"},
            "symbols": {"query": {"types": []}, "tickers": tv_tickers},
            "columns": COLUMNS,
            "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
            "range": [0, 100]
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.tradingview.com/"
        }
        
        response = requests.post(TRADINGVIEW_SCAN_URL, json=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            return jsonify({"error": f"Failed to fetch symbols from TradingView. Status: {response.status_code}"}), 500
            
        result_json = response.json()
        raw_stocks = result_json.get("data", [])
        
        stocks_list = []
        for stock_data in raw_stocks:
            ticker_symbol = stock_data.get("s")
            data_values = stock_data.get("d", [])
            
            if len(data_values) != len(COLUMNS):
                continue
                
            stock = dict(zip(COLUMNS, data_values))
            stock["ticker"] = ticker_symbol
            
            close = float(stock["close"]) if stock["close"] is not None else 0.0
            atr = float(stock["ATR"]) if stock["ATR"] is not None else 0.0
            low_52w = float(stock["price_52_week_low"]) if stock["price_52_week_low"] is not None else 0.0
            avg_vol = float(stock["average_volume"]) if stock["average_volume"] is not None else 1.0
            mkt_cap = float(stock["market_cap_basic"]) if stock["market_cap_basic"] is not None else 0.0
            
            stock["atr_pct"] = round((atr / close) * 100, 2) if close > 0 else 0.0
            stock["pct_above_low"] = round(((close - low_52w) / low_52w) * 100, 2) if low_52w > 0 else 0.0
            stock["turnover_m"] = round((close * avg_vol) / 10000000, 2)
            stock["mkt_cap_cr"] = round(mkt_cap / 10000000, 2)
            stock["relative_volume"] = round(float(stock["relative_volume_10d_calc"]), 2) if stock["relative_volume_10d_calc"] is not None else 0.0
            stock["perf_w"] = round(float(stock["Perf.W"]), 2) if stock["Perf.W"] is not None else 0.0
            stock["perf_m"] = round(float(stock["Perf.1M"]), 2) if stock["Perf.1M"] is not None else 0.0
            stock["perf_3m"] = round(float(stock["Perf.3M"]), 2) if stock["Perf.3M"] is not None else 0.0
            stock["clean_ticker"] = stock["name"]
            
            # Fundamental derived fields
            stock["pe_ratio"] = round(float(stock["price_earnings_ttm"]), 2) if stock.get("price_earnings_ttm") is not None else None
            stock["ev_ebitda"] = round(float(stock["enterprise_value_ebitda_ttm"]), 2) if stock.get("enterprise_value_ebitda_ttm") is not None else None
            stock["pb_ratio"] = round(float(stock["price_book_fq"]), 2) if stock.get("price_book_fq") is not None else None
            stock["div_yield"] = round(float(stock["dividends_yield"]), 2) if stock.get("dividends_yield") is not None else None
            stock["ps_ratio"] = round(float(stock["price_sales_ratio"]), 2) if stock.get("price_sales_ratio") is not None else None
            ev_raw = float(stock["enterprise_value_fq"]) if stock.get("enterprise_value_fq") is not None else None
            stock["ev_cr"] = round(ev_raw / 10000000, 2) if ev_raw is not None else None
            fcf_raw = stock.get("free_cash_flow_ttm") if stock.get("free_cash_flow_ttm") is not None else stock.get("free_cash_flow_fy")
            fcf_raw = float(fcf_raw) if fcf_raw is not None else None
            stock["fcf_yield"] = round((fcf_raw / mkt_cap) * 100, 2) if (fcf_raw is not None and mkt_cap > 0) else None
            stock["mkt_cap_to_sales"] = stock["ps_ratio"]  # Same metric
            stock["gross_margin"] = round(float(stock["gross_margin_ttm"]), 2) if stock.get("gross_margin_ttm") is not None else None
            stock["ebitda_margin"] = round(float(stock["ebitda_margin_ttm"]), 2) if stock.get("ebitda_margin_ttm") is not None else None
            stock["roe"] = round(float(stock["return_on_equity_fq"]), 2) if stock.get("return_on_equity_fq") is not None else None
            stock["roce"] = round(float(stock["return_on_capital_employed_fq"]), 2) if stock.get("return_on_capital_employed_fq") is not None else None
            stock["roa"] = round(float(stock["return_on_assets_fq"]), 2) if stock.get("return_on_assets_fq") is not None else None
            stock["debt_to_equity"] = round(float(stock["debt_to_equity_fq"]), 2) if stock.get("debt_to_equity_fq") is not None else None
            ni_raw = stock.get("net_income_ttm") if stock.get("net_income_ttm") is not None else stock.get("net_income_fy")
            ni_raw = float(ni_raw) if ni_raw is not None else None
            stock["net_income_cr"] = round(ni_raw / 10000000, 2) if ni_raw is not None else None
            stock["fcf_cr"] = round(fcf_raw / 10000000, 2) if fcf_raw is not None else None
            # Derived Quality ratios
            stock["cfo_pat"] = round((fcf_raw * 1.15) / ni_raw * 100, 2) if (fcf_raw is not None and ni_raw is not None and ni_raw != 0) else None
            # Interest coverage - approximate using EBITDA margin and debt ratio
            if stock["ebitda_margin"] is not None and stock["debt_to_equity"] is not None and stock["debt_to_equity"] > 0:
                stock["interest_coverage"] = round(stock["ebitda_margin"] / (stock["debt_to_equity"] * 0.08) if stock["debt_to_equity"] > 0 else 99.0, 2)
            else:
                stock["interest_coverage"] = None
            
            # Compute extra fundamental and growth metrics
            compute_extra_fields(stock)
            
            # Compute intraday and swing score (no deals cross-ref for watchlist fetch)
            compute_intraday_score(stock)
            stock["setupLabel"] = "None"
            compute_swing_score(stock)
            compute_mtf_confirmation(stock)
            classify_setup(stock)
            compute_vol_dryup(stock)
            
            stocks_list.append(stock)
            
        return jsonify({"stocks": stocks_list})
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# Cache configuration for NSE announcements
ANNOUNCEMENTS_CACHE = {}
CACHE_TIMEOUT_SECONDS = 300  # Cache for 5 minutes

def fetch_nse_announcements(symbol=None):
    now = time.time()
    cache_key = symbol if symbol else "ALL"
    
    # Check cache
    if cache_key in ANNOUNCEMENTS_CACHE:
        cache_data = ANNOUNCEMENTS_CACHE[cache_key]
        if now - cache_data["timestamp"] < CACHE_TIMEOUT_SECONDS:
            return cache_data["data"]
            
    # Fetch from NSE
    if symbol:
        url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={symbol}"
    else:
        url = "https://www.nseindia.com/api/corporate-announcements?index=equities"
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
    }
    
    try:
        with nse_fetch_lock:
            # Double check cache inside lock
            if cache_key in ANNOUNCEMENTS_CACHE:
                cache_data = ANNOUNCEMENTS_CACHE[cache_key]
                if now - cache_data["timestamp"] < CACHE_TIMEOUT_SECONDS:
                    return cache_data["data"]
            
            with requests.Session() as s:
                # First hit the announcements page to get session cookies
                s.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", headers=headers, timeout=10)
                res = s.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                # Store in cache
                ANNOUNCEMENTS_CACHE[cache_key] = {
                    "timestamp": now,
                    "data": data
                }
                return data
            else:
                print(f"Failed to fetch {cache_key} from NSE. Status: {res.status_code}")
    except Exception as e:
        print(f"Error fetching {cache_key} from NSE: {str(e)}")
        
    # Fallback to expired cache if available
    if cache_key in ANNOUNCEMENTS_CACHE:
        return ANNOUNCEMENTS_CACHE[cache_key]["data"]
        
    return []

def classify_announcement(desc, text):
    desc_l = desc.lower() if desc else ""
    text_l = text.lower() if text else ""
    
    # Defaults
    cat = "cat-other"
    cat_name = "Other"
    imp = "imp-sentiment"
    imp_name = "Sentiment only"
    sent = "sent-neutral"
    sent_name = "🟡 Neutral"
    reason = "This is a standard corporate disclosure or newspaper publication required by listing regulations. It contains administrative or routine information without a material technical impact."
    
    # 1. Dividend
    if "dividend" in desc_l or "dividend" in text_l or "book closure" in desc_l or "book closure" in text_l or "record date" in desc_l or "record date" in text_l:
        cat = "cat-dividend"
        cat_name = "Dividend"
        imp = "imp-earnings-st"
        imp_name = "Earnings impact (short-term)"
        sent = "sent-positive"
        sent_name = "🟢 Positive"
        reason = "Dividends distribute corporate earnings directly to shareholders. This indicates positive cash flows, stable earnings, and strong management confidence in shareholder returns."
        
    # 2. Results
    elif any(x in desc_l or x in text_l for x in ["results", "financial result", "audited", "unaudited", "earnings", "balance sheet"]):
        cat = "cat-results"
        cat_name = "Results"
        imp = "imp-earnings-st"
        imp_name = "Earnings impact (short-term)"
        if any(x in desc_l or x in text_l for x in ["loss", "fall", "decline", "down", "decrease"]):
            sent = "sent-negative"
            sent_name = "🔴 Negative"
            reason = "Financial results highlight a decline, fall, decrease, or net loss in key metrics (revenue, profit, or margins), signaling short-term financial stress or operational headwinds."
        else:
            sent = "sent-positive"
            sent_name = "🟢 Positive"
            reason = "Financial results show positive revenue/profit growth and margin expansion, with no indicators of declining performance, signaling strong operational momentum."
            
    # 3. Order Win
    elif any(x in desc_l or x in text_l for x in ["order", "contract", "bagged", "secured", "won", "award"]):
        cat = "cat-order-win"
        cat_name = "Order Win"
        imp = "imp-order-book"
        imp_name = "Order book impact"
        sent = "sent-positive"
        sent_name = "🟢 Positive"
        reason = "Securing a new order, contract, or client award expands the company's order book, directly boosts future revenue visibility, and strengthens market leadership."
        
    # 4. Acquisition / Sale
    elif any(x in desc_l or x in text_l for x in ["acquisition", "acquire", "merger", "amalgamation", "takeover", "disposal", "slump sale", "disinvestment", "divestment"]):
        cat = "cat-acquisition"
        cat_name = "Acquisition"
        imp = "imp-balance-sheet"
        imp_name = "Balance sheet impact"
        sent = "sent-positive"
        sent_name = "🟢 Positive"
        reason = "Acquisitions or mergers increase business scale, acquire new technology or assets, expand geographic footprint, and signal positive inorganic growth prospects."
        
    # 5. Capex / Expansion
    elif any(x in desc_l or x in text_l for x in ["capex", "capacity", "expansion", "facility", "plant", "commission", "setting up", "inauguration"]):
        cat = "cat-capex"
        cat_name = "Capex"
        imp = "imp-earnings-lt"
        imp_name = "Earnings impact (long-term)"
        sent = "sent-positive"
        sent_name = "🟢 Positive"
        reason = "Capital expenditure for capacity expansion, new manufacturing plants, or facility commissioning indicates strong long-term demand and a growth-oriented corporate strategy."
        
    # 6. Regulatory
    elif any(x in desc_l or x in text_l for x in ["sebi", "rbi", "penalty", "fine", "warning", "show cause", "adjudication", "regulatory", "notice", "litigation", "summon"]):
        cat = "cat-regulatory"
        cat_name = "Regulatory"
        imp = "imp-governance"
        imp_name = "Governance signal"
        sent = "sent-negative"
        sent_name = "🔴 Negative"
        reason = "Regulatory actions, warnings, penalties, or compliance notices from regulatory bodies (SEBI, RBI, exchanges) represent compliance lapses or operational risks that warrant caution."
        
    # 7. Governance / Appointment
    elif any(x in desc_l or x in text_l for x in ["director", "board", "appointment", "resignation", "ceo", "cfo", "auditor", "governance", "promoter", "kmp", "key managerial"]):
        cat = "cat-governance"
        cat_name = "Governance"
        imp = "imp-governance"
        imp_name = "Governance signal"
        if "resignation" in desc_l or "resignation" in text_l:
            sent = "sent-neutral"
            sent_name = "🟡 Neutral"
            reason = "Resignations of key managerial personnel (KMPs) or auditors represent administrative changes but are classified as neutral to prompt closer review of management stability."
        else:
            sent = "sent-positive"
            sent_name = "🟢 Positive"
            reason = "Appointments of directors, CEOs, CFOs, or updates to audit committees represent standard, routine corporate governance adjustments aimed at reinforcing leadership."
            
    return cat, cat_name, imp, imp_name, sent, sent_name, reason

@app.route("/api/announcements", methods=["POST", "GET"])
def get_announcements():
    from flask import request
    try:
        symbols = []
        if request.method == "POST":
            req_data = request.get_json() or {}
            symbols = req_data.get("symbols", [])
        else:
            symbols_str = request.args.get("symbols", "")
            if symbols_str:
                symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
                
        if not symbols:
            return jsonify({"announcements": []})
            
        clean_symbols = [s.split(":")[-1] for s in symbols]
        
        all_raw_data = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_nse_announcements, sym) for sym in clean_symbols]
            for fut in futures:
                try:
                    all_raw_data.append(fut.result())
                except Exception as e:
                    print(f"Error fetching symbols: {str(e)}")
                    
        processed = []
        seen_seq_ids = set()
        
        for raw_list in all_raw_data:
            if not isinstance(raw_list, list):
                continue
            symbol_count = 0
            for item in raw_list:
                if symbol_count >= 15:
                    break
                seq_id = item.get("seq_id")
                if not seq_id or seq_id in seen_seq_ids:
                    continue
                seen_seq_ids.add(seq_id)
                
                ticker = item.get("symbol")
                desc = item.get("desc", "")
                text = item.get("attchmntText", "")
                
                cat, cat_name, imp, imp_name, sent, sent_name, reason = classify_announcement(desc, text)
                
                an_dt = item.get("an_dt", "")
                date_str = an_dt.split(" ")[0] if " " in an_dt else an_dt
                
                try:
                    dt = datetime.strptime(item.get("sort_date"), "%Y-%m-%d %H:%M:%S")
                    ts = int(dt.timestamp() * 1000)
                except Exception:
                    ts = 0
                    
                processed.append({
                    "id": str(seq_id),
                    "ticker": ticker,
                    "headline": desc if desc else text[:80],
                    "category": cat,
                    "categoryName": cat_name,
                    "impact": imp,
                    "impactName": imp_name,
                    "sentiment": sent,
                    "sentimentName": sent_name,
                    "sentimentReason": reason,
                    "date": date_str,
                    "timestamp": ts,
                    "detailContent": text,
                    "attchmntFile": item.get("attchmntFile", "")
                })
                symbol_count += 1
                
        processed.sort(key=lambda x: x["timestamp"], reverse=True)
                
        return jsonify({"announcements": processed})
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# Cache for NSE Event Calendar
EVENTS_CACHE = {}
EVENTS_CACHE_TIMEOUT = 600  # 10 minutes

def fetch_nse_events(symbols=None):
    """Fetch upcoming events from NSE Event Calendar, optionally filtered by symbol list."""
    now = time.time()
    cache_key = ",".join(sorted(symbols)) if symbols else "ALL"

    if cache_key in EVENTS_CACHE:
        cache_data = EVENTS_CACHE[cache_key]
        if now - cache_data["timestamp"] < EVENTS_CACHE_TIMEOUT:
            return cache_data["data"]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar",
    }

    try:
        with nse_fetch_lock:
            # Double check cache inside lock
            if cache_key in EVENTS_CACHE:
                cache_data = EVENTS_CACHE[cache_key]
                if now - cache_data["timestamp"] < EVENTS_CACHE_TIMEOUT:
                    return cache_data["data"]
            
            with requests.Session() as s:
                s.get(
                    "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar",
                    headers=headers,
                    timeout=12
                )
                res = s.get(
                    "https://www.nseindia.com/api/event-calendar",
                    headers=headers,
                    timeout=12
                )
            if res.status_code == 200:
                all_events = res.json()
                # Filter to symbols in watchlist if provided
                if symbols:
                    sym_set = set(s.upper() for s in symbols)
                    filtered = [e for e in all_events if e.get("symbol", "").upper() in sym_set]
                else:
                    filtered = all_events

                # Sort by date ascending (upcoming first)
                def parse_event_date(e):
                    try:
                        return datetime.strptime(e.get("date", ""), "%d-%b-%Y")
                    except Exception:
                        return datetime.max

                filtered.sort(key=parse_event_date)

                EVENTS_CACHE[cache_key] = {"timestamp": now, "data": filtered}
                return filtered
            else:
                print(f"NSE Event Calendar returned status {res.status_code}")
    except Exception as ex:
        print(f"Error fetching NSE events: {ex}")

    # Return stale cache if available
    if cache_key in EVENTS_CACHE:
        return EVENTS_CACHE[cache_key]["data"]
    return []


@app.route("/api/events", methods=["POST", "GET"])
def get_events():
    from flask import request as flask_request
    try:
        symbols = []
        if flask_request.method == "POST":
            req_data = flask_request.get_json() or {}
            symbols = req_data.get("symbols", [])
        else:
            sym_str = flask_request.args.get("symbols", "")
            if sym_str:
                symbols = [s.strip() for s in sym_str.split(",") if s.strip()]

        clean_symbols = [s.split(":")[-1].upper() for s in symbols]
        events = fetch_nse_events(clean_symbols if clean_symbols else None)

        processed = []
        for ev in events:
            raw_date = ev.get("date", "")
            # Classify purpose
            purpose = ev.get("purpose", "").lower()
            if "dividend" in purpose:
                icon = "💰"
                event_type = "Dividend"
                badge_class = "event-dividend"
            elif "result" in purpose or "financial" in purpose:
                icon = "📊"
                event_type = "Results"
                badge_class = "event-results"
            elif "agm" in purpose or "annual general" in purpose:
                icon = "🏛️"
                event_type = "AGM"
                badge_class = "event-agm"
            elif "buyback" in purpose:
                icon = "🔄"
                event_type = "Buyback"
                badge_class = "event-buyback"
            elif "split" in purpose or "bonus" in purpose:
                icon = "✂️"
                event_type = "Corporate Action"
                badge_class = "event-corp-action"
            elif "rights" in purpose:
                icon = "📋"
                event_type = "Rights Issue"
                badge_class = "event-rights"
            else:
                icon = "📅"
                event_type = "Board Meeting"
                badge_class = "event-board"

            processed.append({
                "symbol": ev.get("symbol", ""),
                "company": ev.get("company", ""),
                "purpose": ev.get("purpose", ""),
                "description": ev.get("bm_desc", ""),
                "date": raw_date,
                "icon": icon,
                "eventType": event_type,
                "badgeClass": badge_class,
            })

        return jsonify({"events": processed})
    except Exception as e:
        return jsonify({"error": str(e), "events": []}), 500


# Cache for Bulk/Block Deals
DEALS_CACHE = {}
DEALS_CACHE_TIMEOUT = 300  # 5 minutes (deals data refreshes during market hours)


def fetch_nse_block_deals():
    """Fetch today's NSE bulk and block deals from snapshot-capital-market-largedeal."""
    now = time.time()
    cache_key = "snapshot_deals"

    if cache_key in DEALS_CACHE:
        cache_data = DEALS_CACHE[cache_key]
        if now - cache_data["timestamp"] < DEALS_CACHE_TIMEOUT:
            return cache_data["data"]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/market-data/bulk-deal-watch",
    }

    try:
        with nse_fetch_lock:
            # Double check cache inside lock
            if cache_key in DEALS_CACHE:
                cache_data = DEALS_CACHE[cache_key]
                if now - cache_data["timestamp"] < DEALS_CACHE_TIMEOUT:
                    return cache_data["data"]
            
            with requests.Session() as s:
                s.get("https://www.nseindia.com/market-data/bulk-deal-watch", headers=headers, timeout=12)
                res = s.get("https://www.nseindia.com/api/snapshot-capital-market-largedeal", headers=headers, timeout=12)
            if res.status_code == 200:
                raw = res.json()
                DEALS_CACHE[cache_key] = {"timestamp": now, "data": raw}
                return raw
            else:
                print(f"NSE large-deal snapshot returned {res.status_code}")
    except Exception as ex:
        print(f"Error fetching snapshot large deals: {ex}")

    # Stale cache fallback
    if cache_key in DEALS_CACHE:
        return DEALS_CACHE[cache_key]["data"]
    return {}


@app.route("/api/deals", methods=["POST", "GET"])
def get_deals():
    from flask import request as flask_request
    try:
        symbols = []
        if flask_request.method == "POST":
            req_data = flask_request.get_json() or {}
            symbols = req_data.get("symbols", [])
        else:
            sym_str = flask_request.args.get("symbols", "")
            if sym_str:
                symbols = [s.strip() for s in sym_str.split(",") if s.strip()]

        clean_symbols = set(s.split(":")[-1].upper() for s in symbols)

        raw = fetch_nse_block_deals()
        as_on_date = raw.get("as_on_date", "")

        def clean_float(val):
            if val is None:
                return 0.0
            try:
                return float(str(val).replace(",", "").strip())
            except:
                return 0.0

        def clean_int(val):
            if val is None:
                return 0
            try:
                return int(str(val).replace(",", "").strip())
            except:
                return 0

        processed = []

        # 1. Process Block Deals
        for deal in raw.get("BLOCK_DEALS_DATA", []):
            sym = deal.get("symbol", "").upper().strip()
            if not sym:
                continue
            if clean_symbols and sym not in clean_symbols:
                continue

            qty = clean_int(deal.get("qty"))
            price = clean_float(deal.get("watp"))
            value_cr = round((qty * price) / 10_000_000, 2)

            # Classify deal size
            if value_cr >= 50:
                deal_size = "Large"
                size_class = "deal-large"
            elif value_cr >= 10:
                deal_size = "Medium"
                size_class = "deal-medium"
            else:
                deal_size = "Small"
                size_class = "deal-small"

            processed.append({
                "symbol": sym,
                "clientName": deal.get("clientName", ""),
                "buySell": deal.get("buySell", ""),
                "dealType": "Block Deal",
                "price": price,
                "volume": qty,
                "valueCr": value_cr,
                "dealSize": deal_size,
                "sizeClass": size_class,
                "tradeDate": deal.get("date", as_on_date),
                "exchange": "NSE",
                "source": "NSE Block Deal Watch",
            })

        # 2. Process Bulk Deals
        for deal in raw.get("BULK_DEALS_DATA", []):
            sym = deal.get("symbol", "").upper().strip()
            if not sym:
                continue
            if clean_symbols and sym not in clean_symbols:
                continue

            qty = clean_int(deal.get("qty"))
            price = clean_float(deal.get("watp"))
            value_cr = round((qty * price) / 10_000_000, 2)

            # Classify deal size
            if value_cr >= 50:
                deal_size = "Large"
                size_class = "deal-large"
            elif value_cr >= 10:
                deal_size = "Medium"
                size_class = "deal-medium"
            else:
                deal_size = "Small"
                size_class = "deal-small"

            processed.append({
                "symbol": sym,
                "clientName": deal.get("clientName", ""),
                "buySell": deal.get("buySell", ""),
                "dealType": "Bulk Deal",
                "price": price,
                "volume": qty,
                "valueCr": value_cr,
                "dealSize": deal_size,
                "sizeClass": size_class,
                "tradeDate": deal.get("date", as_on_date),
                "exchange": "NSE",
                "source": "NSE Bulk Deal Watch",
            })

        # Sort by value descending
        processed.sort(key=lambda x: x["valueCr"], reverse=True)

        total_count = len(raw.get("BLOCK_DEALS_DATA", [])) + len(raw.get("BULK_DEALS_DATA", []))

        return jsonify({
            "deals": processed,
            "tradeDate": as_on_date,
            "marketStatus": "Normal Market" if total_count > 0 else "No Deals Available",
            "totalDealsToday": total_count,
            "filteredCount": len(processed)
        })
    except Exception as e:
        return jsonify({"error": str(e), "deals": []}), 500

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

NEWS_CACHE = {}
NEWS_CACHE_TIMEOUT = 900  # 15 mins

def fetch_google_news(ticker):
    now = time.time()
    if ticker in NEWS_CACHE:
        if now - NEWS_CACHE[ticker]["timestamp"] < NEWS_CACHE_TIMEOUT:
            return NEWS_CACHE[ticker]["data"]
            
    query = urllib.parse.quote(f"{ticker} NSE India OR {ticker} stock")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    
    news_list = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
        
        root = ET.fromstring(xml_data)
        channel = root.find('channel')
        if channel:
            items = channel.findall('item')
            from email.utils import parsedate_to_datetime
            import datetime
            
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            
            for item in items:
                pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
                dt = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
                
                # Filter out news older than 30 days
                if pub_date:
                    try:
                        dt = parsedate_to_datetime(pub_date)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=datetime.timezone.utc)
                        if (now_utc - dt).days > 30:
                            continue
                    except Exception:
                        pass # If parsing fails, we'll keep it
                
                title = item.find('title').text if item.find('title') is not None else ''
                link = item.find('link').text if item.find('link') is not None else ''
                source = item.find('source').text if item.find('source') is not None else ''
                
                news_list.append({
                    'title': title,
                    'link': link,
                    'pub_date': pub_date,
                    'source': source,
                    '_dt': dt
                })
                
                if len(news_list) >= 8:
                    break
                    
        # Sort by latest date first, then remove the temporary _dt key
        news_list.sort(key=lambda x: x['_dt'], reverse=True)
        for news in news_list:
            news.pop('_dt', None)
                
        NEWS_CACHE[ticker] = {"timestamp": now, "data": news_list}
    except Exception as e:
        print(f"Error fetching news for {ticker}: {e}")
        if ticker in NEWS_CACHE:
            return NEWS_CACHE[ticker]["data"]
            
    return news_list

@app.route("/api/news", methods=["GET"])
def get_news():
    from flask import request as flask_request
    symbol = flask_request.args.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"error": "Symbol required", "news": []}), 400
        
    # strip "NSE:" if present
    if symbol.startswith("NSE:"):
        symbol = symbol[4:]
        
    articles = fetch_google_news(symbol)
    return jsonify({"symbol": symbol, "news": articles})

@app.route('/api/breadth-snapshot', methods=['POST'])
def save_breadth_snapshot():
    from flask import request
    d = request.get_json() or {}
    today, now_time = datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%H:%M')
    try:
        conn = sqlite3.connect('scan_history.db')
        conn.cursor().execute(
            "INSERT OR REPLACE INTO breadth_history VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (today, now_time, d.get('advances',0), d.get('declines',0), d.get('unchanged',0),
             d.get('pctAboveSMA21',0), d.get('pctAboveSMA50',0), d.get('pctNear52High',0),
             d.get('avgRecommend',0), d.get('regimeScore',0), d.get('regimeBand','Neutral'))
        )
        conn.commit(); conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/breadth-history', methods=['GET'])
def get_breadth_history():
    from flask import request
    try:
        limit = int(request.args.get('limit', 30))
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute("SELECT date,time,advances,declines,pct_sma21,pct_sma50,"
                  "pct_52high,regime_score,regime_band,avg_recommend FROM breadth_history "
                  "ORDER BY date DESC, time DESC LIMIT ?", (limit,))
        rows = c.fetchall(); conn.close()
        cols = ['date','time','advances','declines','pctAboveSMA21',
                'pctAboveSMA50','pctNear52High','regimeScore','regimeBand','avgRecommend']
        return jsonify(history=[dict(zip(cols, r)) for r in rows])
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/watchlist', methods=['GET'])
def get_watchlist():
    try:
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute("SELECT id, name FROM watchlist_sections ORDER BY position ASC, id ASC")
        sections = c.fetchall()
        
        result = []
        for sec_id, sec_name in sections:
            c.execute("SELECT ticker FROM watchlist_items WHERE section_id = ? ORDER BY position ASC, id ASC", (sec_id,))
            tickers = [r[0] for r in c.fetchall()]
            result.append({
                "id": sec_id,
                "name": sec_name,
                "stocks": tickers
            })
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify(error=str(e)), 500

def build_ranking_entry(ticker, bias, score, metrics, cache_hit):
    return {
        "ticker": ticker,
        "rank": None,  # assigned post-sort
        "predicted_return_pct": metrics.get("return_pct") if metrics else None,
        "ai_forecast_bias": bias,
        "ai_confidence_score": score,
        "forecast_metrics": metrics or {},
        "cache_hit": cache_hit
    }

def _run_kronos_for_ticker(ticker, pred_len):
    """
    Runs Kronos forecast for a single ticker. Checks memory cache and SQLite db cache first.
    Returns: build_ranking_entry(ticker, bias, score, metrics, cache_hit)
    """
    import threading
    p_bias = get_cached_pattern_bias(ticker)
    extra_ctx = {"pattern_bias": p_bias}
    cache_key = (ticker, pred_len)
    is_duplicate = False
    
    with _in_progress_lock_mutex:
        if cache_key in _in_progress_locks:
            event = _in_progress_locks[cache_key]
            is_duplicate = True
        else:
            event = threading.Event()
            _in_progress_locks[cache_key] = event
            is_duplicate = False
            
    if is_duplicate:
        event.wait()
        mem_cached = _get_kronos_cache(ticker)
        if mem_cached:
            bias, score, forecast_list, forecast_metrics = mem_cached
            try:
                history = fetch_historical_prices(ticker, range_str="6mo")
                if history:
                    last_close = float(history[-1]["close"])
                    sliced_forecast = forecast_list[:pred_len]
                    b, s, m = compute_forecast_metrics(sliced_forecast, last_close, history, extra_context=extra_ctx)
                    return build_ranking_entry(ticker, b, s, m, cache_hit=True)
            except Exception:
                pass

    try:
        import sqlite3
        import json
        import pandas as pd
        import numpy as np
        from datetime import datetime

        # Load history first (uses 15-minute global TTL cache inside fetch_historical_prices)
        history = fetch_historical_prices(ticker, range_str="6mo")
        if not history or len(history) < 10:
            return build_ranking_entry(ticker, None, 0, {}, cache_hit=False)

        last_close = float(history[-1]["close"])
        last_date_str = history[-1]["date"]

        # 1. Check memory cache (from setup-analysis, which is 10 days)
        mem_cached = _get_kronos_cache(ticker)
        if mem_cached:
            bias, score, forecast_list, forecast_metrics = mem_cached
            if len(forecast_list) >= pred_len:
                sliced_forecast = forecast_list[:pred_len]
                b, s, m = compute_forecast_metrics(sliced_forecast, last_close, history, extra_context=extra_ctx)
                return build_ranking_entry(ticker, b, s, m, cache_hit=True)

        # 2. Check Database Cache
        conn = sqlite3.connect("scan_history.db")
        c = conn.cursor()
        c.execute(
            "SELECT forecast_json, last_close, generated_at FROM kronos_forecasts WHERE ticker = ? AND pred_len = ? AND (model_type = 'kronos' OR model_type IS NULL) ORDER BY id DESC LIMIT 1",
            (ticker, pred_len)
        )
        db_row = c.fetchone()
        
        if db_row:
            stored_forecast_json, db_last_close, generated_at_str = db_row
            try:
                gen_time = datetime.fromisoformat(generated_at_str)
                if (datetime.now() - gen_time).total_seconds() < 4 * 3600:
                    conn.close()
                    forecast_list = json.loads(stored_forecast_json)
                    b, s, m = compute_forecast_metrics(forecast_list, db_last_close, history, extra_context=extra_ctx)
                    _set_kronos_cache(ticker, b, s, forecast_list, m)
                    return build_ranking_entry(ticker, b, s, m, cache_hit=True)
            except Exception:
                pass

        # 3. Live Inference
        predictor = get_kronos_predictor()
        if not predictor:
            if db_row: # Fallback to stale db cache if available
                conn.close()
                forecast_list = json.loads(stored_forecast_json)
                b, s, m = compute_forecast_metrics(forecast_list, db_last_close, history, extra_context=extra_ctx)
                return build_ranking_entry(ticker, b, s, m, cache_hit=True)
            conn.close()
            return build_ranking_entry(ticker, None, 0, {}, cache_hit=False)

        # Prepare inputs using the last 60 bars for fast inference context
        history_slice = history[-60:]
        df_input = pd.DataFrame([{
            "open": float(d["open"]),
            "high": float(d["high"]),
            "low": float(d["low"]),
            "close": float(d["close"]),
            "volume": float(d["volume"])
        } for d in history_slice])
        df_input["amount"] = df_input["volume"] * df_input[["open", "high", "low", "close"]].mean(axis=1)

        x_timestamps = pd.to_datetime([d["date"] for d in history_slice])
        y_timestamps = generate_next_trading_days(last_date_str, pred_len)

        atr_pct = compute_atr_pct(history)
        T_val = max(0.5, min(0.8, 0.5 + atr_pct * 0.03))

        with kronos_inference_lock:
            raw_samples = predictor.predict(
                df=df_input,
                x_timestamp=pd.Series(x_timestamps),
                y_timestamp=y_timestamps,
                pred_len=pred_len,
                T=T_val,
                top_p=0.8,
                sample_count=10,
                verbose=False,
                return_samples=True
            )

        mean_pred = raw_samples.mean(axis=0)
        p10 = np.percentile(raw_samples, 10, axis=0)
        p90 = np.percentile(raw_samples, 90, axis=0)

        dates = [d.strftime("%Y-%m-%d") for d in y_timestamps]
        forecast_list = []
        for i in range(pred_len):
            forecast_list.append({
                "date": dates[i],
                "open": round(float(mean_pred[i, 0]), 2),
                "high": round(float(mean_pred[i, 1]), 2),
                "low": round(float(mean_pred[i, 2]), 2),
                "close": round(float(mean_pred[i, 3]), 2),
                "volume": int(mean_pred[i, 4]),
                "p10_close": round(float(p10[i, 3]), 2),
                "p90_close": round(float(p90[i, 3]), 2)
            })

        # Save to database
        generated_at = datetime.now().isoformat()
        forecast_json_str = json.dumps(forecast_list)
        c.execute(
            "INSERT INTO kronos_forecasts (ticker, generated_at, pred_len, forecast_json, last_close, model_type) VALUES (?, ?, ?, ?, ?, 'kronos')",
            (ticker, generated_at, pred_len, forecast_json_str, last_close)
        )
        conn.commit()
        conn.close()

        # Compute metrics
        b, s, m = compute_forecast_metrics(forecast_list, last_close, history, extra_context=extra_ctx)
        _set_kronos_cache(ticker, b, s, forecast_list, m)
        return build_ranking_entry(ticker, b, s, m, cache_hit=False)

    except Exception as ex:
        print(f"[Kronos Batch] Live forecast error for {ticker}: {ex}")
        try:
            conn.close()
        except Exception:
            pass
        return build_ranking_entry(ticker, None, 0, {}, cache_hit=False)
    finally:
        with _in_progress_lock_mutex:
            if not is_duplicate:
                event.set()
                _in_progress_locks.pop(cache_key, None)

def get_ensemble_conviction_label(ticker: str) -> str:
    """
    Returns cached ensemble conviction for `ticker` if available in the
    kronos_forecasts table (avoids re-running the full ensemble just for sort).
    """
    try:
        conn = get_db_connection()
        row = conn.execute(
            """SELECT forecast_json FROM kronos_forecasts
               WHERE ticker = ? AND model_type = 'ensemble'
               ORDER BY generated_at DESC LIMIT 1""",
            (ticker,)
        ).fetchone()
        conn.close()
        if row:
            import json
            data = json.loads(row['forecast_json'])
            return data.get('conviction', 'UNKNOWN')
    except Exception as e:
        print(f"[BatchSort] Error getting conviction: {e}")
    return 'UNKNOWN'

@app.route('/api/watchlist/kronos-ranking', methods=['GET'])
def get_watchlist_kronos_ranking():
    from flask import request
    import sqlite3
    from datetime import datetime
    from concurrent.futures import ThreadPoolExecutor

    section_id = request.args.get('section_id', '').strip()
    pred_len = request.args.get('pred_len', '5').strip()
    try:
        pred_len = int(pred_len)
    except ValueError:
        pred_len = 5

    if pred_len not in [3, 5, 10]:
        pred_len = 5

    try:
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        
        # 1. Fetch the sections and tickers
        if section_id:
            c.execute("SELECT id, name FROM watchlist_sections WHERE id = ?", (section_id,))
            sections = c.fetchall()
            if not sections:
                conn.close()
                return jsonify(error="Section not found"), 404
        else:
            c.execute("SELECT id, name FROM watchlist_sections ORDER BY position ASC, id ASC")
            sections = c.fetchall()

        result_sections = []
        for sec_id, sec_name in sections:
            c.execute("SELECT ticker FROM watchlist_items WHERE section_id = ? ORDER BY position ASC, id ASC", (sec_id,))
            tickers = [r[0] for r in c.fetchall()]
            
            # If no tickers in this section, append empty rankings
            if not tickers:
                result_sections.append({
                    "id": sec_id,
                    "name": sec_name,
                    "rankings": []
                })
                continue

            # Run parallel forecasts (capped at 8 workers)
            with ThreadPoolExecutor(max_workers=8) as executor:
                rankings = list(executor.map(lambda t: _run_kronos_for_ticker(t, pred_len), tickers))

            # Sort rankings: 
            # 1. Primary: Valid forecast first, then composite score descending:
            #    composite_score = (ai_confidence_score * 0.6) + (bias_weight * 0.4)
            # 2. Secondary: conviction order (HIGH -> MODERATE -> LOW -> UNKNOWN)
            CONVICTION_ORDER = {'HIGH': 0, 'MODERATE': 1, 'LOW': 2, 'UNKNOWN': 3}
            BIAS_WEIGHTS = {
                'Strong Breakout': 100,
                'Bullish Continuation': 75,
                'Sideways Consolidation': 50,
                'Bearish Pressure': 25,
                'Strong Downtrend': 0
            }
            def sort_key(item):
                bias = item.get("ai_forecast_bias")
                conf = item.get("ai_confidence_score", 0) or 0
                if bias is None:
                    return (True, 0, 3) # Push failures to bottom
                
                bias_score = BIAS_WEIGHTS.get(bias, 50)
                composite_score = (conf * 0.6) + (bias_score * 0.4)
                
                t_clean = item.get("ticker", "")
                if t_clean.startswith("NSE:"):
                    t_clean = t_clean[4:]
                conv = get_ensemble_conviction_label(t_clean)
                conv_score = CONVICTION_ORDER.get(conv, 3)
                return (False, -composite_score, conv_score)

            rankings.sort(key=sort_key)

            # Assign rank
            for idx, item in enumerate(rankings):
                item["rank"] = idx + 1

            missing_count = sum(1 for item in rankings if item.get("ai_forecast_bias") is None)
            result_sections.append({
                "id": sec_id,
                "name": sec_name,
                "rankings": rankings,
                "partial": missing_count > 0,
                "missing_count": missing_count
            })

        conn.close()
        
        total_missing = sum(s.get("missing_count", 0) for s in result_sections)
        return jsonify({
            "generated_at": datetime.now().isoformat(),
            "pred_len": pred_len,
            "sections": result_sections,
            "partial": total_missing > 0,
            "missing_count": total_missing
        })

    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        print(f"[Kronos Batch Route] Error: {e}")
        return jsonify(error=str(e)), 500

@app.route('/api/watchlist/sections/reorder', methods=['PUT'])
def reorder_watchlist_sections():
    from flask import request
    import sqlite3
    try:
        data = request.get_json() or {}
        order = data.get('order')
        if not order or not isinstance(order, list):
            return jsonify(error="order (list) is required"), 400
            
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        for idx, sec_id in enumerate(order):
            c.execute("UPDATE watchlist_sections SET position = ? WHERE id = ?", (idx, sec_id))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/watchlist/sections/<section_id>/reorder', methods=['PUT'])
def reorder_watchlist_items(section_id):
    from flask import request
    import sqlite3
    try:
        data = request.get_json() or {}
        stocks = data.get('stocks')
        if stocks is None or not isinstance(stocks, list):
            return jsonify(error="stocks (list) is required"), 400
            
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        for idx, ticker in enumerate(stocks):
            c.execute("UPDATE watchlist_items SET position = ? WHERE section_id = ? AND ticker = ?", (idx, section_id, ticker.upper()))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/watchlist/sections', methods=['POST'])
def create_watchlist_section():
    from flask import request
    try:
        data = request.get_json() or {}
        sec_id = data.get('id')
        sec_name = data.get('name')
        if not sec_id or not sec_name:
            return jsonify(error="id and name are required"), 400
            
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO watchlist_sections (id, name) VALUES (?, ?)", (sec_id, sec_name))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/watchlist/sections/<sec_id>', methods=['PUT'])
def rename_watchlist_section(sec_id):
    from flask import request
    try:
        data = request.get_json() or {}
        sec_name = data.get('name')
        if not sec_name:
            return jsonify(error="name is required"), 400
            
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute("UPDATE watchlist_sections SET name = ? WHERE id = ?", (sec_name, sec_id))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/watchlist/sections/<sec_id>', methods=['DELETE'])
def delete_watchlist_section(sec_id):
    try:
        conn = sqlite3.connect('scan_history.db')
        conn.execute("PRAGMA foreign_keys = ON;")
        c = conn.cursor()
        c.execute("DELETE FROM watchlist_sections WHERE id = ?", (sec_id,))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/watchlist/items', methods=['POST'])
def add_watchlist_item():
    from flask import request
    try:
        data = request.get_json() or {}
        sec_id = data.get('section_id')
        ticker = data.get('ticker')
        if not sec_id or not ticker:
            return jsonify(error="section_id and ticker are required"), 400
            
        conn = sqlite3.connect('scan_history.db')
        conn.execute("PRAGMA foreign_keys = ON;")
        c = conn.cursor()
        c.execute("SELECT COALESCE(MAX(position), 0) FROM watchlist_items WHERE section_id = ?", (sec_id,))
        max_pos = c.fetchone()[0]
        c.execute("INSERT OR IGNORE INTO watchlist_items (section_id, ticker, position) VALUES (?, ?, ?)", (sec_id, ticker.upper(), max_pos + 1))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/watchlist/items', methods=['DELETE'])
def delete_watchlist_item():
    from flask import request
    try:
        data = request.get_json() or {}
        sec_id = data.get('section_id')
        ticker = data.get('ticker')
        if not sec_id or not ticker:
            return jsonify(error="section_id and ticker are required"), 400
            
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute("DELETE FROM watchlist_items WHERE section_id = ? AND ticker = ?", (sec_id, ticker.upper()))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/journal', methods=['GET'])
def get_journal():
    from flask import request
    conn = None
    try:
        status_filter = request.args.get('status', '').strip().lower()
        limit = request.args.get('limit', '').strip()
        offset = request.args.get('offset', '').strip()
        
        query = """
            SELECT id, ticker, name, date, setupLabel, swingband, entry, stop, 
                   target1, target2, target3, riskAmount, qty, status, 
                   exitPrice, exitDate, pnl, rAchieved, notes 
            FROM trade_journal
        """
        where_clauses = []
        params = []
        
        if status_filter:
            where_clauses.append("LOWER(status) = ?")
            params.append(status_filter)
            
        if where_clauses:
            query += f" WHERE {' AND '.join(where_clauses)}"
            
        query += " ORDER BY id DESC"
        
        if limit:
            try:
                limit_val = int(limit)
                query += " LIMIT ?"
                params.append(limit_val)
                if offset:
                    try:
                        offset_val = int(offset)
                        query += " OFFSET ?"
                        params.append(offset_val)
                    except ValueError:
                        pass
            except ValueError:
                pass

        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute(query, tuple(params))
        rows = c.fetchall()
        conn.close()
        conn = None
        
        cols = ['id', 'ticker', 'name', 'date', 'setupLabel', 'swingband', 'entry', 'stop', 
                'target1', 'target2', 'target3', 'riskAmount', 'qty', 'status', 
                'exitPrice', 'exitDate', 'pnl', 'rAchieved', 'notes']
        trades = [dict(zip(cols, r)) for r in rows]
        return jsonify(trades)
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/journal', methods=['POST'])
def create_journal_entry():
    from flask import request
    conn = None
    try:
        data = request.get_json() or {}
        trade_id = data.get('id')
        if not trade_id:
            return jsonify(error="id is required"), 400
            
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        
        c.execute("SELECT id FROM trade_journal WHERE id = ?", (trade_id,))
        if c.fetchone():
            conn.close()
            conn = None
            return jsonify(error="Trade already exists. Use PUT to update."), 409
            
        c.execute("""
            INSERT OR IGNORE INTO trade_journal (
                id, ticker, name, date, setupLabel, swingband, entry, stop, 
                target1, target2, target3, riskAmount, qty, status, 
                exitPrice, exitDate, pnl, rAchieved, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id, data.get('ticker'), data.get('name'), data.get('date'),
            data.get('setupLabel'), data.get('swingband'), data.get('entry', 0.0),
            data.get('stop', 0.0), data.get('target1', 0.0), data.get('target2', 0.0),
            data.get('target3', 0.0), data.get('riskAmount', 0.0), data.get('qty', 0),
            data.get('status', 'open'), data.get('exitPrice'), data.get('exitDate'),
            data.get('pnl'), data.get('rAchieved'), data.get('notes', '')
        ))
        conn.commit()
        conn.close()
        conn = None
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/journal/<trade_id>', methods=['PUT'])
def update_journal_entry(trade_id):
    from flask import request
    try:
        data = request.get_json() or {}
        
        if 'id' in data and data['id'] != trade_id:
            return jsonify(error="Trade ID mismatch between URL and body"), 400
            
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        
        # Calculate server-side P&L and R-Achieved when exitPrice is provided
        if 'exitPrice' in data and data['exitPrice'] is not None and str(data['exitPrice']).strip() != '':
            # Fetch original trade fields
            c.execute("SELECT entry, qty, stop FROM trade_journal WHERE id = ?", (trade_id,))
            orig = c.fetchone()
            if orig:
                entry_price, qty, stop = orig
                
                entry_val = data.get('entry')
                if entry_val is None:
                    entry_val = entry_price or 0.0
                entry_price = float(entry_val)

                qty_val = data.get('qty')
                if qty_val is None:
                    qty_val = qty or 0
                qty = int(qty_val)

                stop_val = data.get('stop')
                if stop_val is None:
                    stop_val = stop or 0.0
                stop = float(stop_val)

                exit_price = float(data['exitPrice'])
                pnl, r_achieved = compute_pnl_and_r(entry_price, stop, qty, exit_price, risk_amount=data.get('riskAmount'))
                
                data['pnl'] = pnl
                data['rAchieved'] = r_achieved
                data['status'] = 'closed'
        
        type_map = {
            'qty': int,
            'entry': float,
            'stop': float,
            'target1': float,
            'target2': float,
            'target3': float,
            'riskAmount': float,
            'exitPrice': float,
            'pnl': float,
            'rAchieved': float
        }
        
        fields = []
        params = []
        for key in ['status', 'exitPrice', 'exitDate', 'pnl', 'rAchieved', 'notes', 'entry', 'stop', 'target1', 'target2', 'target3', 'riskAmount', 'qty', 'ticker', 'name', 'date', 'setupLabel', 'swingband']:
            if key in data:
                val = data[key]
                if val is not None and str(val).strip() != '':
                    if key in type_map:
                        try:
                            val = type_map[key](val)
                        except (ValueError, TypeError):
                            conn.close()
                            return jsonify(error=f"Invalid value type for {key}"), 400
                else:
                    val = None
                
                fields.append(f"{key} = ?")
                params.append(val)
                
        if not fields:
            conn.close()
            return jsonify(error="No fields to update"), 400
            
        params.append(trade_id)
        query = f"UPDATE trade_journal SET {', '.join(fields)} WHERE id = ?"
        c.execute(query, tuple(params))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return jsonify(error=str(e)), 500

@app.route('/api/journal/<trade_id>', methods=['DELETE'])
def delete_journal_entry(trade_id):
    conn = None
    try:
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute("DELETE FROM trade_journal WHERE id = ?", (trade_id,))
        if c.rowcount == 0:
            conn.close()
            conn = None
            return jsonify(error="Trade not found"), 404
        conn.commit()
        conn.close()
        conn = None
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/migrate-local-data', methods=['POST'])
def migrate_local_data():
    from flask import request
    conn = None
    try:
        data = request.get_json() or {}
        sections = data.get('watchlist_sections', [])
        journal = data.get('journal', [])
        
        conn = sqlite3.connect('scan_history.db')
        conn.execute("PRAGMA foreign_keys = ON;")
        c = conn.cursor()
        
        # Migrate watchlists
        for sec in sections:
            sec_id = sec.get('id')
            sec_name = sec.get('name')
            if sec_id and sec_name:
                c.execute("INSERT OR IGNORE INTO watchlist_sections (id, name) VALUES (?, ?)", (sec_id, sec_name))
                for idx, sym in enumerate(sec.get('stocks', [])):
                    if sym:
                        c.execute("INSERT OR IGNORE INTO watchlist_items (section_id, ticker, position) VALUES (?, ?, ?)", (sec_id, sym.upper(), idx))
                        
        # Migrate journal
        for entry in journal:
            trade_id = entry.get('id')
            if trade_id:
                c.execute("""
                    INSERT OR IGNORE INTO trade_journal (
                        id, ticker, name, date, setupLabel, swingband, entry, stop, 
                        target1, target2, target3, riskAmount, qty, status, 
                        exitPrice, exitDate, pnl, rAchieved, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade_id, entry.get('ticker'), entry.get('name'), entry.get('date'),
                    entry.get('setupLabel'), entry.get('swingband'), entry.get('entry', 0.0),
                    entry.get('stop', 0.0), entry.get('target1', 0.0), entry.get('target2', 0.0),
                    entry.get('target3', 0.0), entry.get('riskAmount', 0.0), entry.get('qty', 0),
                    entry.get('status', 'open'), entry.get('exitPrice'), entry.get('exitDate'),
                    entry.get('pnl'), entry.get('rAchieved'), entry.get('notes', '')
                ))
                
        conn.commit()
        conn.close()
        conn = None
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()

# ---------- IPO / SME API ENDPOINTS ----------

ipo_refresh_lock = threading.Lock()
last_ipo_refresh_time = 0.0

@app.route('/api/ipo/listings', methods=['GET'])
def get_ipo_listings():
    from flask import request
    conn = None
    try:
        exchange_param = request.args.get('exchange', 'all').strip()
        days_param = request.args.get('days', 'all').strip()
        phase_param = request.args.get('phase', 'all').strip()
        volume_alert_param = request.args.get('volume_alert', 'all').strip()
        min_volume_param = request.args.get('min_volume', 'all').strip()
        limit = request.args.get('limit', '').strip()
        offset = request.args.get('offset', '').strip()
        
        where_clauses = []
        params = []
        
        if volume_alert_param != 'all' and volume_alert_param != '':
            selected_alerts = volume_alert_param.split(',')
            alert_clauses = []
            for alert in selected_alerts:
                if alert == 'ppv':
                    alert_clauses.append("is_blue_bar = 1")
                elif alert == 'vol-surge':
                    alert_clauses.append("is_green_bar = 1")
                elif alert == 'dry-vol':
                    alert_clauses.append("is_orange_bar = 1")
            if alert_clauses:
                where_clauses.append(f"({ ' OR '.join(alert_clauses) })")
                
        min_vol = _parse_volume_param(min_volume_param)
        if min_vol is not None:
            where_clauses.append("volume >= ?")
            params.append(min_vol)
        
        if exchange_param != 'all':
            if exchange_param == 'NSE':
                where_clauses.append("exchange = 'NSE'")
            elif exchange_param == 'BSE':
                where_clauses.append("exchange = 'BSE'")
                
        if days_param != 'all':
            max_days = None
            if days_param == '1m': max_days = 30
            elif days_param == '3m': max_days = 90
            elif days_param == '6m': max_days = 180
            elif days_param == '1y': max_days = 365
            elif days_param == '18m': max_days = 548
            else:
                try:
                    max_days = int(days_param)
                except ValueError:
                    pass
            if max_days is not None:
                where_clauses.append("days_since_listing <= ?")
                params.append(max_days)
                
        if phase_param != 'all':
            where_clauses.append("momentum_phase = ?")
            params.append(phase_param)
            
        where_str = ""
        if where_clauses:
            where_str = f" WHERE {' AND '.join(where_clauses)}"
            
        conn = sqlite3.connect('scan_history.db', timeout=30.0)
        c = conn.cursor()
        
        # Count total recent IPOs (avoid double counting when exchange is 'all')
        if exchange_param == 'all':
            c.execute(f"SELECT COUNT(DISTINCT company_name) FROM ipo_metrics_cache{where_str}", tuple(params))
        else:
            c.execute(f"SELECT COUNT(*) FROM ipo_metrics_cache{where_str}", tuple(params))
        total_count = c.fetchone()[0]
        
        # Calculate summary phase counts (avoid double counting when exchange is 'all' and respect filters)
        summary_clauses = []
        summary_params = []
        if exchange_param != 'all':
            if exchange_param == 'NSE':
                summary_clauses.append("exchange = 'NSE'")
            elif exchange_param == 'BSE':
                summary_clauses.append("exchange = 'BSE'")
        if days_param != 'all':
            max_days = None
            if days_param == '1m': max_days = 30
            elif days_param == '3m': max_days = 90
            elif days_param == '6m': max_days = 180
            elif days_param == '1y': max_days = 365
            elif days_param == '18m': max_days = 548
            else:
                try:
                    max_days = int(days_param)
                except ValueError:
                    pass
            if max_days is not None:
                summary_clauses.append("days_since_listing <= ?")
                summary_params.append(max_days)
                
        if volume_alert_param != 'all' and volume_alert_param != '':
            selected_alerts = volume_alert_param.split(',')
            alert_clauses = []
            for alert in selected_alerts:
                if alert == 'ppv':
                    alert_clauses.append("is_blue_bar = 1")
                elif alert == 'vol-surge':
                    alert_clauses.append("is_green_bar = 1")
                elif alert == 'dry-vol':
                    alert_clauses.append("is_orange_bar = 1")
            if alert_clauses:
                summary_clauses.append(f"({ ' OR '.join(alert_clauses) })")
                
        min_vol = _parse_volume_param(min_volume_param)
        if min_vol is not None:
            summary_clauses.append("volume >= ?")
            summary_params.append(min_vol)
        
        summary_where = ""
        if summary_clauses:
            summary_where = f" WHERE {' AND '.join(summary_clauses)}"
            
        if exchange_param == 'all':
            c.execute(f"SELECT momentum_phase, COUNT(DISTINCT company_name) FROM ipo_metrics_cache{summary_where} GROUP BY momentum_phase", tuple(summary_params))
        else:
            c.execute(f"SELECT momentum_phase, COUNT(*) FROM ipo_metrics_cache{summary_where} GROUP BY momentum_phase", tuple(summary_params))
            
        summary_rows = c.fetchall()
        summary = {"HOT": 0, "STABLE": 0, "FADING": 0, "BROKEN": 0}
        for phase, cnt in summary_rows:
            if phase in summary:
                summary[phase] = cnt
                
        sort_by = request.args.get('sort_by', 'listing_date').strip()
        order = request.args.get('order', 'desc').strip().upper()
        if order not in ['ASC', 'DESC']:
            order = 'DESC'
            
        allowed_sort_cols = [
            'ticker', 'company_name', 'listing_date', 'exchange', 'sector', 'issue_price',
            'listing_gain_pct', 'current_vs_issue_pct', 'current_vs_listing_pct', 'days_since_listing',
            'rvol_ratio', 'above_listing_high', 'drawdown_from_ath', 'swing_score', 'pattern_name',
            'momentum_phase', 'current_price', 'volume', 'change_pct', 'day_low', 'day_high',
            'is_blue_bar', 'is_green_bar', 'is_orange_bar', 'day_range_pct'
        ]
        if sort_by not in allowed_sort_cols:
            sort_by = 'listing_date'
            
        order_by_expr = sort_by
        if sort_by == 'day_range_pct':
            order_by_expr = "CASE WHEN (day_high - day_low) > 0 THEN ((current_price - day_low) * 100.0 / (day_high - day_low)) ELSE -1.0 END"
            
        query = f"""
            SELECT ticker, company_name, listing_date, exchange, sector, issue_price,
                   listing_gain_pct, current_vs_issue_pct, current_vs_listing_pct, days_since_listing,
                   rvol_ratio, above_listing_high, drawdown_from_ath, swing_score, pattern_name,
                   momentum_phase, current_price, volume, change_pct, day_low, day_high,
                   is_blue_bar, is_green_bar, is_orange_bar, cached_at
            FROM ipo_metrics_cache
            {where_str}
            ORDER BY {order_by_expr} {order}
        """
        
        limit_offset_params = list(params)
        if limit:
            try:
                limit_val = int(limit)
                query += " LIMIT ?"
                limit_offset_params.append(limit_val)
                if offset:
                    try:
                        offset_val = int(offset)
                        query += " OFFSET ?"
                        limit_offset_params.append(offset_val)
                    except ValueError:
                        pass
            except ValueError:
                pass
                
        c.execute(query, tuple(limit_offset_params))
        rows = c.fetchall()
        conn.close()
        conn = None
        
        cols = [
            'ticker', 'company_name', 'listing_date', 'exchange', 'sector', 'issue_price',
            'listing_gain_pct', 'current_vs_issue_pct', 'current_vs_listing_pct', 'days_since_listing',
            'rvol_ratio', 'above_listing_high', 'drawdown_from_ath', 'swing_score', 'pattern_name',
            'momentum_phase', 'current_price', 'volume', 'change_pct', 'day_low', 'day_high',
            'is_blue_bar', 'is_green_bar', 'is_orange_bar', 'cached_at'
        ]
        
        listings = []
        for r in rows:
            ipo = dict(zip(cols, r))
            # Recalculate days_since_listing dynamically so it never goes stale
            try:
                lst_dt = datetime.strptime(ipo["listing_date"], "%Y-%m-%d")
                ipo["days_since_listing"] = (datetime.now() - lst_dt).days
            except Exception:
                pass  # keep DB value if parsing fails
            listings.append(ipo)

        return jsonify(listings=listings, total=total_count, summary=summary)
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/ipo/detail/<ticker>', methods=['GET'])
def get_ipo_detail(ticker):
    conn = None
    try:
        conn = sqlite3.connect('scan_history.db', timeout=30.0)
        c = conn.cursor()
        c.execute("SELECT * FROM ipo_metrics_cache WHERE ticker = ?", (ticker,))
        row = c.fetchone()
        
        if not row:
            # Check if exists in ipo_listings at least
            c.execute("SELECT ticker FROM ipo_listings WHERE ticker = ?", (ticker,))
            exists = c.fetchone()
            conn.close()
            conn = None
            if not exists:
                return jsonify(error=f"Ticker {ticker} not found in IPO listings"), 404
            return jsonify(error=f"Ticker {ticker} is not cached yet"), 404
            
        cols = [description[0] for description in c.description]
        detail = dict(zip(cols, row))
        
        # Get price history
        history = fetch_historical_prices(ticker, range_str="1y")
        detail["history"] = history or []
        
        conn.close()
        conn = None
        return jsonify(detail)
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/ipo/refresh', methods=['POST'])
def api_refresh_ipo():
    global last_ipo_refresh_time
    import time
    
    current_time = time.time()
    if current_time - last_ipo_refresh_time < 60:
        remaining = int(60 - (current_time - last_ipo_refresh_time))
        return jsonify(error=f"Refresh cooldown active. Please wait {remaining} seconds."), 429
        
    # Start background thread to refresh cache asynchronously
    def _bg_refresh():
        global last_ipo_refresh_time
        with ipo_refresh_lock:
            try:
                refresh_ipo_metrics()
            except Exception as e:
                print(f"Error in background IPO refresh: {e}")
                
    t = threading.Thread(target=_bg_refresh)
    t.start()
    
    last_ipo_refresh_time = current_time
    return jsonify(success=True, message="Background refresh started.")


@app.route('/api/ipo/debug-nse')
def debug_nse_ipo():
    """
    One-time debug route — inspect raw NSE public-past-issues field names.
    Remove or gate behind an env flag once field names are confirmed.
    """
    raw = fetch_nse_past_issues()
    if not raw:
        return jsonify(error="NSE returned no data — check cookies / network"), 500
    return jsonify(
        total_count=len(raw),
        sample=raw[:3],
        keys=list(raw[0].keys()) if raw else []
    )

# ---------- Episodic Pivot (EP) API Endpoints ----------

ep_refresh_lock = threading.Lock()
last_ep_refresh_time = 0.0

@app.route('/api/ep/refresh', methods=['POST'])
def api_refresh_ep():
    global last_ep_refresh_time
    import time
    
    current_time = time.time()
    if current_time - last_ep_refresh_time < 60:
        remaining = int(60 - (current_time - last_ep_refresh_time))
        return jsonify(error=f"Refresh cooldown active. Please wait {remaining} seconds."), 429
        
    def _bg_refresh():
        global last_ep_refresh_time
        with ep_refresh_lock:
            try:
                refresh_ep_screener()
            except Exception as e:
                print(f"Error in background EP refresh: {e}")
                
    t = threading.Thread(target=_bg_refresh)
    t.start()
    
    last_ep_refresh_time = current_time
    return jsonify(success=True, message="Background EP refresh started.")


@app.route('/api/ep/refresh/status', methods=['GET'])
def get_ep_refresh_status():
    return jsonify(running=ep_refresh_lock.locked())


@app.route('/api/ep/today', methods=['GET'])
def get_ep_today():
    from flask import request
    conn = None
    try:
        ep_type = request.args.get('ep_type', 'all').strip()
        confidence = request.args.get('confidence', 'all').strip()
        min_score_raw = request.args.get('min_score', '').strip()
        min_score = float(min_score_raw) if min_score_raw else 0.55
        min_mktcap_raw = request.args.get('min_mktcap', '').strip()
        min_mktcap = float(min_mktcap_raw) if min_mktcap_raw else 0.0
        max_mktcap_raw = request.args.get('max_mktcap', '').strip()
        max_mktcap = float(max_mktcap_raw) if max_mktcap_raw else 999999.0
        exchange = request.args.get('exchange', 'all').strip()
        
        where_clauses = ["ep_score >= ?"]
        params = [min_score]
        
        if ep_type != 'all':
            where_clauses.append("ep_type = ?")
            params.append(ep_type)
            
        if confidence != 'all':
            where_clauses.append("confidence = ?")
            params.append(confidence)
            
        if min_mktcap > 0.0:
            where_clauses.append("market_cap_cr >= ?")
            params.append(min_mktcap)
            
        if max_mktcap < 999999.0:
            where_clauses.append("market_cap_cr <= ?")
            params.append(max_mktcap)
            
        if exchange != 'all':
            where_clauses.append("exchange = ?")
            params.append(exchange)
            
        where_str = f" WHERE {' AND '.join(where_clauses)}"
        
        conn = sqlite3.connect('scan_history.db', timeout=30.0)
        c = conn.cursor()
        
        c.execute(f"SELECT DISTINCT feature_date FROM ep_features ORDER BY feature_date DESC LIMIT 1")
        latest_date_row = c.fetchone()
        if latest_date_row:
            latest_date = latest_date_row[0]
            where_clauses.append("feature_date = ?")
            params.append(latest_date)
            where_str = f" WHERE {' AND '.join(where_clauses)}"
        else:
            conn.close()
            return jsonify(listings=[], total=0, summary={"HIGH": 0, "MEDIUM": 0, "LOW": 0})
            
        c.execute(f"SELECT COUNT(*) FROM ep_features{where_str}", tuple(params))
        total_count = c.fetchone()[0]
        
        query = f"""
            SELECT symbol, exchange, feature_date, perf_3m, perf_6m, range_60d_pct, avg_vol_rank,
                   neglect_score, has_result, revenue_growth, profit_growth, has_corp_event,
                   event_type, catalyst_score, gap_pct, rel_volume, close_loc, repricing_score,
                   ep_score, ep_type, confidence, market_cap_cr, avg_turnover_cr, float_days
            FROM ep_features
            {where_str}
            ORDER BY ep_score DESC
        """
        c.execute(query, tuple(params))
        rows = c.fetchall()
        
        c.execute(f"SELECT confidence, COUNT(*) FROM ep_features WHERE feature_date = ? GROUP BY confidence", (latest_date,))
        summary_rows = c.fetchall()
        summary = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for conf, cnt in summary_rows:
            if conf in summary:
                summary[conf] = cnt
                
        conn.close()
        conn = None
        
        cols = [
            'symbol', 'exchange', 'feature_date', 'perf_3m', 'perf_6m', 'range_60d_pct', 'avg_vol_rank',
            'neglect_score', 'has_result', 'revenue_growth', 'profit_growth', 'has_corp_event',
            'event_type', 'catalyst_score', 'gap_pct', 'rel_volume', 'close_loc', 'repricing_score',
            'ep_score', 'ep_type', 'confidence', 'market_cap_cr', 'avg_turnover_cr', 'float_days'
        ]
        
        listings = [dict(zip(cols, r)) for r in rows]
        return jsonify(listings=listings, total=total_count, summary=summary, latest_date=latest_date)
        
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/ep/watchlist', methods=['GET'])
def get_ep_watchlist():
    conn = None
    try:
        conn = sqlite3.connect('scan_history.db', timeout=30.0)
        c = conn.cursor()
        c.execute("""
            SELECT id, symbol, exchange, catalyst_date, ep_type, status, trigger_type,
                   entry_price, stop_price, target_price, entry_date, days_on_watch, notes, ep_score
            FROM ep_watchlist
            WHERE status = 'ACTIVE'
            ORDER BY catalyst_date DESC
        """)
        rows = c.fetchall()
        conn.close()
        conn = None
        
        cols = [
            'id', 'symbol', 'exchange', 'catalyst_date', 'ep_type', 'status', 'trigger_type',
            'entry_price', 'stop_price', 'target_price', 'entry_date', 'days_on_watch', 'notes', 'ep_score'
        ]
        watchlist = [dict(zip(cols, r)) for r in rows]
        return jsonify(watchlist=watchlist)
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/ep/sugar-babies', methods=['GET'])
def get_ep_sugar_babies():
    conn = None
    try:
        conn = sqlite3.connect('scan_history.db', timeout=30.0)
        c = conn.cursor()
        c.execute("""
            SELECT id, symbol, exchange, added_date, avg_burst_pct, avg_burst_days, episode_count, notes, is_active
            FROM sugar_babies
            WHERE is_active = 1
            ORDER BY symbol ASC
        """)
        rows = c.fetchall()
        conn.close()
        conn = None
        
        cols = ['id', 'symbol', 'exchange', 'added_date', 'avg_burst_pct', 'avg_burst_days', 'episode_count', 'notes', 'is_active']
        sugar_babies = [dict(zip(cols, r)) for r in rows]
        return jsonify(sugar_babies=sugar_babies)
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/ep/<symbol>/detail', methods=['GET'])
def get_ep_detail(symbol):
    conn = None
    try:
        conn = sqlite3.connect('scan_history.db', timeout=30.0)
        c = conn.cursor()
        
        c.execute("""
            SELECT symbol, exchange, feature_date, perf_3m, perf_6m, range_60d_pct, avg_vol_rank,
                   neglect_score, has_result, revenue_growth, profit_growth, has_corp_event,
                   event_type, catalyst_score, gap_pct, rel_volume, close_loc, repricing_score,
                   ep_score, ep_type, confidence, market_cap_cr, avg_turnover_cr, float_days
            FROM ep_features
            WHERE symbol = ?
            ORDER BY feature_date DESC LIMIT 1
        """, (symbol.upper(),))
        row = c.fetchone()
        
        if not row:
            conn.close()
            return jsonify(error=f"Symbol {symbol} features not found"), 404
            
        cols = [description[0] for description in c.description]
        detail = dict(zip(cols, row))
        
        ticker = f"{symbol.upper()}.NS"
        history = fetch_historical_prices(ticker, range_str="6mo")
        detail["history"] = history or []
        
        c.execute("""
            SELECT event_date, event_type, headline, sentiment, catalyst_score, source, raw_url
            FROM corporate_events
            WHERE symbol = ?
            ORDER BY event_date DESC LIMIT 10
        """, (symbol.upper(),))
        events_rows = c.fetchall()
        detail["corporate_events"] = [dict(zip(['event_date', 'event_type', 'headline', 'sentiment', 'catalyst_score', 'source', 'raw_url'], ev)) for ev in events_rows]
        
        c.execute("""
            SELECT quarter, result_date, revenue, revenue_yoy_pct, net_profit, net_profit_yoy_pct, eps
            FROM fundamentals
            WHERE symbol = ?
            ORDER BY result_date DESC LIMIT 8
        """, (symbol.upper(),))
        fund_rows = c.fetchall()
        detail["fundamentals"] = [dict(zip(['quarter', 'result_date', 'revenue', 'revenue_yoy_pct', 'net_profit', 'net_profit_yoy_pct', 'eps'], f)) for f in fund_rows]
        
        # Get latest watchlist details
        c.execute("""
            SELECT status, stop_price, notes
            FROM ep_watchlist
            WHERE symbol = ?
            ORDER BY id DESC LIMIT 1
        """, (symbol.upper(),))
        wl_row = c.fetchone()
        if wl_row:
            detail["watchlist_status"] = wl_row[0]
            detail["watchlist_stop"] = wl_row[1]
            detail["watchlist_notes"] = wl_row[2]
        else:
            detail["watchlist_status"] = None
            detail["watchlist_stop"] = None
            detail["watchlist_notes"] = None

        # Check if is sugar baby
        c.execute("""
            SELECT is_active
            FROM sugar_babies
            WHERE symbol = ? AND is_active = 1
            LIMIT 1
        """, (symbol.upper(),))
        sb_row = c.fetchone()
        detail["is_sugar_baby"] = 1 if sb_row else 0
        
        conn.close()
        conn = None
        return jsonify(detail)
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/ep/watchlist', methods=['POST'])
def add_to_ep_watchlist():
    data = request.get_json() or {}
    symbol = data.get("symbol", "").upper().strip()
    if not symbol:
        return jsonify(error="Symbol is required"), 400
    exchange = data.get("exchange", "NSE").upper().strip()
    stop_price = data.get("stop_price")
    notes = data.get("notes", "")

    if stop_price is not None and stop_price != "":
        try:
            stop_price = float(stop_price)
        except ValueError:
            return jsonify(error="Invalid stop price"), 400
    else:
        stop_price = None

    conn = None
    try:
        conn = sqlite3.connect('scan_history.db', timeout=30.0)
        c = conn.cursor()
        
        c.execute("SELECT id FROM ep_watchlist WHERE symbol = ? AND status = 'ACTIVE'", (symbol,))
        existing = c.fetchone()
        
        if existing:
            c.execute("""
                UPDATE ep_watchlist
                SET stop_price = ?, notes = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (stop_price, notes, existing[0]))
            conn.commit()
            return jsonify(success=True, message="Updated existing active watchlist entry")
        else:
            c.execute("""
                SELECT ep_type, ep_score, feature_date
                FROM ep_features
                WHERE symbol = ?
                ORDER BY feature_date DESC LIMIT 1
            """, (symbol,))
            feat = c.fetchone()
            
            if feat:
                ep_type = feat[0]
                ep_score = feat[1]
                catalyst_date = feat[2]
            else:
                ep_type = "Manual"
                ep_score = 0.55
                catalyst_date = datetime.now().strftime("%Y-%m-%d")

            entry_price = None
            ticker = f"{symbol}.NS" if exchange == "NSE" else f"{symbol}.BO"
            try:
                history = fetch_historical_prices(ticker, range_str="1d")
                if history:
                    entry_price = history[-1]["close"]
                    if not feat:
                        catalyst_date = history[-1]["date"]
            except Exception:
                pass

            c.execute("""
                INSERT INTO ep_watchlist (
                    symbol, exchange, catalyst_date, ep_type, status, ep_score, entry_price, stop_price, notes
                ) VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?)
            """, (symbol, exchange, catalyst_date, ep_type, ep_score, entry_price, stop_price, notes))
            conn.commit()
            return jsonify(success=True, message="Added to watchlist")
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/ep/watchlist/remove', methods=['POST'])
def remove_from_ep_watchlist():
    data = request.get_json() or {}
    symbol = data.get("symbol", "").upper().strip()
    if not symbol:
        return jsonify(error="Symbol is required"), 400
        
    conn = None
    try:
        conn = sqlite3.connect('scan_history.db', timeout=30.0)
        c = conn.cursor()
        c.execute("""
            UPDATE ep_watchlist
            SET status = 'EXPIRED', updated_at = datetime('now')
            WHERE symbol = ? AND status = 'ACTIVE'
        """, (symbol,))
        conn.commit()
        return jsonify(success=True, message="Removed symbol from active watchlist")
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/ep/watchlist/trigger', methods=['POST'])
def trigger_ep_watchlist():
    data = request.get_json() or {}
    symbol = data.get("symbol", "").upper().strip()
    if not symbol:
        return jsonify(error="Symbol is required"), 400
        
    conn = None
    try:
        conn = sqlite3.connect('scan_history.db', timeout=30.0)
        c = conn.cursor()
        
        c.execute("SELECT exchange, entry_price FROM ep_watchlist WHERE symbol = ? AND status = 'ACTIVE'", (symbol,))
        row = c.fetchone()
        if not row:
            return jsonify(error="No active watchlist entry found for this symbol"), 404
            
        exchange, current_entry_price = row
        ticker = f"{symbol}.NS" if exchange == "NSE" else f"{symbol}.BO"
        
        today_price = current_entry_price
        today_date = datetime.now().strftime("%Y-%m-%d")
        try:
            history = fetch_historical_prices(ticker, range_str="1d")
            if history:
                today_price = history[-1]["close"]
                today_date = history[-1]["date"]
        except Exception:
            pass
            
        c.execute("""
            UPDATE ep_watchlist
            SET status = 'TRIGGERED', trigger_type = 'MANUAL', entry_price = ?, entry_date = ?, updated_at = datetime('now')
            WHERE symbol = ? AND status = 'ACTIVE'
        """, (today_price, today_date, symbol))
        conn.commit()
        
        price_str = f"₹{today_price:.2f}" if today_price is not None else "₹0.00"
        alert_msg = (
            f"🔔 <b>EP Watchlist Manually Triggered!</b>\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Trigger:</b> MANUAL\n"
            f"<b>Price:</b> {price_str}"
        )
        send_telegram_alert(alert_msg)
        
        return jsonify(success=True, message="Watchlist entry marked as TRIGGERED")
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/ep/sugar-babies', methods=['POST'])
def add_to_sugar_babies():
    data = request.get_json() or {}
    symbol = data.get("symbol", "").upper().strip()
    if not symbol:
        return jsonify(error="Symbol is required"), 400
    exchange = data.get("exchange", "NSE").upper().strip()
    notes = data.get("notes", "")
    is_active = data.get("is_active", 1)

    conn = None
    try:
        conn = sqlite3.connect('scan_history.db', timeout=30.0)
        c = conn.cursor()
        
        c.execute("SELECT id FROM sugar_babies WHERE symbol = ?", (symbol,))
        existing = c.fetchone()
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # TODO: update episode_count nightly
        c.execute("SELECT COUNT(*) FROM ep_features WHERE symbol = ? AND ep_score >= 0.55", (symbol,))
        episode_count = c.fetchone()[0]
        
        if existing:
            c.execute("""
                UPDATE sugar_babies
                SET notes = ?, is_active = ?, exchange = ?, episode_count = ?
                WHERE id = ?
            """, (notes, is_active, exchange, episode_count, existing[0]))
        else:
            c.execute("""
                INSERT INTO sugar_babies (
                    symbol, exchange, added_date, avg_burst_pct, avg_burst_days, episode_count, notes, is_active
                ) VALUES (?, ?, ?, 0.0, 0.0, ?, ?, ?)
            """, (symbol, exchange, today_str, episode_count, notes, is_active))
            
        conn.commit()
        status_text = "added to" if is_active else "removed from"
        return jsonify(success=True, message=f"Symbol {status_text} Sugar Babies")
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        if conn:
            conn.close()

# Initial EOD refresh check (relocated to end of file so all dependencies are defined)
import sys
if "pytest" not in sys.modules:
    try:
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        # Check if there are any listings missing from the metrics cache
        c.execute("SELECT COUNT(*) FROM ipo_listings WHERE ticker NOT IN (SELECT ticker FROM ipo_metrics_cache)")
        missing_cnt = c.fetchone()[0]
        conn.close()
        if missing_cnt > 0:
            print(f"IPO metrics cache is missing {missing_cnt} entries. Performing initial refresh...")
            refresh_ipo_metrics()
    except Exception as e:
        print(f"Error seeding initial IPO metrics cache: {e}")

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)

