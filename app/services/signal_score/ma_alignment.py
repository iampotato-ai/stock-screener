"""
Multi-timeframe Moving Average alignment scoring.

Computes SMA values for 5, 10, 20, and 60-day periods, bias percentages
(close vs each SMA), and a bullish/bearish alignment score.
"""
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

# Default MA periods matching WorldMonitor's analyze-stock approach
DEFAULT_PERIODS: Tuple[int, ...] = (5, 10, 20, 60)


def _compute_sma(prices: List[float], period: int) -> float:
    """Compute simple moving average for the last `period` prices."""
    if len(prices) < period:
        return 0.0
    return sum(prices[-period:]) / period


def compute_ma_alignment(
    closes: List[float],
    periods: Tuple[int, ...] = DEFAULT_PERIODS,
) -> Dict[str, Any]:
    """
    Compute SMA values and bullish/bearish alignment score.

    Args:
        closes: Daily closing prices, oldest-first.
        periods: MA periods to evaluate (default: 5, 10, 20, 60).

    Returns:
        Dict with:
            sma_values: {sma_5: float, sma_10: float, ...}
            bias_pcts: {sma_5_bias: float, ...} — (close - sma) / sma * 100
            alignment_score: float in [-1.0, +1.0]
            alignment_label: "Bullish Aligned" | "Mostly Bullish" | "Mixed" |
                             "Mostly Bearish" | "Bearish Aligned"
    """
    max_period = max(periods)
    if len(closes) < max_period:
        return _default_result(periods)

    current_close = closes[-1]

    # Compute SMA values
    sma_values: Dict[str, float] = {}
    for p in periods:
        sma_values[f"sma_{p}"] = _compute_sma(closes, p)

    # Compute bias percentages
    bias_pcts: Dict[str, float] = {}
    for p in periods:
        sma_val = sma_values[f"sma_{p}"]
        if sma_val > 0:
            bias_pcts[f"sma_{p}_bias"] = round((current_close - sma_val) / sma_val * 100, 2)
        else:
            bias_pcts[f"sma_{p}_bias"] = 0.0

    # Compute alignment score
    alignment_score = _compute_alignment_score(current_close, sma_values, periods)
    alignment_label = _classify_alignment(alignment_score)

    return {
        "sma_values": sma_values,
        "bias_pcts": bias_pcts,
        "alignment_score": round(alignment_score, 4),
        "alignment_label": alignment_label,
    }


def _compute_alignment_score(
    close: float,
    sma_values: Dict[str, float],
    periods: Tuple[int, ...],
) -> float:
    """
    Score MA alignment from -1.0 (fully bearish) to +1.0 (fully bullish).

    Checks pairwise ordering:
      - Close > shortest SMA > next SMA > ... > longest SMA → +1.0
      - Reverse → -1.0
      - Partial alignment → interpolated
    """
    # Build ordered list: [close, sma_5, sma_10, sma_20, sma_60]
    values = [close] + [sma_values[f"sma_{p}"] for p in sorted(periods)]
    n_pairs = len(values) - 1
    if n_pairs == 0:
        return 0.0

    bullish_pairs = 0
    bearish_pairs = 0
    for i in range(n_pairs):
        if values[i] > values[i + 1]:
            bullish_pairs += 1
        elif values[i] < values[i + 1]:
            bearish_pairs += 1
        # Equal pairs are neutral — don't count either way

    # Score: net bullish pairs / total pairs
    score = (bullish_pairs - bearish_pairs) / n_pairs
    return max(-1.0, min(1.0, score))


def _classify_alignment(score: float) -> str:
    """Map alignment score to a human-readable label."""
    if score >= 0.8:
        return "Bullish Aligned"
    elif score >= 0.3:
        return "Mostly Bullish"
    elif score >= -0.3:
        return "Mixed"
    elif score >= -0.8:
        return "Mostly Bearish"
    else:
        return "Bearish Aligned"


def _default_result(periods: Tuple[int, ...]) -> Dict[str, Any]:
    """Return a neutral default when insufficient data is available."""
    sma_values = {f"sma_{p}": 0.0 for p in periods}
    bias_pcts = {f"sma_{p}_bias": 0.0 for p in periods}
    return {
        "sma_values": sma_values,
        "bias_pcts": bias_pcts,
        "alignment_score": 0.0,
        "alignment_label": "Mixed",
    }
