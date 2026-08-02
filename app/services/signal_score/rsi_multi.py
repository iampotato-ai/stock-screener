"""
Multi-period RSI (6, 12, 24) with classification.

Reuses the existing _calculate_rsi() from app/utils/technical.py for
each period, then classifies each and computes a weighted composite score.
"""
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

# Periods and their weights for composite score
RSI_PERIODS: Tuple[Tuple[int, float], ...] = (
    (6, 0.40),   # Short-term — most reactive
    (12, 0.35),  # Medium-term
    (24, 0.25),  # Longer-term — smoothest
)

# Classification boundaries
_OVERBOUGHT = 80
_BULLISH_UPPER = 80
_BULLISH_LOWER = 60
_NEUTRAL_LOWER = 40
_BEARISH_LOWER = 20
_OVERSOLD = 20


def compute_rsi_multi(
    closes: List[float],
    periods: Tuple[Tuple[int, float], ...] = RSI_PERIODS,
) -> Dict[str, Any]:
    """
    Compute RSI for multiple periods and return classifications.

    Args:
        closes: Daily closing prices, oldest-first.
        periods: Tuple of (period, weight) pairs.

    Returns:
        Dict with:
            rsi_values: {rsi_6: float, rsi_12: float, rsi_24: float}
            classifications: {rsi_6: str, rsi_12: str, rsi_24: str}
            composite_score: float in [-1.0, +1.0]
            composite_label: "Overbought" | "Bullish" | "Neutral" | "Bearish" | "Oversold"
    """
    max_period = max(p for p, _ in periods)
    if len(closes) <= max_period:
        return _default_result(periods)

    from app.utils.technical import _calculate_rsi

    rsi_values: Dict[str, float] = {}
    classifications: Dict[str, str] = {}
    weighted_sum = 0.0
    total_weight = 0.0

    for period, weight in periods:
        rsi_val = _calculate_rsi(closes, period=period)
        key = f"rsi_{period}"
        rsi_values[key] = round(rsi_val, 2)
        classifications[key] = _classify_rsi(rsi_val)

        # Normalize RSI to [-1.0, +1.0] for composite scoring
        normalized = _normalize_rsi(rsi_val)
        weighted_sum += normalized * weight
        total_weight += weight

    composite_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    composite_score = max(-1.0, min(1.0, composite_score))
    composite_label = _classify_composite(composite_score)

    return {
        "rsi_values": rsi_values,
        "classifications": classifications,
        "composite_score": round(composite_score, 4),
        "composite_label": composite_label,
    }


def _classify_rsi(rsi: float) -> str:
    """Classify a single RSI value into a human-readable category."""
    if rsi > _OVERBOUGHT:
        return "Overbought"
    elif rsi >= _BULLISH_LOWER:
        return "Bullish"
    elif rsi >= _NEUTRAL_LOWER:
        return "Neutral"
    elif rsi >= _BEARISH_LOWER:
        return "Bearish"
    else:
        return "Oversold"


def _normalize_rsi(rsi: float) -> float:
    """
    Normalize RSI (0–100) to a score in [-1.0, +1.0].

    Mapping:
        RSI 50 → 0.0 (neutral center)
        RSI 100 → +1.0
        RSI 0 → -1.0
    """
    return (rsi - 50.0) / 50.0


def _classify_composite(score: float) -> str:
    """Classify the composite RSI score."""
    if score > 0.6:
        return "Overbought"
    elif score > 0.2:
        return "Bullish"
    elif score >= -0.2:
        return "Neutral"
    elif score >= -0.6:
        return "Bearish"
    else:
        return "Oversold"


def _default_result(periods: Tuple[Tuple[int, float], ...]) -> Dict[str, Any]:
    """Return neutral defaults when RSI cannot be computed."""
    rsi_values = {f"rsi_{p}": 50.0 for p, _ in periods}
    classifications = {f"rsi_{p}": "Neutral" for p, _ in periods}
    return {
        "rsi_values": rsi_values,
        "classifications": classifications,
        "composite_score": 0.0,
        "composite_label": "Neutral",
    }
