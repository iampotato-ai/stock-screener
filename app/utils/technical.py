"""
Technical analysis utility functions.
"""
import numpy as np
import time
import json
import urllib.request
from datetime import datetime
from collections import OrderedDict

# Cache for fetch_historical_prices
_historical_prices_cache = OrderedDict()  # {(ticker, range_str): (timestamp, data)}
_HIST_CACHE_TTL = 15 * 60     # 15 minutes
_MAX_HIST_CACHE = 500         # Cap at 500 unique ticker/range combinations


def fetch_historical_prices(ticker, range_str="6mo"):
    """
    Fetch historical daily OHLCV data for a ticker from Yahoo Finance.
    Returns list of dicts.
    """
    cache_key = (ticker, range_str)
    now = time.time()
    if cache_key in _historical_prices_cache:
        t_cached, cached_data = _historical_prices_cache[cache_key]
        if now - t_cached < _HIST_CACHE_TTL:
            return cached_data

    import urllib.request
    import json
    import os
    symbol = ticker
    if not symbol.endswith(".NS") and not symbol.endswith(".BO") and not symbol.startswith("^"):
        symbol = f"{symbol}.NS"

    # Get Yahoo Finance URL from environment variable with fallback
    yahoo_finance_url = os.environ.get(
        'YAHOO_FINANCE_URL',
        'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={range_str}'
    )
    url = yahoo_finance_url.format(symbol=symbol, range_str=range_str)
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
            for val in closes[1:]:
                ema10 = val * alpha10 + ema10 * (1 - alpha10)

            alpha20 = 2 / (20 + 1)
            ema20 = closes[0]
            for val in closes[1:]:
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
    vcp_pattern = None
    if len(closes) >= 60:
        # Try to find local peaks to identify contraction periods dynamically
        best_vcp_pattern = None
        best_d3 = float('inf')
        for peak_window in [10, 8, 6, 4]:
            peaks = []
            for i in range(peak_window, len(highs) - 2):
                if highs[i] == max(highs[i - peak_window : i + peak_window + 1]):
                    if not peaks or (i - peaks[-1] > peak_window):
                        peaks.append(i)

            # Keep only peaks in the last 100 trading days
            peaks = [p for p in peaks if p >= len(highs) - 100]

            if len(peaks) >= 3:
                # Need at least 4 peaks to define 3 contraction intervals between them
                p_indices = peaks[-4:]
                depths = []
                for idx in range(len(p_indices) - 1):
                    p_start = p_indices[idx]
                    p_end = p_indices[idx+1]
                    peak_val = highs[p_start]
                    trough_val = min(lows[p_start:p_end])
                    depth = (peak_val - trough_val) / peak_val * 100
                    depths.append(depth)

                if len(depths) >= 3:
                    d1, d2, d3 = depths[-3:]
                    if d1 > d2 and d2 > d3 and d1 <= 30.0 and d3 <= 8.0:
                        # Max high in the 3rd contraction is the resistance level
                        pivot_high = max(highs[p_indices[-2]:])
                        is_breakout = current_close >= pivot_high * 0.98 and vol_ratio >= 1.4
                        desc = f"Volatility contraction detected dynamically with 3 contractions ({d1:.1f}% → {d2:.1f}% → {d3:.1f}%)."
                        if is_breakout:
                            candidate_pattern = {
                                "pattern": "VCP Breakout (3T)",
                                "grade": "A+" if d3 <= 5.0 else "A",
                                "description": f"{desc} Coiled breakout confirmed today on {vol_ratio:.1f}x volume."
                            }
                        else:
                            candidate_pattern = {
                                "pattern": "VCP Consolidation (3T)",
                                "grade": "A" if d3 <= 5.0 else "B+",
                                "description": f"{desc} Price is extremely tight. Watching for breakout above pivot resistance."
                            }
                        if d3 < best_d3:
                            best_d3 = d3
                            best_vcp_pattern = candidate_pattern
        vcp_pattern = best_vcp_pattern

        # Fallback to the original fixed-width 80-day window check if no dynamic pattern is found
        if not vcp_pattern and len(closes) >= 80:
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
                        vcp_pattern = {
                            "pattern": "VCP Breakout (3T)",
                            "grade": "A+" if d3 <= 5.0 else "A",
                            "description": f"{desc} Coiled breakout confirmed today on {vol_ratio:.1f}x volume."
                        }
                    else:
                        vcp_pattern = {
                            "pattern": "VCP Consolidation (3T)",
                            "grade": "A" if d3 <= 5.0 else "B+",
                            "description": f"{desc} Price is extremely tight. Watching for breakout above pivot resistance."
                        }

        if vcp_pattern:
            return vcp_pattern

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