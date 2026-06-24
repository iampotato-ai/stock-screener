# bull_snort_service.py
"""Service module implementing the Bull Snort institutional accumulation & breakout filter.

Provides:
- compute_bull_snort(symbol, ...) -> dict | None
- screen_bull_snort(symbols: list[str]) -> list[dict]
- Helper functions for scoring base accumulation and final score.

Feature gated via ENABLE_BULL_SNORT flag.
"""

import logging
import numpy as np
from typing import List, Dict, Any
from flask import current_app

from app.utils.technical import fetch_historical_prices

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds — tune via backtesting
# ---------------------------------------------------------------------------
DEFAULT_VOL_AVG_PERIOD = 20  # rolling avg period for Bull Snort candle volume
DEFAULT_VOL_SURGE_MIN = 3.0  # Bull Snort candle: min vol ratio
DEFAULT_CLOSE_POSITION_MIN = 0.65  # Bull Snort candle: min close position (top 35%)
DEFAULT_MIN_GAP_HISTORY = 10.0  # Phase 1: price must have been 10%+ below DMA
DEFAULT_MAX_CURRENT_GAP = 5.0  # Phase 2: price must be within 5% of DMA now
BASE_LOOKBACK_DAYS = 126  # 6 months of trading days
BASE_NO_NEW_LOW_WINDOW = 10  # Phase 2: no new low in last N sessions
MIN_ROWS_REQUIRED = 230  # Minimum rows of historical data required for Bull Snort calculation


def _has_sufficient_history(symbol: str) -> bool:
    """Return True iff the symbol has at least MIN_ROWS_REQUIRED rows of history."""
    hist = fetch_historical_prices(symbol, range_str="2y")
    return hist is not None and len(hist) >= MIN_ROWS_REQUIRED

# ---------------------------------------------------------------------------
# Helper: base volume accumulation scoring
# ---------------------------------------------------------------------------
def _score_base_accumulation(close, volume, dma200, lookback) -> Dict[str, Any]:
    """Score institutional volume accumulation during the base period.

    Parameters:
        close (pd.Series): Close price series.
        volume (pd.Series): Volume series.
        dma200 (pd.Series): 200‑day moving average of close.
        lookback (int): Number of days to look back (e.g., 126).

    Returns:
        dict: {'accumulation_score': float, 'pivot_score': float, 'surge_score': float}
    """
    # Extract base window
    base_close = close.iloc[-lookback:]
    base_volume = volume.iloc[-lookback:]
    base_dma = dma200.iloc[-lookback:]

    # Only count when price is below DMA
    mask = base_close < base_dma
    vol_below = base_volume[mask]

    # Detect pivots (local maxima) and surges (>= 2x 20‑day avg)
    def detect_volume_pivots(series, lookback=2):
        pivots = []
        for i in range(lookback, len(series) - lookback):
            window = series.iloc[i - lookback : i + lookback + 1]
            if series.iloc[i] == window.max():
                pivots.append(i)
        return pivots

    def detect_volume_surges(series, avg_period=20, surge_multiplier=2.0):
        avg_vol = series.rolling(avg_period).mean()
        surges = series >= avg_vol * surge_multiplier
        return surges[surges].index.tolist()

    n_pivots = len(detect_volume_pivots(vol_below))
    n_surges = len(detect_volume_surges(vol_below))

    # Scoring: up to 100 points each, weighted equally
    pivot_score = min(n_pivots / 5.0, 1.0) * 100
    surge_score = min(n_surges / 3.0, 1.0) * 100
    accumulation_score = (pivot_score * 0.5) + (surge_score * 0.5)

    return {
        "n_pivots": n_pivots,
        "n_surges": n_surges,
        "pivot_score": pivot_score,
        "surge_score": surge_score,
        "accumulation_score": accumulation_score,
    }

# ---------------------------------------------------------------------------
# Helper: final score composition
# ---------------------------------------------------------------------------
def _compute_final_score(
    vol_ratio: float,
    vol_surge_min: float,
    pct_change: float,
    close_position: float,
    accum_score: float,
    current_gap: float,
    max_gap_6mo: float,
) -> float:
    """Combine phase‑4 metrics with base accumulation into a final score (0‑100)."""
    # Simple weighted sum – weights tuned for typical market conditions
    weights = {
        "vol_ratio": 0.2,
        "pct_change": 0.15,
        "close_position": 0.15,
        "accum_score": 0.3,
        "gap": 0.1,
        "max_gap_6mo": 0.1,
    }
    # Normalise components to 0‑1 where appropriate
    vol_norm = min(vol_ratio / vol_surge_min, 1.0)
    pct_norm = min(pct_change / 5.0, 1.0)  # treat 5%+ as max
    close_norm = close_position  # already 0‑1
    gap_norm = 1.0 - (current_gap / DEFAULT_MAX_CURRENT_GAP) if DEFAULT_MAX_CURRENT_GAP else 0.0
    max_gap_norm = min(max_gap_6mo / DEFAULT_MIN_GAP_HISTORY, 1.0)

    score = (
        weights["vol_ratio"] * vol_norm
        + weights["pct_change"] * pct_norm
        + weights["close_position"] * close_norm
        + weights["accum_score"] * (accum_score / 100.0)
        + weights["gap"] * gap_norm
        + weights["max_gap_6mo"] * max_gap_norm
    )
    return round(score * 100, 2)

