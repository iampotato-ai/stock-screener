"""
Auto-computed trade levels: stop-loss and take-profit.

Derives SL/TP from signal direction, nearest support/resistance levels,
and ATR for volatility-adjusted placement.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Constraints
_MAX_SL_PCT = 5.0       # Maximum SL distance from close (%)
_MIN_RR_RATIO = 1.5     # Minimum reward-to-risk ratio enforced


def compute_trade_levels(
    current_close: float,
    signal_verdict: str,
    nearest_support: float,
    nearest_resistance: float,
    atr: float,
) -> Dict[str, Any]:
    """
    Auto-generate stop-loss and take-profit levels.

    Args:
        current_close: Current closing price.
        signal_verdict: Signal verdict string (e.g. "Strong Buy", "Hold").
        nearest_support: Nearest support level below current price.
        nearest_resistance: Nearest resistance level above current price.
        atr: 14-period ATR value.

    Returns:
        Dict with:
            direction: "LONG" | "SHORT" | "NEUTRAL"
            stop_loss: float
            take_profit: float
            risk_reward_ratio: float
            risk_amount_pct: float (% distance from close to SL)
            reward_amount_pct: float (% distance from close to TP)
    """
    if current_close <= 0:
        return _default_result()

    direction = _verdict_to_direction(signal_verdict)

    if direction == "NEUTRAL":
        return {
            "direction": "NEUTRAL",
            "stop_loss": round(nearest_support, 2),
            "take_profit": round(nearest_resistance, 2),
            "risk_reward_ratio": 0.0,
            "risk_amount_pct": 0.0,
            "reward_amount_pct": 0.0,
        }

    # Ensure ATR is reasonable
    if atr <= 0:
        atr = current_close * 0.02  # 2% fallback

    if direction == "LONG":
        sl, tp = _compute_long_levels(current_close, nearest_support, nearest_resistance, atr)
    else:
        sl, tp = _compute_short_levels(current_close, nearest_support, nearest_resistance, atr)

    # Compute risk/reward metrics
    risk_amount = abs(current_close - sl)
    reward_amount = abs(tp - current_close)

    risk_pct = (risk_amount / current_close * 100) if current_close > 0 else 0.0
    reward_pct = (reward_amount / current_close * 100) if current_close > 0 else 0.0
    rr_ratio = (reward_amount / risk_amount) if risk_amount > 0 else 0.0

    return {
        "direction": direction,
        "stop_loss": round(sl, 2),
        "take_profit": round(tp, 2),
        "risk_reward_ratio": round(rr_ratio, 2),
        "risk_amount_pct": round(risk_pct, 2),
        "reward_amount_pct": round(reward_pct, 2),
    }


def _compute_long_levels(
    close: float,
    support: float,
    resistance: float,
    atr: float,
) -> tuple:
    """Compute SL and TP for a LONG (buy) signal."""
    # Stop-loss: below nearest support, but capped at 5% from close
    sl_candidate = max(support - 0.5 * atr, close - 2.0 * atr)
    max_sl_distance = close * (_MAX_SL_PCT / 100.0)
    sl = max(sl_candidate, close - max_sl_distance)

    # Take-profit: above nearest resistance
    tp_candidate = min(resistance + 0.3 * atr, close + 3.0 * atr)

    # Enforce minimum R:R ratio
    risk = close - sl
    if risk > 0:
        min_reward = risk * _MIN_RR_RATIO
        tp = max(tp_candidate, close + min_reward)
    else:
        tp = tp_candidate

    return sl, tp


def _compute_short_levels(
    close: float,
    support: float,
    resistance: float,
    atr: float,
) -> tuple:
    """Compute SL and TP for a SHORT (sell) signal."""
    # Stop-loss: above nearest resistance, capped at 5% from close
    sl_candidate = min(resistance + 0.5 * atr, close + 2.0 * atr)
    max_sl_distance = close * (_MAX_SL_PCT / 100.0)
    sl = min(sl_candidate, close + max_sl_distance)

    # Take-profit: below nearest support
    tp_candidate = max(support - 0.3 * atr, close - 3.0 * atr)

    # Enforce minimum R:R ratio
    risk = sl - close
    if risk > 0:
        min_reward = risk * _MIN_RR_RATIO
        tp = min(tp_candidate, close - min_reward)
    else:
        tp = tp_candidate

    return sl, tp


def _verdict_to_direction(verdict: str) -> str:
    """Map signal verdict to trade direction."""
    buy_verdicts = {"Strong Buy", "Buy"}
    sell_verdicts = {"Sell", "Strong Sell"}

    if verdict in buy_verdicts:
        return "LONG"
    elif verdict in sell_verdicts:
        return "SHORT"
    else:
        return "NEUTRAL"


def _default_result() -> Dict[str, Any]:
    """Return neutral defaults when computation fails."""
    return {
        "direction": "NEUTRAL",
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "risk_reward_ratio": 0.0,
        "risk_amount_pct": 0.0,
        "reward_amount_pct": 0.0,
    }
