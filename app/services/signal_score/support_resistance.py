"""
Support and Resistance level computation from price action.

Identifies S/R levels from swing highs and swing lows, clusters nearby
levels into zones, ranks by touch count, and returns the nearest levels.
"""
import logging
from typing import Dict, Any, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Clustering tolerance: levels within this % are merged into one zone
_CLUSTER_TOLERANCE_PCT = 1.5
_SWING_WINDOW = 5
_MIN_BARS = 20


def compute_support_resistance(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    lookback: int = 120,
) -> Dict[str, Any]:
    """
    Compute support and resistance levels from price action.

    Args:
        highs: Daily high prices, oldest-first.
        lows: Daily low prices, oldest-first.
        closes: Daily closing prices, oldest-first.
        lookback: Number of bars to analyze (default 120).

    Returns:
        Dict with:
            nearest_support: float — closest support below current price
            nearest_resistance: float — closest resistance above current price
            key_levels: list of {price, type, strength, touches}
            price_position: float 0.0 (at support) to 1.0 (at resistance)
    """
    if len(highs) < _MIN_BARS or len(lows) < _MIN_BARS:
        current = closes[-1] if closes else 0.0
        return _default_result(current)

    # Use the most recent `lookback` bars
    h = np.array(highs[-lookback:], dtype=np.float64)
    l = np.array(lows[-lookback:], dtype=np.float64)
    current_close = closes[-1]

    # Find swing highs and swing lows
    resistance_levels = _find_swing_highs(h, window=_SWING_WINDOW)
    support_levels = _find_swing_lows(l, window=_SWING_WINDOW)

    # Cluster nearby levels
    all_levels = (
        [(v, "resistance") for v in resistance_levels]
        + [(v, "support") for v in support_levels]
    )
    clustered = _cluster_levels(all_levels, tolerance_pct=_CLUSTER_TOLERANCE_PCT)

    # Find nearest support and resistance relative to current close
    supports = [lv for lv in clustered if lv["price"] < current_close]
    resistances = [lv for lv in clustered if lv["price"] > current_close]

    nearest_support = max((s["price"] for s in supports), default=current_close * 0.95)
    nearest_resistance = min((r["price"] for r in resistances), default=current_close * 1.05)

    # Price position within the S/R band
    sr_range = nearest_resistance - nearest_support
    if sr_range > 0:
        price_position = (current_close - nearest_support) / sr_range
        price_position = max(0.0, min(1.0, price_position))
    else:
        price_position = 0.5

    # Sort key levels by strength (touches)
    key_levels = sorted(clustered, key=lambda x: x["touches"], reverse=True)[:10]

    return {
        "nearest_support": round(nearest_support, 2),
        "nearest_resistance": round(nearest_resistance, 2),
        "key_levels": key_levels,
        "price_position": round(price_position, 4),
    }


def _find_swing_highs(highs: np.ndarray, window: int = 5) -> List[float]:
    """Return values at local maxima positions."""
    peaks = []
    n = len(highs)
    for i in range(window, n - window):
        if highs[i] == np.max(highs[i - window: i + window + 1]):
            peaks.append(float(highs[i]))
    return peaks


def _find_swing_lows(lows: np.ndarray, window: int = 5) -> List[float]:
    """Return values at local minima positions."""
    troughs = []
    n = len(lows)
    for i in range(window, n - window):
        if lows[i] == np.min(lows[i - window: i + window + 1]):
            troughs.append(float(lows[i]))
    return troughs


def _cluster_levels(
    levels: List[Tuple[float, str]],
    tolerance_pct: float = 1.5,
) -> List[Dict[str, Any]]:
    """
    Cluster nearby price levels into zones.

    Levels within `tolerance_pct` of each other are merged. The cluster
    center is the average price, and touches is the count of merged levels.
    """
    if not levels:
        return []

    # Sort by price
    sorted_levels = sorted(levels, key=lambda x: x[0])

    clusters: List[Dict[str, Any]] = []
    current_cluster_prices: List[float] = [sorted_levels[0][0]]
    current_cluster_types: List[str] = [sorted_levels[0][1]]

    for i in range(1, len(sorted_levels)):
        price, level_type = sorted_levels[i]
        cluster_center = sum(current_cluster_prices) / len(current_cluster_prices)
        pct_diff = abs(price - cluster_center) / cluster_center * 100 if cluster_center > 0 else 999

        if pct_diff <= tolerance_pct:
            current_cluster_prices.append(price)
            current_cluster_types.append(level_type)
        else:
            # Finalize current cluster
            clusters.append(_finalize_cluster(current_cluster_prices, current_cluster_types))
            current_cluster_prices = [price]
            current_cluster_types = [level_type]

    # Finalize last cluster
    clusters.append(_finalize_cluster(current_cluster_prices, current_cluster_types))

    return clusters


def _finalize_cluster(
    prices: List[float],
    types: List[str],
) -> Dict[str, Any]:
    """Create a cluster summary dict."""
    avg_price = sum(prices) / len(prices)
    touches = len(prices)

    # Determine dominant type
    res_count = sum(1 for t in types if t == "resistance")
    sup_count = sum(1 for t in types if t == "support")
    dominant_type = "resistance" if res_count >= sup_count else "support"

    # Strength: 1 = weak, 2 = moderate, 3 = strong
    if touches >= 4:
        strength = 3
    elif touches >= 2:
        strength = 2
    else:
        strength = 1

    return {
        "price": round(avg_price, 2),
        "type": dominant_type,
        "strength": strength,
        "touches": touches,
    }


def _default_result(current_close: float) -> Dict[str, Any]:
    """Return default S/R when insufficient data."""
    return {
        "nearest_support": round(current_close * 0.95, 2),
        "nearest_resistance": round(current_close * 1.05, 2),
        "key_levels": [],
        "price_position": 0.5,
    }
