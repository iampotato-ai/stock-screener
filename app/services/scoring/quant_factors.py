"""
Quant Factor Signals for Momentum Scoring.

Ported and adapted from HKUDS/Vibe-Trading (MIT License).
Source: https://github.com/HKUDS/Vibe-Trading
Factors derived from:
  - Kakushadze (2016) "101 Formulaic Alphas" arXiv:1601.00991 (alpha101)
  - Guotai Junan Securities (2014) short-horizon factor report (gtja191)

All factors are designed for single-stock, single-period evaluation using
data already available in StockDataSchema. Multi-period factors gracefully
degrade to 0 when history is insufficient (< MIN_BARS).

Usage:
    score = score_quant_factors(stock_data, close_history, volume_history)
"""
from __future__ import annotations

import logging
import math
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

MIN_BARS = 5       # Minimum historical bars for multi-period factors
IDEAL_BARS = 20    # Preferred lookback window


# ---------------------------------------------------------------------------
# Single-period factors (require only current OHLCV in stock_data)
# ---------------------------------------------------------------------------

def gtja001(close: float, open_: float) -> float:
    """
    GTJA #1 — Intraday return (close vs open).
    Strong positive = bullish gap fill / momentum continuation.
    Returns a score in [-1, 1].
    """
    if open_ <= 0:
        return 0.0
    return (close - open_) / open_


def gtja006(high: float, open_: float, low: float) -> float:
    """
    GTJA #6 — Buying pressure ratio.
    (high - open) / (open - low + ε). High values indicate sellers dominated.
    Inverted: low ratio (buyers dominated) = bullish signal.
    Returns a normalised score in [-1, 1].
    """
    denom = abs(open_ - low) + 1e-9
    raw = (high - open_) / denom
    # Invert: low raw = bullish; clamp to [-2, 2] then normalise
    inverted = -raw
    return max(-1.0, min(1.0, inverted / 2.0))


def gtja032(close: float, open_: float, high: float, low: float) -> float:
    """
    GTJA #32 — Close location in daily range.
    (close - low) / (high - low + ε). 1.0 = closed at high (bullish).
    Returns a score in [0, 1].
    """
    denom = (high - low) + 1e-9
    return max(0.0, min(1.0, (close - low) / denom))


def alpha012(daily_return: float, volume_ratio: float) -> float:
    """
    Alpha101 #12 — Volume-signed return.
    sign(volume_ratio - 1) * (-1 * sign(daily_return))
    Inverted: rising volume + falling price = bearish divergence (negative).
    Positive output = healthy momentum (volume confirms price direction).
    Returns in [-1, 1].
    """
    vol_sign = 1.0 if volume_ratio >= 1.0 else -1.0
    ret_sign = 1.0 if daily_return >= 0 else -1.0
    return vol_sign * ret_sign


def alpha041(high: float, low: float, volume_ratio: float) -> float:
    """
    Alpha101 #41 — Illiquidity proxy (inverted Amihud ratio).
    Uses intraday range / volume_ratio as a proxy.
    Low illiquidity (easy to trade) = positive signal.
    Returns a score in [0, 1].
    """
    if volume_ratio <= 0:
        return 0.0
    intraday_range = abs(high - low)
    raw_illiq = intraday_range / (volume_ratio * 100.0)  # normalise
    # Invert: lower illiquidity is better; cap at 1
    return max(0.0, min(1.0, 1.0 - raw_illiq))


# ---------------------------------------------------------------------------
# Multi-period factors (require close_history / volume_history lists)
# ---------------------------------------------------------------------------

