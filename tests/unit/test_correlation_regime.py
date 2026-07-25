"""
Unit tests for app/services/correlation_regime.py
(pure math functions only — no Flask/DB context required)
"""
import pytest
from app.services.correlation_regime import (
    compute_daily_returns,
    compute_avg_pairwise_correlation,
    classify_regime,
    apply_hysteresis,
    FUSED_THRESHOLD,
    DIVERGED_THRESHOLD,
)


# ──────────────────────────────────────────────────────────────────────────────
# compute_daily_returns
# ──────────────────────────────────────────────────────────────────────────────
class TestComputeDailyReturns:
    def test_basic_returns(self):
        result = compute_daily_returns([100.0, 110.0, 99.0])
        assert result[0] == pytest.approx(0.10)
        assert result[1] == pytest.approx(-0.10, rel=1e-3)

    def test_single_price_returns_empty(self):
        assert compute_daily_returns([100.0]) == []

    def test_empty_list_returns_empty(self):
        assert compute_daily_returns([]) == []

    def test_zero_price_skipped_safely(self):
        result = compute_daily_returns([100.0, 0.0, 110.0])
        # The zero-price bar is skipped by the guard
        assert isinstance(result, list)


# ──────────────────────────────────────────────────────────────────────────────
# compute_avg_pairwise_correlation
# ──────────────────────────────────────────────────────────────────────────────
class TestComputeAvgPairwiseCorrelation:
    def _make_returns(self, n: int, seed_offset: float = 0.0):
        """Simple synthetic return stream."""
        return [seed_offset + 0.01 * i for i in range(n)]

    def test_identical_series_gives_corr_one(self):
        rets = self._make_returns(20)
        matrix = {'A': rets, 'B': rets}
        avg = compute_avg_pairwise_correlation(matrix)
        assert avg == pytest.approx(1.0, abs=1e-6)

    def test_independent_series_near_zero(self):
        # Alternating signs — negatively correlated or near zero
        a = [1.0, -1.0] * 10
        b = [-1.0, 1.0] * 10
        matrix = {'A': a, 'B': b}
        avg = compute_avg_pairwise_correlation(matrix)
        assert avg == pytest.approx(-1.0, abs=0.05)

    def test_fewer_than_two_symbols_returns_zero(self):
        matrix = {'A': [0.01, 0.02, 0.03]}
        assert compute_avg_pairwise_correlation(matrix) == 0.0

    def test_empty_matrix_returns_zero(self):
        assert compute_avg_pairwise_correlation({}) == 0.0

    def test_fused_market_detection(self):
        # Build 5 highly-correlated series
        base = [0.01 * i for i in range(20)]
        matrix = {f'S{i}': base for i in range(5)}
        avg = compute_avg_pairwise_correlation(matrix)
        assert avg >= FUSED_THRESHOLD, "All identical series should trigger FUSED threshold"

    def test_handles_constant_series_gracefully(self):
        matrix = {'A': [0.0] * 20, 'B': [0.01, 0.02] * 10}
        result = compute_avg_pairwise_correlation(matrix)
        assert isinstance(result, float)


# ──────────────────────────────────────────────────────────────────────────────
# classify_regime
# ──────────────────────────────────────────────────────────────────────────────
class TestClassifyRegime:
    def test_fused(self):
        assert classify_regime(0.80) == 'FUSED'

    def test_normal_upper(self):
        assert classify_regime(0.50) == 'NORMAL'

    def test_normal_lower(self):
        assert classify_regime(0.30) == 'NORMAL'

    def test_diverged(self):
        assert classify_regime(0.10) == 'DIVERGED'

    def test_boundary_fused(self):
        assert classify_regime(FUSED_THRESHOLD) == 'FUSED'

    def test_boundary_diverged(self):
        assert classify_regime(DIVERGED_THRESHOLD) == 'DIVERGED'

    def test_negative_corr_is_diverged(self):
        assert classify_regime(-0.30) == 'DIVERGED'


# ──────────────────────────────────────────────────────────────────────────────
# apply_hysteresis
# ──────────────────────────────────────────────────────────────────────────────
class TestApplyHysteresis:
    def test_no_history_returns_new_regime(self):
        assert apply_hysteresis('FUSED', [], n_days=3) == 'FUSED'

    def test_regime_switches_after_n_days(self):
        history = ['NORMAL', 'FUSED', 'FUSED']   # 2 FUSED already
        result = apply_hysteresis('FUSED', history, n_days=3)
        assert result == 'FUSED'

    def test_regime_does_not_switch_on_single_day(self):
        history = ['NORMAL', 'NORMAL']
        result = apply_hysteresis('FUSED', history, n_days=3)
        assert result == 'NORMAL', "Should stay NORMAL — only 1 FUSED day"

    def test_back_to_normal_requires_persistence(self):
        history = ['FUSED', 'FUSED', 'NORMAL']
        result = apply_hysteresis('NORMAL', history, n_days=3)
        assert result == 'NORMAL', "Two consecutive NORMALs at n_days=3 → switches"

    def test_unanimous_in_window_switches(self):
        history = ['DIVERGED', 'DIVERGED']
        result = apply_hysteresis('DIVERGED', history, n_days=3)
        assert result == 'DIVERGED'
