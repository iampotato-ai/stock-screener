"""
Engine module for Stage Analyzer Service
Provides high‑level orchestration functions that combine classification,
scoring, explanation generation and rendering utilities.
"""

from __future__ import annotations

from typing import Dict, Any

# Local imports – these modules are part of the same package.
from .stage_classifier import classify_stock  # noqa: F401
from .explanations import generate_stage_explanation
from .trend_template import render_trend

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze(stock_data: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full stage‑analysis pipeline for a single stock.

    The pipeline consists of:
    1. Determining the stage label and scoring via ``classify_stock``.
    2. Generating a human‑readable explanation string.
    3. Rendering a formatted trend description (multi‑line by default).

    Args:
        stock_data: Raw stock information – must contain a ``history`` key that
            the classifier can interpret.

    Returns:
        A dictionary with the following keys:
        - ``score``: The ``StageScore`` TypedDict returned by the classifier.
        - ``explanation``: Plain‑text explanation.
        - ``trend``: Rendered trend string (multi‑line).
    """
    # 1. Classification & scoring
    score_data = classify_stock(stock_data)

    # 2. Explanation generation
    explanation = generate_stage_explanation(score_data)

    # 3. Trend rendering – keep multi‑line output for readability.
    trend = render_trend(score_data, multiline=True)

    return {
        "score": score_data,
        "explanation": explanation,
        "trend": trend,
    }

def get_score(stock_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience wrapper that returns only the raw ``StageScore``.

    This mirrors the pattern used by other services where a ``process``
    function returns a lightweight payload.
    """
    return classify_stock(stock_data)

def explain(score_data: Dict[str, Any]) -> str:
    """Generate an explanation for an already‑computed ``StageScore``.

    Args:
        score_data: ``StageScore`` TypedDict or a compatible mapping.
    """
    return generate_stage_explanation(score_data)

def render(score_data: Dict[str, Any], *, multiline: bool = True) -> str:
    """Render a human‑readable description from a ``StageScore``.

    Args:
        score_data: ``StageScore`` TypedDict or compatible mapping.
        multiline: Use the detailed template when ``True``; otherwise a
            compact one‑line summary.
    """
    return render_trend(score_data, multiline=multiline)

__all__ = [
    "analyze",
    "get_score",
    "explain",
    "render",
]
