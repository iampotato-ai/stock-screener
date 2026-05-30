import os
import requests
import time
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import threading
from flask import Flask, jsonify, render_template
import sqlite3

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
    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            UNIQUE(section_id, ticker),
            FOREIGN KEY(section_id) REFERENCES watchlist_sections(id) ON DELETE CASCADE
        )
    ''')
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
            last_close  REAL NOT NULL
        )
    ''')
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
    
    conn.commit()
    conn.close()

init_db()

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
    
    current_close = closes[-1]
    current_volume = volumes[-1]
    avg_volume_50 = sum(volumes[-50:]) / 50 if len(volumes) >= 50 else sum(volumes) / len(volumes)
    vol_ratio = current_volume / avg_volume_50 if avg_volume_50 > 0 else 1.0
    
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
        local_idx = highs[slice_start:-25].index(cup_left_high)
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

def analyze_single_stock(stock):
    try:
        ticker = stock["clean_ticker"]
        history = fetch_historical_prices(ticker, range_str="6mo")
        if history:
            result = classify_technical_pattern(history)
            stock["pattern_name"] = result["pattern"]
            stock["pattern_grade"] = result["grade"]
            stock["pattern_desc"] = result["description"]
        else:
            print(f"[Yahoo Finance] Fetch failed for {ticker} (silently falling back to Trend Continuation)")
            stock["pattern_name"] = "Trend Continuation"
            stock["pattern_grade"] = "B"
            stock["pattern_desc"] = "Price in standard swing configuration. Historical daily data fetch not available."
    except Exception as e:
        print(f"[Yahoo Finance] Error analyzing setup for {ticker}: {e}")
        stock["pattern_name"] = "Trend Continuation"
        stock["pattern_grade"] = "B"
        stock["pattern_desc"] = f"Analysis error: {e}"

def populate_screener_intelligence(stocks_list):
    if not stocks_list:
        return
    # Analyze the top 50 momentum stocks (sorted by swing score and relative volume)
    stocks_to_analyze = sorted(
        stocks_list, 
        key=lambda x: (x.get("swingscore", 0), x.get("relative_volume", 0)), 
        reverse=True
    )[:50]
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        executor.map(analyze_single_stock, stocks_to_analyze)
        
    analyzed_tickers = {s["clean_ticker"] for s in stocks_to_analyze}
    for stock in stocks_list:
        if stock["clean_ticker"] not in analyzed_tickers:
            stock["pattern_name"] = "Trend Continuation"
            stock["pattern_grade"] = "B"
            stock["pattern_desc"] = "Stock qualifies for momentum trend. Setup analysis limited to top 50 matches."

# ── Kronos AI Predictor Loading ──
kronos_predictor = None
kronos_load_lock = threading.Lock()

# ── Kronos Result Cache (4hr TTL per ticker) ──
import time as _time
from collections import OrderedDict
_kronos_cache = OrderedDict()       # {ticker: (timestamp, bias, score, forecast_list, forecast_metrics)}
_kronos_cache_lock = threading.Lock()
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
                    import torch
                    torch.set_num_threads(1)
                    from model import Kronos, KronosTokenizer, KronosPredictor
                    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
                    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
                    kronos_predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=2048)
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

