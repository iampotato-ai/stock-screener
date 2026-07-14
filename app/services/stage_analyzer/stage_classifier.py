"""
Stage Analyzer – Classifier Module
Provides a thin wrapper that determines a qualitative “stage” label for a
stock based on its recent price history and then produces a
:class:`StageScore` using the generic :class:`StageAnalyzer`.
"""

from typing import Dict, List, Any

from .models import StageScore
from .scoring import StageAnalyzer


class StageClassifier:
    """
    Determines a stage label (e.g., ``early``, ``mid`` or ``late``) for a
    stock based on its recent price history and returns a populated
    :class:`StageScore`.
    """

    def __init__(self):
        self.analyzer = StageAnalyzer()

    @staticmethod
    def _extract_closes(history: List[Dict[str, Any]]) -> List[float]:
        """Return a list of closing prices from a history payload."""
        return [entry.get("close") for entry in history if isinstance(entry, dict) and entry.get("close") is not None]

    @staticmethod
    def _growth_rate(closes: List[float]) -> float:
        """Simple growth rate: (last - first) / first."""
        if not closes or closes[0] == 0:
            return 0.0
        return (closes[-1] - closes[0]) / closes[0]

    def determine_stage(self, stock_data: Dict[str, Any]) -> str:
        """
        Heuristic to map recent price movement to a stage label (Stan Weinstein 1-4).

        - **Stage 2** : strong upward momentum (> 10% growth over the period)
        - **Stage 4** : downward pressure (<= -5% growth)
        - **Stage 1** : consolidation (flat growth between -5% and 10% in lower range)
        - **Stage 3** : top/distribution (flat growth between -5% and 10% in upper range)

        Returns ``"Unknown"`` when insufficient data is present.
        """
        history = stock_data.get("history", [])
        if not isinstance(history, list) or len(history) < 5:
            return "Unknown"

        closes = self._extract_closes(history)
        if len(closes) < 2:
            return "Unknown"

        growth = self._growth_rate(closes)

        if growth > 0.10:
            return "Stage 2"
        if growth < -0.05:
            return "Stage 4"

        # Distinguish Stage 1 vs Stage 3 for consolidating flat growth
        max_close = max(closes)
        min_close = min(closes)
        current_close = closes[-1]

        if (max_close - min_close) > 0 and (current_close - min_close) / (max_close - min_close) > 0.6:
            return "Stage 3"
        return "Stage 1"

    def analyze(self, stock_data: Dict[str, Any]) -> StageScore:
        """
        Produce a :class:`StageScore` for the given ``stock_data``.

        The function first determines the stage label using
        :meth:`determine_stage` and then delegates scoring to the generic
        :class:`StageAnalyzer`. The returned ``StageScore`` includes the
        inferred stage as part of its payload.
        """
        stage = self.determine_stage(stock_data)
        return self.analyzer.analyze(stock_data, stage)


# Singleton for convenient import elsewhere
stage_classifier = StageClassifier()


def classify_stock(stock_data: Dict[str, Any]) -> StageScore:
    """
    Convenience function mirroring the pattern used in other services
    (e.g., ``nlp_service.process_announcement``). Returns a fully
    populated :class:`StageScore``.
    """
    return stage_classifier.analyze(stock_data)
