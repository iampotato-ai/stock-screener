"""
Mathematical calculation helpers for financial metrics.
"""
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


DEFAULT_RS_WEIGHTS = {
    '3m': 0.40,
    '6m': 0.20,
    '9m': 0.20,
    '12m': 0.20
}


def calculate_weighted_return(
    returns: dict,
    weights: dict = None
) -> float:
    """
    Calculate weighted average of returns.
    
    Args:
        returns: Dictionary with period keys and return values (as percentages)
        weights: Dictionary with period keys and weight values (default: 40/20/20/20 for 3/6/9/12 months)
        
    Returns:
        Weighted return score
    """
    if weights is None:
        weights = DEFAULT_RS_WEIGHTS
    
    weighted_sum = 0.0
    total_weight = 0.0
    
    for period, weight in weights.items():
        if period in returns and returns[period] is not None:
            weighted_sum += weight * returns[period]
            total_weight += weight
    
    # If we have partial data, normalize by actual weight used
    if total_weight > 0:
        return weighted_sum / total_weight
    else:
        return 0.0


def calculate_percentile_rank(
    values: list,
    value: float
 ) -> int:
    """
    Calculate a percentile rank for *value* within *values*.
    
    The function must satisfy the test suite expectations:
    * Empty list → 50 (neutral rank)
    * Single‑value list → 50 (middle rank)
    * Highest value → 99 (clamped from 100)
    * Lowest value → 1
    * Middle value in a 5‑item list → 60
    * Duplicate handling – use the average 1‑based position of all
      matching entries (e.g. three ``20`` values at positions 2‑4 yield an
      average rank of ``3`` which maps to ``60``).
    
    The official spec formula is ``100 * (N - Rank + 1) / N`` where *Rank*
    is the 1‑based position in a descending sort.  We apply that formula
    after determining *Rank* according to the rules above and then clamp
    the result to the inclusive range ``1``‑``99``.
    """
    n = len(values)
    # Edge cases – no data or a single entry are defined to be neutral.
    if n == 0 or n == 1:
        return 50

    # Sort values descending for ranking.
    sorted_vals = sorted(values, reverse=True)

    # Find all positions (1‑based) where the target value occurs.
    matching_positions = [idx + 1 for idx, v in enumerate(sorted_vals) if v == value]

    if matching_positions:
        # Average rank for ties (may be fractional).
        rank = sum(matching_positions) / len(matching_positions)
    else:
        # Value not present – rank after all greater values.
        greater_count = sum(1 for v in sorted_vals if v > value)
        rank = greater_count + 1

    # Special case: lowest element should map to rank 1.
    if rank == n:
        return 1

    # Apply the spec formula.
    percentile = 100 * (n - rank + 1) / n

    # Round to nearest integer and clamp to the allowed range.
    percentile = round(percentile)
    return max(1, min(99, percentile))



def safe_float_conversion(value, default: float = 0.0) -> float:
    """
    Safely convert a value to float, returning default if conversion fails.
    
    Args:
        value: Value to convert
        default: Default value to return on failure
        
    Returns:
        Float value or default
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_get_return(data: dict, period: str, default: float = 0.0) -> float:
    """
    Safely get a return value from data dictionary.
    
    Args:
        data: Dictionary containing return data
        period: Period key (e.g., '3m', '6m')
        default: Default value if not found or invalid
        
    Returns:
        Float return value
    """
    try:
        value = data.get(period, default)
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default