def compute_forecast_metrics(forecast_list, last_close, history):
    """
    Computes forecast scoring metrics, forecast bias, and confidence score.
    Returns: (ai_forecast_bias, ai_confidence_score, forecast_metrics)
    """
    if not forecast_list:
        return None, 0, {}

    import numpy as np

    forecast_closes = [r["close"] for r in forecast_list]
    forecast_highs  = [r["high"] for r in forecast_list]
    current_close   = last_close

    # ── M1: Endpoint Return % ──────────────────────────────────────────
    m1_return_pct = (forecast_closes[-1] - current_close) / (current_close + 1e-5) * 100

    # ── M2: Momentum Split (early vs late 3 bars) ──────────────────────
    early_len = min(3, len(forecast_closes))
    late_len = min(3, len(forecast_closes))
    early_avg = np.mean(forecast_closes[:early_len]) if early_len > 0 else current_close
    late_avg  = np.mean(forecast_closes[-late_len:]) if late_len > 0 else current_close
    m2_split_pct = (late_avg - early_avg) / (current_close + 1e-5) * 100

    # ── M3: Day-by-Day Consistency % ──────────────────────────────────
    if len(forecast_closes) > 1:
        up_days = sum(
            1 for i in range(1, len(forecast_closes))
            if forecast_closes[i] > forecast_closes[i-1]
        )
        m3_consistency_pct = up_days / (len(forecast_closes) - 1) * 100
    else:
        m3_consistency_pct = 50.0

    # ── M4: Breakout Above 20d Recent High ────────────────────────────
    highs = [day["high"] for day in history]
    recent_20d_high = max(highs[-21:-1]) if len(highs) >= 21 else max(highs)
    m4_breakout = max(forecast_highs) > recent_20d_high

    # ── M5: Max Drawdown During Forecast Window ────────────────────────
    m5_drawdown_pct = (min(forecast_closes) - current_close) / (current_close + 1e-5) * 100

    # ── [TWEAK 2] Realised return std from history ──────────────
    hist_closes = [float(d["close"]) for d in history]
    realised_returns = []
    horizon = len(forecast_list)
    for i in range(horizon, len(hist_closes)):
        r = (hist_closes[i] - hist_closes[i - horizon]) / (hist_closes[i - horizon] + 1e-5) * 100
        realised_returns.append(r)
    realised_std = float(np.std(realised_returns)) if len(realised_returns) >= 5 else 5.0
    normalised_return = m1_return_pct / (realised_std + 1e-5)

    # ── Weighted Score [-1, +1] ────────────────────────────────────────
    def _norm(val, lo, hi):
        """Linearly map val from [lo, hi] to [-1, +1], clamped."""
        return float(np.clip((val - lo) / ((hi - lo) / 2 + 1e-9) - 1, -1, 1))

    s1 = _norm(m1_return_pct,     -10,  10)   # endpoint direction  (30%)
    s2 = _norm(m2_split_pct,       -5,   5)   # momentum quality    (25%)
    s3 = _norm(m3_consistency_pct,  30,  70)  # day consistency     (20%)
    s4 = 1.0 if m4_breakout else -0.2         # breakout signal     (15%)
    s5 = _norm(-m5_drawdown_pct,   -8,   0)   # inverse of drawdown (10%)

    weighted_score = (0.30 * s1 + 0.25 * s2 + 0.20 * s3
                      + 0.15 * s4 + 0.10 * s5)

    # ── 5-Label Bias ───────────────────────────────────────────────────
    if weighted_score > 0.40:
        ai_forecast_bias = "Strong Breakout"
    elif weighted_score > 0.15:
        ai_forecast_bias = "Bullish Continuation"
    elif weighted_score > -0.15:
        ai_forecast_bias = "Sideways Consolidation"
    elif weighted_score > -0.40:
        ai_forecast_bias = "Bearish Pressure"
    else:
        ai_forecast_bias = "Strong Downtrend"

    # ── [TWEAK 3] Dampened cv_score for flat forecasts ─────────────────
    atr_pct = compute_atr_pct(history)
    fc_mean = np.mean(forecast_closes)
    fc_std  = np.std(forecast_closes)
    cv      = fc_std / (fc_mean + 1e-5)
    forecast_range_pct = (max(forecast_closes) - min(forecast_closes)) / (current_close + 1e-5) * 100
    is_flat_forecast   = forecast_range_pct < atr_pct          # less than 1 ATR of movement
    cv_weight = 0.20 if is_flat_forecast else 0.40             # dampen cv on flat names

    cv_score   = float(np.clip(1.0 - cv * 10, 0, 1))
    
    if weighted_score > 0:
        cons_score = float(np.clip((m3_consistency_pct - 50) / 50, 0.0, 1.0))
    elif weighted_score < 0:
        cons_score = float(np.clip((50 - m3_consistency_pct) / 50, 0.0, 1.0))
    else:
        cons_score = 0.0
        
    mag_score  = abs(weighted_score)
    cons_weight = 0.50 if is_flat_forecast else 0.40
    mag_weight  = 0.30 if is_flat_forecast else 0.20
    ai_confidence_score = int(np.clip(
        (cv_weight * cv_score + cons_weight * cons_score + mag_weight * mag_score) * 100,
        25, 92
    ))

    forecast_metrics = {
        "return_pct":         round(m1_return_pct,    2),
        "momentum_split":     round(m2_split_pct,     2),
        "consistency_pct":    round(m3_consistency_pct, 1),
        "breakout_signal":    bool(m4_breakout),
        "max_drawdown_pct":   round(m5_drawdown_pct,  2),
        "weighted_score":     round(weighted_score,   3),
        "normalised_return":  round(normalised_return, 2),
        "realised_std_10d":   round(realised_std,      2),
        "forecast_range_pct": round(forecast_range_pct, 2),
        "is_flat_forecast":   bool(is_flat_forecast),
    }

    return ai_forecast_bias, ai_confidence_score, forecast_metrics

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
        
    history = fetch_historical_prices(ticker, range_str="6mo")
    if not history:
        return jsonify(
            ticker=ticker,
            pattern="Trend Continuation",
            grade="B",
            description="Unable to retrieve daily chart history from Yahoo Finance.",
            indicators={}
        )
        
    result = classify_technical_pattern(history)
    
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
                    ai_forecast_bias, ai_confidence_score, forecast_metrics = compute_forecast_metrics(
                        forecast_list, current_close, history
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
        chart_data=[{
            "date": d["date"],
            "open": d["open"],
            "high": d["high"],
            "low": d["low"],
            "close": d["close"],
            "volume": d["volume"]
        } for d in history]
    )

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
        
    sample_count = int(request.args.get('sample_count', 20))
    
    # 1. Fetch historical prices (120 bars for calculation of ATR%)
    history = fetch_historical_prices(ticker, range_str="6mo")
    if not history or len(history) < 10:
        return jsonify(error="Insufficient price history"), 400
        
    last_date_str = history[-1]["date"]
    
    # Check database to see if we already have it stored for today
    conn = sqlite3.connect("scan_history.db")
    c = conn.cursor()
    c.execute(
        "SELECT forecast_json, last_close, generated_at FROM kronos_forecasts WHERE ticker = ? AND pred_len = ? ORDER BY id DESC LIMIT 1",
        (ticker, pred_len)
    )
    db_row = c.fetchone()
    
    # If the database record matches today's generated date, use it
    if db_row:
        stored_forecast_json, last_close, generated_at_str = db_row
        gen_date = generated_at_str.split('T')[0]
        today_str = datetime.now().strftime('%Y-%m-%d')
        if gen_date == today_str:
            conn.close()
            return jsonify(
                ticker=ticker,
                pred_len=pred_len,
                forecast=json.loads(stored_forecast_json),
                last_close=last_close,
                generated_at=generated_at_str
            )
            
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
        
        # Call model with return_samples=True to compute bands
        # Shape returned is (sample_count, pred_len, features)
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
            "INSERT INTO kronos_forecasts (ticker, generated_at, pred_len, forecast_json, last_close) VALUES (?, ?, ?, ?, ?)",
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
        "SELECT id, generated_at, pred_len, forecast_json, last_close FROM kronos_forecasts WHERE ticker = ? ORDER BY id DESC",
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
        jdk_rs = ((100.0 + sector_4w) / (100.0 + uni_median) * 100.0) if (100.0 + uni_median) != 0 else 100.0
        
        # Fetch last week's jdk_rs (excluding this week) to compute robust momentum
        cursor.execute(
            'SELECT jdk_rs FROM rrg_history WHERE sector = ? AND week != ? ORDER BY snapped_at DESC LIMIT 1',
            (sector, iso_week)
        )
        row = cursor.fetchone()
        prev_rs = row[0] if row else jdk_rs
        rs_momentum = jdk_rs - prev_rs
        
        # Quadrant mapping
        if jdk_rs >= 100.0 and rs_momentum >= 0.0:
            quadrant = 'Leading'
        elif jdk_rs >= 100.0 and rs_momentum < 0.0:
            quadrant = 'Weakening'
        elif jdk_rs < 100.0 and rs_momentum < 0.0:
            quadrant = 'Lagging'
        else:
            quadrant = 'Improving'
            
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
    _last_snapshot_time = now_time
    _rrg_snapped_today = None
    try:
        res = scan_stocks()
        res_data = res.get_json()
        if "error" in res_data:
            return jsonify(error=res_data["error"]), 500
            
        universe = res_data.get("universe", [])
        if not universe:
            return jsonify(error="No universe stocks found to snap"), 500
            
        sector_scores, _, _, _ = calculate_backend_sector_scores(universe)
        snapshot_rrg_week(sector_scores, universe)
        return jsonify(success=True, message="RRG Snapshot saved successfully")
    except Exception as e:
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
                        jdk_rs = ((100.0 + sector_R) / (100.0 + bench_R) * 100.0) if (100.0 + bench_R) != 0 else 100.0
                        jdk_rs_list.append((w_str, jdk_rs, date))
                        
                # Calculate weekly momentum and upsert to DB
                for i in range(1, len(jdk_rs_list)):
                    w_str, val, date = jdk_rs_list[i]
                    prev_w_str, prev_val, prev_date = jdk_rs_list[i - 1]
                    rs_momentum = val - prev_val
                    
                    # Quadrant mapping
                    if val >= 100.0 and rs_momentum >= 0.0:
                        quadrant = 'Leading'
                    elif val >= 100.0 and rs_momentum < 0.0:
                        quadrant = 'Weakening'
                    elif val < 100.0 and rs_momentum < 0.0:
                        quadrant = 'Lagging'
                    else:
                        quadrant = 'Improving'
                        
                    # We simulate snapped_at time as close of that week to keep ordering
                    snap_time = (datetime.strptime(date, "%Y-%m-%d") + timedelta(hours=16)).isoformat()
                    
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
                    
        # Grab last 20 matching dates
        target_indices = valid_indices[-20:]
        
        trail_points = []
        for idx in target_indices:
            date = bench_dates[idx]
            close = history_map[date]
            bench_close = bench_closes[idx]
            
            # Weekly performance (5 days ago)
            prev_date_w = bench_dates[idx - 5]
            close_w = history_map.get(prev_date_w, close)
            bench_close_w = bench_closes[idx - 5]
            
            # Monthly performance (21 days ago)
            prev_date_m = bench_dates[idx - 21]
            close_m = history_map.get(prev_date_m, close)
            bench_close_m = bench_closes[idx - 21]
            
            stock_w = (close - close_w) / close_w * 100 if close_w > 0 else 0
            stock_m = (close - close_m) / close_m * 100 if close_m > 0 else 0
            bench_w = (bench_close - bench_close_w) / bench_close_w * 100 if bench_close_w > 0 else 0
            bench_m = (bench_close - bench_close_m) / bench_close_m * 100 if bench_close_m > 0 else 0
            
            x = stock_m - bench_m
            y = stock_w - bench_w
            
            trail_points.append({
                "date": date,
                "x": round(x, 2),
                "y": round(y, 2)
            })
            
        return {
            "label": label,
            "ticker": ticker,
            "trail": trail_points
        }
        
    results = []
    # Calculate in parallel to keep scan fast
    with ThreadPoolExecutor(max_workers=20) as executor:
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
        c.execute("SELECT id, name FROM watchlist_sections")
        sections = c.fetchall()
        
        result = []
        for sec_id, sec_name in sections:
            c.execute("SELECT ticker FROM watchlist_items WHERE section_id = ?", (sec_id,))
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
                # Recompute metrics for the specific pred_len
                b, s, m = compute_forecast_metrics(sliced_forecast, last_close, history)
                return build_ranking_entry(ticker, b, s, m, cache_hit=True)

        # 2. Check Database Cache
        conn = sqlite3.connect("scan_history.db")
        c = conn.cursor()
        c.execute(
            "SELECT forecast_json, last_close, generated_at FROM kronos_forecasts WHERE ticker = ? AND pred_len = ? ORDER BY id DESC LIMIT 1",
            (ticker, pred_len)
        )
        db_row = c.fetchone()
        
        if db_row:
            stored_forecast_json, db_last_close, generated_at_str = db_row
            gen_date = generated_at_str.split('T')[0]
            today_str = datetime.now().strftime('%Y-%m-%d')
            if gen_date == today_str:
                conn.close()
                forecast_list = json.loads(stored_forecast_json)
                b, s, m = compute_forecast_metrics(forecast_list, db_last_close, history)
                return build_ranking_entry(ticker, b, s, m, cache_hit=True)

        # 3. Live Inference
        predictor = get_kronos_predictor()
        if not predictor:
            if db_row: # Fallback to stale db cache if available
                conn.close()
                forecast_list = json.loads(stored_forecast_json)
                b, s, m = compute_forecast_metrics(forecast_list, db_last_close, history)
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
            "INSERT INTO kronos_forecasts (ticker, generated_at, pred_len, forecast_json, last_close) VALUES (?, ?, ?, ?, ?)",
            (ticker, generated_at, pred_len, forecast_json_str, last_close)
        )
        conn.commit()
        conn.close()

        # Compute metrics
        b, s, m = compute_forecast_metrics(forecast_list, last_close, history)
        return build_ranking_entry(ticker, b, s, m, cache_hit=False)

    except Exception as ex:
        print(f"[Kronos Batch] Live forecast error for {ticker}: {ex}")
        try:
            conn.close()
        except Exception:
            pass
        return build_ranking_entry(ticker, None, 0, {}, cache_hit=False)

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
            c.execute("SELECT id, name FROM watchlist_sections")
            sections = c.fetchall()

        result_sections = []
        for sec_id, sec_name in sections:
            c.execute("SELECT ticker FROM watchlist_items WHERE section_id = ?", (sec_id,))
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

            # Sort rankings: highest predicted_return_pct first, None/failed at the bottom
            rankings.sort(key=lambda x: x["predicted_return_pct"] if x["predicted_return_pct"] is not None else -9999, reverse=True)

            # Assign rank
            for idx, item in enumerate(rankings):
                item["rank"] = idx + 1

            result_sections.append({
                "id": sec_id,
                "name": sec_name,
                "rankings": rankings
            })

        conn.close()
        
        return jsonify({
            "generated_at": datetime.now().isoformat(),
            "pred_len": pred_len,
            "sections": result_sections
        })

    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        print(f"[Kronos Batch Route] Error: {e}")
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
        c.execute("INSERT OR IGNORE INTO watchlist_items (section_id, ticker) VALUES (?, ?)", (sec_id, ticker.upper()))
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
    try:
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute("""
            SELECT id, ticker, name, date, setupLabel, swingband, entry, stop, 
                   target1, target2, target3, riskAmount, qty, status, 
                   exitPrice, exitDate, pnl, rAchieved, notes 
            FROM trade_journal 
            ORDER BY id DESC
        """)
        rows = c.fetchall()
        conn.close()
        
        cols = ['id', 'ticker', 'name', 'date', 'setupLabel', 'swingband', 'entry', 'stop', 
                'target1', 'target2', 'target3', 'riskAmount', 'qty', 'status', 
                'exitPrice', 'exitDate', 'pnl', 'rAchieved', 'notes']
        trades = [dict(zip(cols, r)) for r in rows]
        return jsonify(trades)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/journal', methods=['POST'])
