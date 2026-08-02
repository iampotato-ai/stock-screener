"""
Composite signal score aggregation and verdict mapping.

Weights all component scores into a 0–100 composite signal, then maps
to a human-readable verdict.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Component weights (must sum to 1.0)
_WEIGHTS = {
    "ma": 0.25,
    "macd": 0.15,
    "rsi": 0.15,
    "volume": 0.15,
    "trend": 0.20,
    "risk": 0.10,
}

# Verdict boundaries
_VERDICT_MAP = [
    (80, "Strong Buy"),
    (65, "Buy"),
    (45, "Hold"),
    (30, "Watch"),
    (15, "Sell"),
    (0, "Strong Sell"),
]


def compute_composite_signal(
    ma_score: float,
    macd_score: float,
    rsi_score: float,
    volume_score: float,
    trend_score: float,
    risk_score: float,
) -> Dict[str, Any]:
    """
    Aggregate component scores into a composite signal.

    Args:
        ma_score: MA alignment score in [-1.0, +1.0].
        macd_score: MACD cross score in [-1.0, +1.0].
        rsi_score: RSI composite score in [-1.0, +1.0].
        volume_score: Volume analysis score in [-1.0, +1.0].
        trend_score: Trend classifier score in [-1.0, +1.0].
        risk_score: Risk analytics score in [0.0, 1.0] (1.0 = low risk).

    Returns:
        Dict with:
            score: float (0–100)
            verdict: str
            breakdown: dict of per-component contributions
    """
    # Clamp inputs
    ma_score = _clamp(ma_score, -1.0, 1.0)
    macd_score = _clamp(macd_score, -1.0, 1.0)
    rsi_score = _clamp(rsi_score, -1.0, 1.0)
    volume_score = _clamp(volume_score, -1.0, 1.0)
    trend_score = _clamp(trend_score, -1.0, 1.0)
    risk_score = _clamp(risk_score, 0.0, 1.0)

    # Convert risk_score from [0,1] to [-1,+1] for consistent weighting
    # risk_score 1.0 (low risk) → +1.0, risk_score 0.0 (high risk) → -1.0
    risk_normalized = risk_score * 2.0 - 1.0

    # Compute weighted raw score
    raw = (
        ma_score * _WEIGHTS["ma"]
        + macd_score * _WEIGHTS["macd"]
        + rsi_score * _WEIGHTS["rsi"]
        + volume_score * _WEIGHTS["volume"]
        + trend_score * _WEIGHTS["trend"]
        + risk_normalized * _WEIGHTS["risk"]
    )

    # Normalize from [-1, +1] to [0, 100]
    normalized = (raw + 1.0) / 2.0 * 100.0
    final_score = _clamp(normalized, 0.0, 100.0)

    # Map to verdict
    verdict = _score_to_verdict(final_score)

    # Breakdown for transparency
    breakdown = {
        "ma_contribution": round(ma_score * _WEIGHTS["ma"], 4),
        "macd_contribution": round(macd_score * _WEIGHTS["macd"], 4),
        "rsi_contribution": round(rsi_score * _WEIGHTS["rsi"], 4),
        "volume_contribution": round(volume_score * _WEIGHTS["volume"], 4),
        "trend_contribution": round(trend_score * _WEIGHTS["trend"], 4),
        "risk_contribution": round(risk_normalized * _WEIGHTS["risk"], 4),
        "raw_score": round(raw, 4),
    }

    return {
        "score": round(final_score, 1),
        "verdict": verdict,
        "breakdown": breakdown,
    }


def _score_to_verdict(score: float) -> str:
    """Map composite score to a verdict string."""
    for threshold, label in _VERDICT_MAP:
        if score >= threshold:
            return label
    return "Strong Sell"


def _clamp(value: float, low: float, high: float) -> float:
    """Clamp value to [low, high] range."""
    return max(low, min(high, value))
