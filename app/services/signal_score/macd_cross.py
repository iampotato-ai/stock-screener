"""
MACD golden/death cross detection with status classification.

Wraps the existing compute_macd() from fetcher_utils and adds cross-type
detection, approaching-state identification, and sustained-direction counting.
"""
import logging
import math
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def compute_macd_cross(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> Dict[str, Any]:
    """
    Compute MACD values and detect cross type.

    Args:
        closes: Daily closing prices, oldest-first.
        fast: Fast EMA period (default 12).
        slow: Slow EMA period (default 26).
        signal_period: Signal line EMA period (default 9).

    Returns:
        Dict with macd_line, signal_line, histogram, cross_type,
        bars_since_cross, and score (-1.0 to +1.0).
    """
    min_required = slow + signal_period + 5  # Need extra bars for cross detection
    if len(closes) < min_required:
        return _default_result()

    try:
        from app.services.scoring.fetcher_utils import compute_macd
        macd_line_list, signal_list, hist_list = compute_macd(
            closes, fast_period=fast, slow_period=slow, signal_period=signal_period
        )
    except Exception as e:
        logger.warning("Failed to compute MACD: %s", e)
        return _default_result()

    # Get the last valid values
    macd_val = _last_valid(macd_line_list)
    signal_val = _last_valid(signal_list)
    hist_val = _last_valid(hist_list)

    if math.isnan(macd_val) or math.isnan(signal_val):
        return _default_result()

    # Detect cross type from histogram series
    cross_type, bars_since = _detect_cross(hist_list)

    # Compute score
    score = _compute_score(cross_type, hist_val, bars_since)

    return {
        "macd_line": round(macd_val, 4),
        "signal_line": round(signal_val, 4),
        "histogram": round(hist_val, 4),
        "cross_type": cross_type,
        "bars_since_cross": bars_since,
        "score": round(score, 4),
    }


def _detect_cross(hist_list: List[float]) -> tuple:
    """
    Detect the most recent cross type from the MACD histogram series.

    Returns:
        (cross_type, bars_since_cross) tuple.

    Cross types:
        golden_cross      — histogram just flipped positive (within last 3 bars)
        death_cross        — histogram just flipped negative (within last 3 bars)
        approaching_golden — histogram negative but narrowing for 2+ bars
        approaching_death  — histogram positive but narrowing for 2+ bars
        sustained_bull     — histogram positive for 5+ consecutive bars
        sustained_bear     — histogram negative for 5+ consecutive bars
        none               — no clear pattern
    """
    # Filter out NaN values from the end
    valid_hist = []
    for v in reversed(hist_list):
        if not math.isnan(v):
            valid_hist.insert(0, v)
        else:
            break
    # We need at least the tail portion
    if len(valid_hist) < 3:
        return "none", 0

    # Use last 20 bars max for efficiency
    recent = valid_hist[-20:]
    current_hist = recent[-1]

    # Count consecutive bars in current direction
    consecutive = 0
    current_sign = 1 if current_hist >= 0 else -1
    for v in reversed(recent):
        v_sign = 1 if v >= 0 else -1
        if v_sign == current_sign:
            consecutive += 1
        else:
            break

    # Check for recent cross (flip within last 3 bars)
    if consecutive <= 3 and len(recent) > consecutive:
        prev_sign = 1 if recent[-(consecutive + 1)] >= 0 else -1
        if current_sign == 1 and prev_sign == -1:
            return "golden_cross", consecutive
        elif current_sign == -1 and prev_sign == 1:
            return "death_cross", consecutive

    # Check for sustained direction (5+ bars)
    if consecutive >= 5:
        if current_sign == 1:
            return "sustained_bull", consecutive
        else:
            return "sustained_bear", consecutive

    # Check for approaching cross (narrowing histogram)
    if len(recent) >= 3:
        last_3 = [abs(v) for v in recent[-3:]]
        is_narrowing = last_3[-1] < last_3[-2] < last_3[-3]
        if is_narrowing:
            if current_hist < 0:
                return "approaching_golden", consecutive
            else:
                return "approaching_death", consecutive

    return "none", consecutive


def _compute_score(cross_type: str, histogram: float, bars_since: int) -> float:
    """Map cross type to a score from -1.0 to +1.0."""
    score_map = {
        "golden_cross": 0.8,
        "sustained_bull": 0.6,
        "approaching_golden": 0.3,
        "none": 0.0,
        "approaching_death": -0.3,
        "sustained_bear": -0.6,
        "death_cross": -0.8,
    }
    base = score_map.get(cross_type, 0.0)

    # Modulate by histogram magnitude (stronger histogram = stronger signal)
    if histogram != 0:
        mag_bonus = min(abs(histogram) / 5.0, 0.2)  # Cap at ±0.2
        if histogram > 0:
            base = min(1.0, base + mag_bonus)
        else:
            base = max(-1.0, base - mag_bonus)

    return max(-1.0, min(1.0, base))


def _last_valid(values: List[float]) -> float:
    """Return the last non-NaN value from a list."""
    for v in reversed(values):
        if not math.isnan(v):
            return v
    return float("nan")


def _default_result() -> Dict[str, Any]:
    """Return neutral defaults when MACD cannot be computed."""
    return {
        "macd_line": 0.0,
        "signal_line": 0.0,
        "histogram": 0.0,
        "cross_type": "none",
        "bars_since_cross": 0,
        "score": 0.0,
    }