def create_journal_entry():
    from flask import request
    try:
        data = request.get_json() or {}
        trade_id = data.get('id')
        if not trade_id:
            return jsonify(error="id is required"), 400
            
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO trade_journal (
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
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/journal/<trade_id>', methods=['PUT'])
def update_journal_entry(trade_id):
    from flask import request
    try:
        data = request.get_json() or {}
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        
        fields = []
        params = []
        for key in ['status', 'exitPrice', 'exitDate', 'pnl', 'rAchieved', 'notes', 'entry', 'stop', 'target1', 'target2', 'target3', 'riskAmount', 'qty', 'ticker', 'name', 'date', 'setupLabel', 'swingband']:
            if key in data:
                fields.append(f"{key} = ?")
                params.append(data[key])
                
        if not fields:
            return jsonify(error="No fields to update"), 400
            
        params.append(trade_id)
        query = f"UPDATE trade_journal SET {', '.join(fields)} WHERE id = ?"
        c.execute(query, tuple(params))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/journal/<trade_id>', methods=['DELETE'])
def delete_journal_entry(trade_id):
    try:
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute("DELETE FROM trade_journal WHERE id = ?", (trade_id,))
        conn.commit()
        conn.close()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/migrate-local-data', methods=['POST'])
def migrate_local_data():
    from flask import request
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
                c.execute("INSERT OR REPLACE INTO watchlist_sections (id, name) VALUES (?, ?)", (sec_id, sec_name))
                stocks = sec.get('stocks', [])
                for sym in stocks:
                    if sym:
                        c.execute("INSERT OR IGNORE INTO watchlist_items (section_id, ticker) VALUES (?, ?)", (sec_id, sym.upper()))
                        
        # Migrate journal
        for entry in journal:
            trade_id = entry.get('id')
            if trade_id:
                c.execute("""
                    INSERT OR REPLACE INTO trade_journal (
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
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)

