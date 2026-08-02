"""
Volume regime classification.

Classifies today's volume action into one of six regimes based on
relative volume (RVOL) and price direction.
"""
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# RVOL thresholds
_HEAVY_THRESHOLD = 1.5
_SHRINK_THRESHOLD = 0.7
_RVOL_LOOKBACK = 20  # 20-day average volume


def classify_volume(
    closes: List[float],
    volumes: List[int],
    lookback: int = _RVOL_LOOKBACK,
) -> Dict[str, Any]:
    """
    Classify today's volume regime.

    Args:
        closes: Daily closing prices, oldest-first.
        volumes: Daily volumes, oldest-first (same length as closes).
        lookback: Period for average volume calculation (default 20).

    Returns:
        Dict with:
            regime: "Heavy Up" | "Light Up" | "Shrink Up" |
                    "Heavy Down" | "Light Down" | "Shrink Down"
            rvol: float (today_volume / avg_volume)
            today_volume: int
            avg_volume: float
            price_change_pct: float
            score: float in [-1.0, +1.0]
    """
    if len(closes) < 2 or len(volumes) < 2:
        return _default_result()

    if len(closes) != len(volumes):
        logger.warning("closes and volumes length mismatch: %d vs %d",
                       len(closes), len(volumes))
        min_len = min(len(closes), len(volumes))
        closes = closes[-min_len:]
        volumes = volumes[-min_len:]

    today_close = closes[-1]
    prev_close = closes[-2]
    today_volume = volumes[-1]

    # Handle edge case of zero/None volume
    if today_volume is None or today_volume <= 0:
        return _default_result()

    # Compute average volume (excluding today)
    vol_window = volumes[-(lookback + 1):-1] if len(volumes) > lookback else volumes[:-1]
    if not vol_window:
        return _default_result()

    avg_volume = sum(vol_window) / len(vol_window) if vol_window else 1.0
    if avg_volume <= 0:
        avg_volume = 1.0

    rvol = today_volume / avg_volume
    price_change_pct = ((today_close - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
    is_up = price_change_pct >= 0

    # Classify regime
    regime = _classify_regime(is_up, rvol)
    score = _compute_score(regime, rvol, price_change_pct)

    return {
        "regime": regime,
        "rvol": round(rvol, 2),
        "today_volume": today_volume,
        "avg_volume": round(avg_volume, 0),
        "price_change_pct": round(price_change_pct, 2),
        "score": round(score, 4),
    }


def _classify_regime(is_up: bool, rvol: float) -> str:
    """Classify into one of six volume regimes."""
    if is_up:
        if rvol >= _HEAVY_THRESHOLD:
            return "Heavy Up"
        elif rvol < _SHRINK_THRESHOLD:
            return "Shrink Up"
        else:
            return "Light Up"
    else:
        if rvol >= _HEAVY_THRESHOLD:
            return "Heavy Down"
        elif rvol < _SHRINK_THRESHOLD:
            return "Shrink Down"
        else:
            return "Light Down"


def _compute_score(regime: str, rvol: float, price_change_pct: float) -> float:
    """
    Map volume regime to a score in [-1.0, +1.0].

    Heavy Up is most bullish (+1.0), Heavy Down most bearish (-1.0).
    Shrink regimes are closer to neutral (low conviction).
    """
    regime_scores = {
        "Heavy Up": 0.8,
        "Light Up": 0.3,
        "Shrink Up": 0.1,       # Low conviction rally
        "Shrink Down": -0.1,    # Low conviction decline
        "Light Down": -0.3,
        "Heavy Down": -0.8,
    }
    base = regime_scores.get(regime, 0.0)

    # Modulate slightly by RVOL magnitude for Heavy regimes
    if regime in ("Heavy Up", "Heavy Down"):
        mag_bonus = min((rvol - _HEAVY_THRESHOLD) / 5.0, 0.2)
        if regime == "Heavy Up":
            base = min(1.0, base + mag_bonus)
        else:
            base = max(-1.0, base - mag_bonus)

    return max(-1.0, min(1.0, base))


def _default_result() -> Dict[str, Any]:
    """Return neutral defaults when volume data is insufficient."""
    return {
        "regime": "Light Up",
        "rvol": 1.0,
        "today_volume": 0,
        "avg_volume": 0.0,
        "price_change_pct": 0.0,
        "score": 0.0,
    }
