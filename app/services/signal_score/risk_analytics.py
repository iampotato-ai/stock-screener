"""
Risk analytics: realized volatility, ATR, and max drawdown.

Computes three risk metrics from daily OHLCV data for the TechnicalSnapshot.
"""
import math
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def compute_risk_analytics(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    vol_period: int = 30,
    atr_period: int = 14,
    drawdown_period: int = 90,
) -> Dict[str, Any]:
    """
    Compute risk metrics from OHLCV data.

    Args:
        closes: Daily closing prices, oldest-first.
        highs: Daily high prices, oldest-first.
        lows: Daily low prices, oldest-first.
        vol_period: Lookback for realized volatility (default 30).
        atr_period: ATR period (default 14).
        drawdown_period: Lookback for max drawdown (default 90).

    Returns:
        Dict with:
            realized_vol_30d: float (annualized, e.g. 0.35 = 35%)
            atr_14: float (absolute INR value)
            atr_14_pct: float (% of close, e.g. 2.5)
            max_drawdown_90d: float (negative decimal, e.g. -0.12)
            risk_label: "Low" | "Medium" | "High" | "Very High"
            risk_score: float in [0.0, 1.0] (1.0 = lowest risk, 0.0 = highest)
    """
    if len(closes) < atr_period + 1:
        return _default_result()

    current_close = closes[-1]

    # 1. Realized volatility (30d annualized)
    realized_vol = _compute_realized_volatility(closes, vol_period)

    # 2. ATR (14-period Wilder smoothing)
    atr = _compute_atr(closes, highs, lows, atr_period)
    atr_pct = (atr / current_close * 100) if current_close > 0 else 0.0

    # 3. Max drawdown (90d)
    max_dd = _compute_max_drawdown(closes, drawdown_period)

    # 4. Risk label and score
    risk_label = _classify_risk(realized_vol, atr_pct, max_dd)
    risk_score = _compute_risk_score(realized_vol, atr_pct, max_dd)

    return {
        "realized_vol_30d": round(realized_vol, 4),
        "atr_14": round(atr, 2),
        "atr_14_pct": round(atr_pct, 2),
        "max_drawdown_90d": round(max_dd, 4),
        "risk_label": risk_label,
        "risk_score": round(risk_score, 4),
    }


def _compute_realized_volatility(closes: List[float], period: int) -> float:
    """
    Annualized realized volatility from log returns.

    Formula: σ = std(ln(c_t / c_{t-1})) × √252
    """
    if len(closes) < period + 1:
        return 0.0

    recent = closes[-(period + 1):]
    log_returns = []
    for i in range(1, len(recent)):
        if recent[i] > 0 and recent[i - 1] > 0:
            log_returns.append(math.log(recent[i] / recent[i - 1]))

    if len(log_returns) < 2:
        return 0.0

    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
    daily_vol = math.sqrt(variance)
    annualized = daily_vol * math.sqrt(252)
    return annualized


def _compute_atr(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    period: int,
) -> float:
    """
    Compute Average True Range using Wilder smoothing.

    TR = max(H-L, |H-Cprev|, |L-Cprev|)
    ATR starts as SMA of first `period` TR values, then Wilder-smoothed.
    """
    n = min(len(closes), len(highs), len(lows))
    if n < period + 1:
        return 0.0

    # Compute True Range series
    tr_values = []
    for i in range(1, n):
        high_low = highs[i] - lows[i]
        high_prev_close = abs(highs[i] - closes[i - 1])
        low_prev_close = abs(lows[i] - closes[i - 1])
        tr_values.append(max(high_low, high_prev_close, low_prev_close))

    if len(tr_values) < period:
        return sum(tr_values) / len(tr_values) if tr_values else 0.0

    # Initial ATR = SMA of first `period` TR values
    atr = sum(tr_values[:period]) / period

    # Wilder smoothing for remaining values
    for i in range(period, len(tr_values)):
        atr = (atr * (period - 1) + tr_values[i]) / period

    return atr


def _compute_max_drawdown(closes: List[float], period: int) -> float:
    """
    Compute maximum drawdown over the trailing `period` bars.

    Returns a negative decimal (e.g. -0.12 means 12% drawdown).
    """
    recent = closes[-period:] if len(closes) >= period else closes
    if len(recent) < 2:
        return 0.0

    running_peak = recent[0]
    max_dd = 0.0

    for price in recent[1:]:
        if price > running_peak:
            running_peak = price
        drawdown = (price - running_peak) / running_peak
        if drawdown < max_dd:
            max_dd = drawdown

    return max_dd


def _classify_risk(vol: float, atr_pct: float, max_dd: float) -> str:
    """Classify overall risk level from metrics."""
    # Score each metric
    risk_points = 0

    if vol > 0.60:
        risk_points += 3
    elif vol > 0.40:
        risk_points += 2
    elif vol > 0.25:
        risk_points += 1

    if atr_pct > 4.0:
        risk_points += 3
    elif atr_pct > 2.5:
        risk_points += 2
    elif atr_pct > 1.5:
        risk_points += 1

    if max_dd < -0.25:
        risk_points += 3
    elif max_dd < -0.15:
        risk_points += 2
    elif max_dd < -0.08:
        risk_points += 1

    if risk_points >= 7:
        return "Very High"
    elif risk_points >= 4:
        return "High"
    elif risk_points >= 2:
        return "Medium"
    else:
        return "Low"


def _compute_risk_score(vol: float, atr_pct: float, max_dd: float) -> float:
    """
    Compute a risk score in [0.0, 1.0].

    1.0 = lowest risk (best), 0.0 = highest risk (worst).
    Used by composite signal to penalize high-risk stocks.
    """
    # Normalize each metric to [0, 1] where 1 = low risk
    vol_score = max(0.0, 1.0 - vol / 0.80)       # 80%+ vol → 0
    atr_score = max(0.0, 1.0 - atr_pct / 6.0)    # 6%+ ATR → 0
    dd_score = max(0.0, 1.0 + max_dd / 0.30)     # -30%+ dd → 0

    # Weighted average
    combined = vol_score * 0.35 + atr_score * 0.35 + dd_score * 0.30
    return max(0.0, min(1.0, combined))


def _default_result() -> Dict[str, Any]:
    """Return neutral defaults when insufficient data."""
    return {
        "realized_vol_30d": 0.0,
        "atr_14": 0.0,
        "atr_14_pct": 0.0,
        "max_drawdown_90d": 0.0,
        "risk_label": "Medium",
        "risk_score": 0.5,
    }
