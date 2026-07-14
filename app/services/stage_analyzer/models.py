"""
Models for the stage analyzer service.

Provides typed data structures used by stage analysis components.
"""

from typing import TypedDict


class StageScore(TypedDict, total=False):
    """
    TypedDict representing the result of a stage analysis.

    Attributes
    ----------
    stage: str
        Name of the analysis stage (e.g., "early", "mid", "late", "unknown").
    score: int
        Points awarded for this stage.
    max_score: int
        Maximum possible points for the stage.
    details: dict
        Arbitrary nested dictionary containing breakdowns, diagnostics,
        or any additional information the analyzer wishes to expose.
    """
    stage: str
    score: int
    max_score: int
    details: dict