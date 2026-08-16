"""Multiyear Breakout Scanner Service.

Identifies NSE stocks breaking out to all-time highs after consolidating
for 5+ years.  The scanner fetches full price history via yfinance ``max``
range, determines the prior ATH, checks base length, and filters for
recent breakouts.

Public API
----------
- ``scan_multiyear_breakouts(symbols, ...)`` – batch scan returning list of
  qualifying breakout dicts.
- ``compute_single_breakout(symbol, history, ...)`` – pure function for a
  single stock.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults — overridable via Flask config or API query params
# ---------------------------------------------------------------------------
DEFAULT_MIN_BASE_YEARS = 5
DEFAULT_BREAKOUT_WINDOW_DAYS = 10
DEFAULT_VOLUME_AVG_PERIOD = 20
MIN_HISTORY_YEARS = 5  # skip stocks with < 5 years of data


# ---------------------------------------------------------------------------
# High-speed Yahoo Finance v8 Chart Helper (with retry & rate-limit resilience)
# ---------------------------------------------------------------------------

YAHOO_V8_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=0&period2=9999999999&interval=1d"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _fetch_max_history(symbol: str, retries: int = 2) -> Optional[List[Dict[str, Any]]]:
    """Fetch full multi-decade price history for *symbol* using direct Yahoo Finance v8 chart API.

    Returns a list of dicts with keys ``date``, ``open``, ``high``, ``low``,
    ``close``, ``volume`` sorted ascending by date, or ``None`` on failure.
    """
    import urllib.request
    import urllib.error
    import json

    ticker_str = symbol
    if not ticker_str.endswith(".NS") and not ticker_str.endswith(".BO") and not ticker_str.startswith("^"):
        ticker_str = f"{ticker_str}.NS"

    url = YAHOO_V8_CHART_URL.format(symbol=ticker_str)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode('utf-8'))

            if not data.get('chart') or not data['chart'].get('result') or not data['chart']['result']:
                return None

            result = data['chart']['result'][0]
            timestamps = result.get('timestamp')
            if not timestamps:
                return None

            quote = result.get('indicators', {}).get('quote', [{}])[0]
            adj_list = result.get('indicators', {}).get('adjclose', [{}])[0].get('adjclose', [])

            opens = quote.get('open', [])
            highs = quote.get('high', [])
            lows = quote.get('low', [])
            closes = quote.get('close', [])
            volumes = quote.get('volume', [])

            rows: List[Dict[str, Any]] = []
            for i in range(len(timestamps)):
                raw_c = closes[i] if i < len(closes) else None
                if raw_c is None or raw_c <= 0:
                    continue

                adj_c = adj_list[i] if i < len(adj_list) and adj_list[i] is not None and adj_list[i] > 0 else raw_c
                adj_factor = adj_c / raw_c if raw_c > 0 else 1.0

                raw_o = opens[i] if i < len(opens) and opens[i] is not None else raw_c
                raw_h = highs[i] if i < len(highs) and highs[i] is not None else raw_c
                raw_l = lows[i] if i < len(lows) and lows[i] is not None else raw_c
                v = volumes[i] if i < len(volumes) and volumes[i] is not None else 0

                dt_str = datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d')
                rows.append({
                    "date": dt_str,
                    "open": round(float(raw_o) * adj_factor, 2),
                    "high": round(float(raw_h) * adj_factor, 2),
                    "low": round(float(raw_l) * adj_factor, 2),
                    "close": round(float(adj_c), 2),
                    "volume": int(v),
                })
            return rows if len(rows) > 0 else None

        except urllib.error.HTTPError as http_err:
            if http_err.code == 429 and attempt < retries:
                time.sleep(1.0 * (attempt + 1))
                continue
            logger.debug("HTTP %s fetching max-history for %s", http_err.code, symbol)
            break
        except Exception as exc:
            if attempt < retries:
                time.sleep(0.5)
                continue
            logger.debug("Fetch failed for %s: %s", symbol, exc)
            break

    # Fallback to yfinance if direct v8 endpoint failed
    try:
        import yfinance as yf
        ticker = yf.Ticker(ticker_str)
        df = ticker.history(period="max", auto_adjust=True)
        if df is not None and not df.empty:
            rows = []
            for idx, row in df.iterrows():
                dt = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
                close_val = float(row.get("Close", 0))
                if close_val <= 0:
                    continue
                rows.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "open": float(row.get("Open", 0)),
                    "high": float(row.get("High", 0)),
                    "low": float(row.get("Low", 0)),
                    "close": close_val,
                    "volume": int(row.get("Volume", 0)),
                })
            return rows if len(rows) > 0 else None
    except Exception:
        pass

    return None


def _fetch_nifty_history() -> Optional[List[Dict[str, Any]]]:
    """Fetch Nifty 50 full history for RS calculation."""
    return _fetch_max_history("^NSEI")


# ---------------------------------------------------------------------------
# Single-stock breakout detection (pure function)
# ---------------------------------------------------------------------------

def compute_single_breakout(
    symbol: str,
    history: List[Dict[str, Any]],
    nifty_history: Optional[List[Dict[str, Any]]] = None,
    min_base_years: int = DEFAULT_MIN_BASE_YEARS,
    breakout_window_days: int = DEFAULT_BREAKOUT_WINDOW_DAYS,
    market_cap_cr: Optional[float] = None,
    sector: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Analyse a single stock's full history for a multiyear ATH breakout.

    Parameters
    ----------
    symbol : str
        Ticker symbol (plain, e.g. ``RELIANCE``).
    history : list[dict]
        Full OHLCV history sorted ascending by date.
    nifty_history : list[dict] | None
        Nifty 50 history for RS calculation.
    min_base_years : int
        Minimum years the stock must have traded below its prior ATH.
    breakout_window_days : int
        The breakout must have occurred within the last N trading days.
    market_cap_cr : float | None
        Market capitalisation in ₹ Crores (for display).
    sector : str | None
        Sector name (for display).

    Returns
    -------
    dict | None
        Breakout record if the stock qualifies, otherwise ``None``.
    """
    if not history or len(history) < 252 * min_base_years:
        return None  # not enough data

    closes = [bar["close"] for bar in history]
    dates = [bar["date"] for bar in history]
    volumes = [bar["volume"] for bar in history]
    n = len(closes)

    # --- Step 1: Find the all-time high *before* the recent window ----------
    # We want the prior ATH — the peak that was set historically, which is now
    # being broken.  Look at the entire history *except* the last
    # ``breakout_window_days`` bars.
    cutoff = max(0, n - breakout_window_days)
    if cutoff < 252:
        return None  # not enough pre-breakout history

    prior_closes = closes[:cutoff]
    prior_ath = max(prior_closes)
    prior_ath_idx = prior_closes.index(prior_ath)
    prior_ath_date = dates[prior_ath_idx]

    # --- Step 2: Was the ATH set ≥ min_base_years ago? ----------------------
    try:
        ath_dt = datetime.strptime(prior_ath_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    latest_dt_str = dates[-1]
    try:
        latest_dt = datetime.strptime(latest_dt_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    years_since_ath = (latest_dt - ath_dt).days / 365.25
    if years_since_ath < min_base_years:
        return None

    # --- Step 3: Check that stock was BELOW the ATH for the base period -----
    # Verify the stock didn't touch or exceed the ATH between the ATH date and
    # the breakout window.  Allow a small tolerance of 1% to handle noise.
    tolerance = prior_ath * 0.01
    for i in range(prior_ath_idx + 1, cutoff):
        if closes[i] >= prior_ath - tolerance:
            # The stock revisited the ATH — this isn't a clean long base.
            # Reset the "prior ATH" to this revisit if it's higher.
            if closes[i] > prior_ath:
                prior_ath = closes[i]
                prior_ath_idx = i
                prior_ath_date = dates[i]

    # Re-check years since the *adjusted* ATH
    try:
        ath_dt = datetime.strptime(prior_ath_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    years_since_ath = (latest_dt - ath_dt).days / 365.25
    if years_since_ath < min_base_years:
        return None

    # --- Step 4: Has it broken out recently? --------------------------------
    recent_closes = closes[cutoff:]
    breakout_occurred = False
    breakout_date = None
    for i, c in enumerate(recent_closes):
        if c > prior_ath:
            breakout_occurred = True
            breakout_date = dates[cutoff + i]
            break

    if not breakout_occurred:
        return None

    # --- Step 5: Compute metrics -------------------------------------------
    current_price = closes[-1]
    pct_above_ath = round((current_price - prior_ath) / prior_ath * 100, 2)

    # Volume confirmation: was breakout-day volume above 20-day average?
    breakout_abs_idx = cutoff + (recent_closes.index(
        next(c for c in recent_closes if c > prior_ath)
    ) if breakout_occurred else 0)
    vol_avg_start = max(0, breakout_abs_idx - DEFAULT_VOLUME_AVG_PERIOD)
    avg_vol = np.mean(volumes[vol_avg_start:breakout_abs_idx]) if breakout_abs_idx > vol_avg_start else 0
    breakout_vol = volumes[breakout_abs_idx] if breakout_abs_idx < n else 0
    volume_confirmed = bool(avg_vol > 0 and breakout_vol > avg_vol * 1.0)

    # Consolidation range: (ATH - base_low) / ATH * 100
    base_closes = closes[prior_ath_idx:cutoff]
    base_low = min(base_closes) if base_closes else prior_ath
    consolidation_range = round((prior_ath - base_low) / prior_ath * 100, 2)

    # RS vs Nifty 50 (50-day relative performance)
    rs_vs_nifty = None
    if nifty_history and len(nifty_history) >= 50:
        nifty_closes = [bar["close"] for bar in nifty_history]
        nifty_50d_return = (nifty_closes[-1] - nifty_closes[-50]) / nifty_closes[-50] if nifty_closes[-50] else 0
        stock_50d_return = (closes[-1] - closes[-50]) / closes[-50] if len(closes) >= 50 and closes[-50] else 0
        rs_vs_nifty = round(stock_50d_return - nifty_50d_return, 4)

    return {
        "symbol": symbol,
        "current_price": round(current_price, 2),
        "prior_ath_price": round(prior_ath, 2),
        "prior_ath_date": prior_ath_date,
        "breakout_date": breakout_date,
        "years_below_ath": round(years_since_ath, 1),
        "pct_above_ath": pct_above_ath,
        "volume_confirmed": volume_confirmed,
        "breakout_volume": breakout_vol,
        "avg_volume_20d": int(avg_vol) if avg_vol else 0,
        "consolidation_range_pct": consolidation_range,
        "base_low": round(base_low, 2),
        "market_cap_cr": market_cap_cr,
        "sector": sector,
        "rs_vs_nifty": rs_vs_nifty,
    }


# ---------------------------------------------------------------------------
# Batch scanner
# ---------------------------------------------------------------------------

def scan_multiyear_breakouts(
    symbols: List[str],
    min_base_years: int = DEFAULT_MIN_BASE_YEARS,
    breakout_window_days: int = DEFAULT_BREAKOUT_WINDOW_DAYS,
    max_workers: int = 10,
) -> List[Dict[str, Any]]:
    """Scan a list of symbols for multiyear ATH breakouts.

    Fetches full yfinance history in parallel, runs
    ``compute_single_breakout`` on each, and returns the list of qualifying
    breakout records sorted by ``years_below_ath`` descending.
    """
    if not symbols:
        return []

    logger.info(
        "Multiyear Breakout scan starting: %d symbols, min_base=%d yr, window=%d days",
        len(symbols), min_base_years, breakout_window_days,
    )

    # Fetch Nifty 50 history once for RS calculation
    nifty_history = _fetch_nifty_history()

    # Fetch market cap data for display
    market_caps: Dict[str, float] = {}
    sectors: Dict[str, str] = {}
    try:
        from flask import has_app_context
        if has_app_context():
            from app.database import fetch_all
            rows = fetch_all(
                "SELECT ticker, market_cap_inr FROM market_cap_cache"
            )
            if rows:
                for row in rows:
                    ticker = row["ticker"]
                    cap_inr = row["market_cap_inr"]
                    if cap_inr:
                        market_caps[ticker] = round(float(cap_inr) / 1e7, 2)  # Convert to Crores
    except Exception as e:
        logger.warning("Failed to load market_cap_cache: %s", e)

    results: List[Dict[str, Any]] = []
    processed = 0
    failed = 0

    def _process(sym: str) -> Optional[Dict[str, Any]]:
        history = _fetch_max_history(sym)
        if not history:
            return None

        res = compute_single_breakout(
            symbol=sym,
            history=history,
            nifty_history=nifty_history,
            min_base_years=min_base_years,
            breakout_window_days=breakout_window_days,
            market_cap_cr=market_caps.get(sym),
            sector=sectors.get(sym, "General"),
        )
        if res is None:
            return None

        # Only fetch sector & market cap info from Yahoo for candidates that actually qualify
        if res.get("sector") in (None, "General", "N/A") or res.get("market_cap_cr") is None:
            try:
                import yfinance as yf
                ticker_str = f"{sym}.NS" if not sym.endswith((".NS", ".BO")) else sym
                info = yf.Ticker(ticker_str).info or {}
                if res.get("sector") in (None, "General", "N/A"):
                    res["sector"] = info.get("sector", "General")
                if res.get("market_cap_cr") is None:
                    cap = info.get("marketCap")
                    if cap:
                        res["market_cap_cr"] = round(float(cap) / 1e7, 2)
            except Exception:
                if not res.get("sector"):
                    res["sector"] = "General"

        return res

    effective_workers = min(max_workers, max(1, len(symbols)))

    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        future_to_sym = {executor.submit(_process, sym): sym for sym in symbols}
        for future in as_completed(future_to_sym):
            sym = future_to_sym[future]
            processed += 1
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception as exc:
                failed += 1
                logger.warning("Multiyear breakout scan failed for %s: %s", sym, exc)

            if processed % 50 == 0:
                logger.info(
                    "Multiyear Breakout progress: %d/%d processed, %d found so far",
                    processed, len(symbols), len(results),
                )

    # Sort by years_below_ath descending (longest bases first)
    results.sort(key=lambda r: r.get("years_below_ath", 0), reverse=True)

    logger.info(
        "Multiyear Breakout scan complete: %d/%d symbols processed, "
        "%d breakouts found, %d failures",
        processed, len(symbols), len(results), failed,
    )
    return results
