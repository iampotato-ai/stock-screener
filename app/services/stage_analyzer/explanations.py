"""
Explanations Module for Stage Analyzer Service
Generates human‑readable explanations for StageScore results.
"""

import logging
from .models import StageScore

logger = logging.getLogger(__name__)


def generate_stage_explanation(score_data: StageScore) -> str:
    """
    Generate an explanation string for a stage analysis.

    Args:
        score_data: TypedDict representing a stage analysis result.

    Returns:
        Formatted explanation string.
    """
    try:
        stage = score_data.get("stage", "UNKNOWN")
        score = score_data.get("score", 0)
        max_score = score_data.get("max_score", 0)
        details = score_data.get("details", {})

        # Header
        lines = [
            f"Stage: {stage}",
            f"Score: {score}/{max_score}",
            "",
        ]

        # Add details if present
        if isinstance(details, dict) and details:
            lines.append("Details:")
            for key, value in details.items():
                # Render simple values; for complex objects use repr
                val_str = (
                    value if isinstance(value, (str, int, float, bool)) else repr(value)
                )
                lines.append(f"- {key}: {val_str}")

        return "\n".join(lines)

    except Exception as e:
        logger.error("Error generating stage explanation: %s", e)
        stage_name = score_data.get('stage', 'ERROR') if isinstance(score_data, dict) else 'ERROR'
        return f"Stage: {stage_name}\nScore: Error\nDetails: Unable to generate explanation"


# Keep the class for backward compatibility, mapping to the function.
class StageExplanationGenerator:
    """
    Generates a concise, human‑readable explanation for a StageScore.
    Deprecation Warning: Use generate_stage_explanation function directly.
    """

    def generate_explanation(self, score_data: StageScore) -> str:
        return generate_stage_explanation(score_data)