def _safe_std(values: List[float]) -> float:
    """Population standard deviation, safe for small lists."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return math.sqrt(variance)


def _safe_mean(values: List[float]) -> float:
    """Mean, returns 0.0 on empty."""
    return sum(values) / len(values) if values else 0.0


def gtja026_volume_consistency(volume_history: List[int]) -> float:
    """
    GTJA #26 — Volume consistency signal.
    Low coefficient of variation in volume = consistent institutional buying.
    High CV = erratic / retail-driven volume.
    Returns a score in [0, 1] (higher = more consistent volume).
    """
    if len(volume_history) < MIN_BARS:
        return 0.5  # neutral when insufficient history

    recent = [float(v) for v in volume_history[-10:] if v > 0]
    if not recent:
        return 0.5

    mean_vol = _safe_mean(recent)
    if mean_vol <= 0:
        return 0.5

    cv = _safe_std(recent) / mean_vol   # coefficient of variation
    # Low CV = consistent; map 0→1 (perfect) to 2→0 (chaotic)
    return max(0.0, min(1.0, 1.0 - cv / 2.0))


def alpha001_volume_weighted_alpha(
    close_history: List[float],
    volume_history: List[int]
) -> float:
    """
    Alpha101 #1 — Volume-weighted return deviation.
    Ranks (close - vwap_proxy) cross-sectionally. Here we compute a
    single-stock proxy: excess return vs own volume-weighted average.
    Positive = price above VWAP proxy → bullish.
    Returns a score in [-1, 1].
    """
    if len(close_history) < MIN_BARS or len(volume_history) < MIN_BARS:
        return 0.0

    n = min(len(close_history), len(volume_history), IDEAL_BARS)
    closes = close_history[-n:]
    vols = [float(v) for v in volume_history[-n:]]

    total_vol = sum(vols)
    if total_vol <= 0:
        return 0.0

    vwap_proxy = sum(c * v for c, v in zip(closes, vols)) / total_vol
    last_close = closes[-1]

    if vwap_proxy <= 0:
        return 0.0

    deviation = (last_close - vwap_proxy) / vwap_proxy
    return max(-1.0, min(1.0, deviation * 10.0))   # scale: 10% dev → score 1


def alpha006_open_volume_corr(
    open_history: List[float],
    volume_history: List[int]
) -> float:
    """
    Alpha101 #6 — Open/Volume correlation (institutional footprint).
    Negative correlation between open and volume suggests institutional
    accumulation (buy the open quietly → positive signal when corr < 0).
    Returns a score in [-1, 1]; negative raw corr = positive (bullish).
    """
    if len(open_history) < MIN_BARS or len(volume_history) < MIN_BARS:
        return 0.0

    n = min(len(open_history), len(volume_history), IDEAL_BARS)
    opens = open_history[-n:]
    vols = [float(v) for v in volume_history[-n:]]

    mean_o = _safe_mean(opens)
    mean_v = _safe_mean(vols)

    cov = _safe_mean([(o - mean_o) * (v - mean_v) for o, v in zip(opens, vols)])
    std_o = _safe_std(opens)
    std_v = _safe_std(vols)

    if std_o <= 0 or std_v <= 0:
        return 0.0

    corr = cov / (std_o * std_v)
    # Invert: negative corr = bullish (institutions suppress open, accumulate)
    return max(-1.0, min(1.0, -corr))


def gtja_trend_5d(close_history: List[float]) -> float:
    """
    GTJA short-horizon trend — 5-day price momentum.
    (close_today - close_5d_ago) / close_5d_ago.
    Returns a score in [-1, 1] (positive = uptrend).
    """
    if len(close_history) < 6:
        return 0.0

    close_now = close_history[-1]
    close_5d = close_history[-6]

    if close_5d <= 0:
        return 0.0

    ret = (close_now - close_5d) / close_5d
    return max(-1.0, min(1.0, ret * 5.0))   # scale: 20% move → score 1


# ---------------------------------------------------------------------------
# Composite scorer
# ---------------------------------------------------------------------------

def score_quant_factors(
    stock_data: Dict[str, Any],
    close_history: Optional[List[float]] = None,
    volume_history: Optional[List[int]] = None,
    open_history: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """
    Compute a composite quant-factor score (0–4 points) for the momentum pillar.

    The score blends 5 single-period signals and up to 5 multi-period signals.
    All signals are normalised to [-1, 1] before blending. The final output
    is scaled to [0, 4].

    Args:
        stock_data:      Dict conforming to StockDataSchema.
        close_history:   Optional list of recent daily closes (oldest first).
        volume_history:  Optional list of recent daily volumes (oldest first).
        open_history:    Optional list of recent daily opens (oldest first).

    Returns:
        {
            'score': float,          # 0–4 blended quant signal contribution
            'signal_scores': dict,   # per-factor raw scores
            'factors_computed': int, # how many factors fired
        }
    """
    close  = float(stock_data.get('price', 0) or 0)
    open_  = float(stock_data.get('open_price', close) or close)
    high   = float(stock_data.get('high', close) or close)
    low    = float(stock_data.get('low', close) or close)
    volume_ratio = float(stock_data.get('volume_ratio', 1.0) or 1.0)
    daily_return = float(stock_data.get('momentum_acceleration', 0) or 0) / 100.0

    signals: Dict[str, float] = {}

    # ── Single-period signals ──────────────────────────────────────────────
    if close > 0 and open_ > 0:
        signals['gtja001_intraday_return'] = gtja001(close, open_)
        signals['gtja006_buying_pressure'] = gtja006(high, open_, low)
        signals['gtja032_close_location']  = gtja032(close, open_, high, low)
        signals['alpha012_vol_signed_return'] = alpha012(daily_return, volume_ratio)
        signals['alpha041_illiquidity_inv']   = alpha041(high, low, volume_ratio)

    # ── Multi-period signals (degrade gracefully) ──────────────────────────
    ch = close_history or []
    vh = volume_history or []
    oh = open_history  or []

    signals['gtja026_vol_consistency'] = gtja026_volume_consistency(vh)
    signals['gtja_trend_5d']           = gtja_trend_5d(ch)

    if len(ch) >= MIN_BARS and len(vh) >= MIN_BARS:
        signals['alpha001_vwap_deviation']  = alpha001_volume_weighted_alpha(ch, vh)

    if len(oh) >= MIN_BARS and len(vh) >= MIN_BARS:
        signals['alpha006_open_vol_corr']   = alpha006_open_volume_corr(oh, vh)

    # ── Blend: simple equal-weight average of available signals ───────────
    if not signals:
        return {'score': 0.0, 'signal_scores': {}, 'factors_computed': 0}

    values = list(signals.values())
    avg_signal = sum(values) / len(values)            # in [-1, 1]
    normalised = (avg_signal + 1.0) / 2.0             # to [0, 1]
    composite_score = round(normalised * 4.0, 2)      # scale to [0, 4]

    logger.debug(
        "Quant factors: %d signals, avg=%.3f, score=%.2f",
        len(signals), avg_signal, composite_score
    )

    return {
        'score': composite_score,
        'signal_scores': {k: round(v, 4) for k, v in signals.items()},
        'factors_computed': len(signals),
    }