# ---------------------------------------------------------------------------
# Public API: compute a single symbol
# ---------------------------------------------------------------------------
def compute_bull_snort(
    symbol: str,
    vol_avg_period: int = DEFAULT_VOL_AVG_PERIOD,
    vol_surge_min: float = DEFAULT_VOL_SURGE_MIN,
    close_position_min: float = DEFAULT_CLOSE_POSITION_MIN,
    min_gap_history: float = DEFAULT_MIN_GAP_HISTORY,
    max_current_gap: float = DEFAULT_MAX_CURRENT_GAP,
) -> Dict[str, Any] | None:
    """Run the full 4‑phase Bull Snort evaluation for *symbol*.

    Returns a dict with the computed score and candle details, or ``None`` if any required phase fails.
    """
    try:
        df = fetch_historical_prices(symbol, range_str="2y")
        if df is None or len(df) < 230:
            logger.warning("%s: insufficient data", symbol)
            return None

        df = df.sort_index()
        close = df["Close"]
        volume = df["Volume"]
        high = df["High"]
        low = df["Low"]
        dma200 = close.rolling(200).mean()
        if np.isnan(dma200.iloc[-1]):
            return None

        # Phase 1 – deep downtrend & DMA still declining
        gap_series = (dma200 - close) / close * 100
        max_gap_6mo = gap_series.iloc[-BASE_LOOKBACK_DAYS :].max()
        if max_gap_6mo < min_gap_history:
            return None
        dma_slope = (dma200.iloc[-1] - dma200.iloc[-21]) / 20
        norm_slope = (dma_slope / dma200.iloc[-1]) * 100
        if norm_slope >= 0:
            return None

        # Phase 2 – base formation
        recent_lows = close.iloc[-(BASE_NO_NEW_LOW_WINDOW + 1) : -1]
        if close.iloc[-1] < recent_lows.min():
            return None
        current_gap = (dma200.iloc[-1] - close.iloc[-1]) / close.iloc[-1] * 100
        if not (0 <= current_gap <= max_current_gap):
            return None

        # Phase 3 – accumulation score
        accum_result = _score_base_accumulation(close, volume, dma200, BASE_LOOKBACK_DAYS)

        # Phase 4 – candlestick breakout
        today_close = close.iloc[-1]
        prev_close = close.iloc[-2]
        today_high = high.iloc[-1]
        today_low = low.iloc[-1]
        today_vol = volume.iloc[-1]
        avg_vol = volume.iloc[-(vol_avg_period + 1) : -1].mean()
        vol_ratio = today_vol / avg_vol if avg_vol > 0 else 0.0
        is_vol_surge = vol_ratio >= vol_surge_min
        is_positive = today_close > prev_close
        candle_range = today_high - today_low
        if candle_range == 0:
            return None
        close_position = (today_close - today_low) / candle_range
        is_strong_close = close_position >= close_position_min
        if not (is_vol_surge and is_positive and is_strong_close):
            return None

        # Final score composition
        final_score = _compute_final_score(
            vol_ratio=vol_ratio,
            vol_surge_min=vol_surge_min,
            pct_change=(today_close - prev_close) / prev_close * 100,
            close_position=close_position,
            accum_score=accum_result["accumulation_score"],
            current_gap=current_gap,
            max_gap_6mo=max_gap_6mo,
        )

        return {
            "symbol": symbol,
            "date": str(df.index[-1].date()),
            # Candle
            "open": round(df["Open"].iloc[-1], 2),
            "high": round(today_high, 2),
            "low": round(today_low, 2),
            "close": round(today_close, 2),
            "prev_close": round(prev_close, 2),
            "pct_change": round((today_close - prev_close) / prev_close * 100, 2),
            # Volume
            "volume": int(today_vol),
            "avg_volume": int(avg_vol),
            "vol_ratio": round(vol_ratio, 3),
            # Candle strength
            "close_position": round(close_position, 3),
            "candle_range": round(candle_range, 2),
            # DMA context
            "dma200": round(dma200.iloc[-1], 2),
            "current_gap_pct": round(current_gap, 2),
            "max_gap_6mo_pct": round(max_gap_6mo, 2),
            "dma_slope_norm": round(norm_slope, 4),
            # Base accumulation
            "n_vol_pivots": accum_result["n_pivots"],
            "n_vol_surges": accum_result["n_surges"],
            "accumulation_score": round(accum_result["accumulation_score"], 2),
            # Final score
            "final_score": final_score,
        }
    except Exception as exc:
        logger.exception("Error computing Bull Snort for %s", symbol)
        return None

# ---------------------------------------------------------------------------
# Public API: screen a list of symbols
# ---------------------------------------------------------------------------
def screen_bull_snort(
    symbols: List[str],
    vol_avg_period: int = DEFAULT_VOL_AVG_PERIOD,
    vol_surge_min: float = DEFAULT_VOL_SURGE_MIN,
    close_position_min: float = DEFAULT_CLOSE_POSITION_MIN,
    min_gap_history: float = DEFAULT_MIN_GAP_HISTORY,
    max_current_gap: float = DEFAULT_MAX_CURRENT_GAP,
) -> List[Dict[str, Any]]:
    """Run ``compute_bull_snort`` for each symbol in *symbols* and return successful results.
    """
    results = []
    skipped = []  # for optional diagnostic cache
    for sym in symbols:
        if not _has_sufficient_history(sym):
            skipped.append(sym)
            continue  # silent skip
        res = compute_bull_snort(
            sym,
            vol_avg_period=vol_avg_period,
            vol_surge_min=vol_surge_min,
            close_position_min=close_position_min,
            min_gap_history=min_gap_history,
            max_current_gap=max_current_gap,
        )
        if res:
            results.append(res)

    # Update diagnostic cache if any symbols were skipped
    if skipped:
        current_app.config.setdefault('BULL_SNORT_SKIPPED', set()).update(skipped)

    # Sort results by final score descending
    results.sort(key=lambda x: x.get('final_score', 0), reverse=True)
    return results
__all__ = [
    "compute_bull_snort",
    "screen_bull_snort",
    "_score_base_accumulation",
    "_compute_final_score",
]
