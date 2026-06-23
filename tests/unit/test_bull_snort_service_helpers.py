# tests/unit/test_bull_snort_service_helpers.py
"""Tests for internal helper functions of Bull Snort service.
These tests verify that the scoring and final scoring helpers behave as expected
with synthetic pandas Series inputs.
"""

import pandas as pd
import pytest

from app.services.bull_snort_service import _score_base_accumulation, _compute_final_score


def test_score_base_accumulation_basic():
    """Validate that base accumulation scoring returns a dict with expected keys and ranges."""
    # Synthetic data: 10 days of close, volume, and 200DMA values
    close = pd.Series([95, 96, 94, 97, 93, 92, 91, 90, 89, 88])
    volume = pd.Series([1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900])
    dma200 = pd.Series([100, 100, 100, 100, 100, 100, 100, 100, 100, 100])

    result = _score_base_accumulation(close, volume, dma200, lookback=10)
    # Expected keys
    assert set(result.keys()) == {"pivot_score", "surge_score", "accumulation_score", "n_pivots", "n_surges"}
    # Scores should be within 0..100 range
    for key, value in result.items():
        assert 0.0 <= value <= 100.0


def test_compute_final_score_weights():
    """Check final score calculation combines inputs according to weights and bounds.
    Using extreme values to ensure clipping works.
    """
    # Use vol_ratio far above min, pct_change high, close_position high, accumulation high,
    # and favorable gap values.
    score = _compute_final_score(
        vol_ratio=10.0,  # high ratio
        vol_surge_min=3.0,
        pct_change=20.0,  # above 5% cap
        close_position=0.9,
        accum_score=100.0,
        current_gap=0.0,  # best (gap 0)
        max_gap_6mo=15.0,  # above min_history 10
    )
    # Final score should be capped at 100
    assert 0.0 <= score <= 100.0
    # With maxed inputs, expect near-maximum score
    assert score > 80.0
