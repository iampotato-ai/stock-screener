"""Trend Template module for Stage Analyzer.
Provides reusable string templates and rendering helpers for StageScore
objects. The templates are simple f‑string style placeholders that can be
used by the explanation generator or any UI component displaying stage
analysis results.
"""

from __future__ import annotations

from typing import Dict, Any

# ---------------------------------------------------------------------------
# Templates – simple multi‑line strings with `{placeholder}` syntax.
# ---------------------------------------------------------------------------

# Basic one‑line summary of a stage score.
BASIC_SUMMARY = "{stage} stage – {score}/{max_score}"

# Detailed multi‑line template. `{details}` will be replaced with a
# formatted list of `key: value` pairs (one per line) if `details` is a
# mapping, otherwise an empty string.
DETAILED_TEMPLATE = """Stage: {stage}
Score: {score}/{max_score}
{details}"""

# Helper to render the ``details`` mapping into a bullet list.  This is
# deliberately tiny – the heavy‑lifting rendering is performed by the
# ``render_trend`` function below.
def _format_details(details: Dict[str, Any] | None) -> str:
    if not details:
        return ""
    lines = ["Details:"]
    for key, value in details.items():
        # Simple representation – for complex objects fall back to ``repr``.
        if isinstance(value, (str, int, float, bool)):
            val_str = str(value)
        else:
            val_str = repr(value)
        lines.append(f"- {key}: {val_str}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Public rendering function
# ---------------------------------------------------------------------------

def render_trend(score_data: Dict[str, Any], *, multiline: bool = True) -> str:
    """Render a human‑readable description for a ``StageScore``.

    Args:
        score_data: Mapping that contains at least ``stage``, ``score`` and
            ``max_score`` keys. A ``details`` key may contain an additional
            mapping of diagnostic information.
        multiline: If ``True`` (default) use the multi‑line template;
            otherwise return the compact ``BASIC_SUMMARY``.

    Returns:
        A formatted string ready for display or logging.
    """
    stage = score_data.get("stage", "unknown")
    score = score_data.get("score", 0)
    max_score = score_data.get("max_score", 0)
    details = score_data.get("details") if isinstance(score_data.get("details"), dict) else None

    if multiline:
        details_str = _format_details(details)
        # Ensure there is a trailing newline only when details are present.
        if details_str:
            return DETAILED_TEMPLATE.format(stage=stage, score=score, max_score=max_score, details=details_str)
        else:
            # Omit the empty ``details`` line for cleaner output.
            return f"Stage: {stage}\nScore: {score}/{max_score}"
    else:
        return BASIC_SUMMARY.format(stage=stage, score=score, max_score=max_score)

__all__ = ["render_trend", "BASIC_SUMMARY", "DETAILED_TEMPLATE"]