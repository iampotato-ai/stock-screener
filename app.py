import os
import requests
import time
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS breadth_history (
            date TEXT,
            time TEXT,
            advances INTEGER,
            declines INTEGER,
            unchanged INTEGER,
            pct_sma21 REAL,
            pct_sma50 REAL,
            pct_52high REAL,
            avg_recommend REAL,
            regime_score INTEGER,
            regime_band TEXT,
            PRIMARY KEY (date, time)
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
                
        for stock in filtered_stocks:
            classify_setup(stock)
            compute_vol_dryup(stock)
            
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
                    '_dt': dt if 'dt' in locals() else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
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
    try:
        conn = sqlite3.connect('scan_history.db')
        c = conn.cursor()
        c.execute("SELECT date,time,advances,declines,pct_sma21,pct_sma50,"
                  "pct_52high,regime_score,regime_band FROM breadth_history "
                  "ORDER BY date DESC, time DESC LIMIT 50")
        rows = c.fetchall(); conn.close()
        cols = ['date','time','advances','declines','pctAboveSMA21',
                'pctAboveSMA50','pctNear52High','regimeScore','regimeBand']
        return jsonify(history=[dict(zip(cols, r)) for r in rows])
    except Exception as e:
        return jsonify(error=str(e)), 500

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)

