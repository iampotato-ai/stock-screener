"""
Trend status classifier.

Synthesizes MA alignment, MACD cross, and RSI composite into a discrete
trend label: Strong Bull / Bull / Neutral / Bear / Strong Bear.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def classify_trend(
    ma_score: float,
    macd_score: float,
    macd_cross: str,
    rsi_score: float,
) -> Dict[str, Any]:
    """
    Classify the overall trend from component scores.

    Args:
        ma_score: MA alignment score in [-1.0, +1.0].
        macd_score: MACD cross score in [-1.0, +1.0].
        macd_cross: MACD cross type string.
        rsi_score: RSI composite score in [-1.0, +1.0].

    Returns:
        Dict with:
            trend_label: "Strong Bull" | "Bull" | "Neutral" | "Bear" | "Strong Bear"
            trend_score: float in [-1.0, +1.0] (raw weighted average)
            components: dict of input scores for transparency
    """
    # Weighted synthesis: MA dominates, MACD confirms, RSI validates
    raw_score = (
        ma_score * 0.45 +
        macd_score * 0.30 +
        rsi_score * 0.25
    )

    # Apply cross-type overrides for strong signals
    if macd_cross in ("golden_cross",) and ma_score > 0.0:
        raw_score = min(1.0, raw_score + 0.15)
    elif macd_cross in ("death_cross",) and ma_score < 0.0:
        raw_score = max(-1.0, raw_score - 0.15)

    raw_score = max(-1.0, min(1.0, raw_score))
    trend_label = _score_to_label(raw_score, ma_score, macd_cross, rsi_score)

    return {
        "trend_label": trend_label,
        "trend_score": round(raw_score, 4),
        "components": {
            "ma_score": round(ma_score, 4),
            "macd_score": round(macd_score, 4),
            "macd_cross": macd_cross,
            "rsi_score": round(rsi_score, 4),
        },
    }


def _score_to_label(
    score: float,
    ma_score: float,
    macd_cross: str,
    rsi_score: float,
) -> str:
    """
    Map the synthesized score to a trend label.

    Strong Bull requires:
      - score >= 0.5 AND MA fully bullish (>= 0.5) AND RSI > 0.3
      - OR score >= 0.6 (strong enough on its own)

    Strong Bear is the mirror.
    """
    # Strong Bull
    if score >= 0.6:
        return "Strong Bull"
    if score >= 0.5 and ma_score >= 0.5 and rsi_score > 0.3:
        return "Strong Bull"

    # Bull
    if score >= 0.2:
        # Demote to Neutral if MACD just gave death cross
        if macd_cross == "death_cross":
            return "Neutral"
        return "Bull"

    # Neutral
    if score >= -0.2:
        return "Neutral"

    # Bear
    if score >= -0.5:
        # Promote to Neutral if MACD just gave golden cross
        if macd_cross == "golden_cross":
            return "Neutral"
        return "Bear"

    # Strong Bear
    if score <= -0.6:
        return "Strong Bear"
    if score <= -0.5 and ma_score <= -0.5 and rsi_score < -0.3:
        return "Strong Bear"

    return "Strong Bear"
