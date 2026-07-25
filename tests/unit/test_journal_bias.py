"""
Unit tests for app/services/journal_bias.py
(pure Python — no Flask/DB context required)
"""
import pytest
from app.services.journal_bias import (
    compute_disposition_effect,
    compute_overtrading_score,
    compute_momentum_chasing,
    compute_anchoring_bias,
    analyze_biases,
    MIN_TRADES_FOR_ANALYSIS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_trade(
    ticker='RELIANCE',
    entry=100.0,
    stop=95.0,
    pnl=None,
    status='closed',
    date='2024-01-15',
    exit_date='2024-01-25',
    r_achieved=None,
):
    return {
        'ticker': ticker,
        'entry': entry,
        'stop': stop,
        'pnl': pnl,
        'status': status,
        'date': date,
        'exitDate': exit_date,
        'rAchieved': r_achieved,
    }


# ──────────────────────────────────────────────────────────────────────────────
# compute_disposition_effect
# ──────────────────────────────────────────────────────────────────────────────
class TestDispositionEffect:
    def test_normal_ratio(self):
        # Winners held 10d, losers held 5d → ratio = 2.0 (healthy)
        trades = [
            _make_trade(pnl=500,  date='2024-01-01', exit_date='2024-01-11'),  # winner, 10d
            _make_trade(pnl=300,  date='2024-01-01', exit_date='2024-01-11'),  # winner, 10d
            _make_trade(pnl=-200, date='2024-01-01', exit_date='2024-01-06'),  # loser,  5d
            _make_trade(pnl=-100, date='2024-01-01', exit_date='2024-01-06'),  # loser,  5d
        ]
        result = compute_disposition_effect(trades)
        assert result == pytest.approx(2.0, rel=0.01)

    def test_disposition_bias_present(self):
        # Losers held longer than winners → ratio < 1.0
        trades = [
            _make_trade(pnl=200,  date='2024-01-01', exit_date='2024-01-03'),  # winner, 2d
            _make_trade(pnl=-150, date='2024-01-01', exit_date='2024-01-21'),  # loser, 20d
        ]
        result = compute_disposition_effect(trades)
        assert result is not None and result < 1.0

    def test_no_closed_trades_returns_none(self):
        trades = [_make_trade(pnl=None, status='open')]
        result = compute_disposition_effect(trades)
        assert result is None

    def test_only_winners_returns_none(self):
        trades = [
            _make_trade(pnl=100, date='2024-01-01', exit_date='2024-01-05'),
            _make_trade(pnl=200, date='2024-01-01', exit_date='2024-01-05'),
        ]
        result = compute_disposition_effect(trades)
        assert result is None

    def test_only_losers_returns_none(self):
        trades = [
            _make_trade(pnl=-100, date='2024-01-01', exit_date='2024-01-05'),
        ]
        result = compute_disposition_effect(trades)
        assert result is None

    def test_malformed_dates_handled_gracefully(self):
        trades = [
            {'pnl': 100, 'date': 'not-a-date', 'exitDate': 'also-bad', 'status': 'closed'},
            {'pnl': -50, 'date': 'bad',         'exitDate': 'bad',       'status': 'closed'},
        ]
        result = compute_disposition_effect(trades)
        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# compute_overtrading_score
# ──────────────────────────────────────────────────────────────────────────────
class TestOvertradingScore:
    def test_empty_returns_zero(self):
        assert compute_overtrading_score([]) == 0.0

    def test_single_trade_returns_zero(self):
        assert compute_overtrading_score([_make_trade()]) == 0.0

    def test_healthy_cadence(self):
        # 6 trades over ~24 days ≈ optimal cadence; use wider tolerance
        trades = [
            _make_trade(date=f'2024-01-{d:02d}') for d in [1, 5, 10, 15, 20, 25]
        ]
        score = compute_overtrading_score(trades)
        assert score == pytest.approx(1.0, abs=0.5)

    def test_overtrading_detected(self):
        # 20 trades in 1 month → clearly overtrading
        trades = [_make_trade(date=f'2024-01-{(i % 28) + 1:02d}') for i in range(20)]
        score = compute_overtrading_score(trades)
        assert score > 1.5

    def test_undertrading(self):
        # 1 trade per month for 6 months
        trades = [
            _make_trade(date=f'2024-0{m}-01') for m in range(1, 7)
        ]
        score = compute_overtrading_score(trades)
        assert score < 0.5


# ──────────────────────────────────────────────────────────────────────────────
# compute_momentum_chasing
# ──────────────────────────────────────────────────────────────────────────────
class TestMomentumChasing:
    def test_empty_returns_zero(self):
        assert compute_momentum_chasing([]) == 0.0

    def test_no_chasing(self):
        # entry-stop gap = 2% → below 3% threshold
        trades = [_make_trade(entry=100.0, stop=98.0)] * 5
        score = compute_momentum_chasing(trades)
        assert score == 0.0

    def test_all_chasing(self):
        # entry-stop gap = 10% → all above threshold
        trades = [_make_trade(entry=100.0, stop=90.0)] * 5
        score = compute_momentum_chasing(trades)
        assert score == pytest.approx(1.0)

    def test_partial_chasing(self):
        # 2 chasing out of 4 valid
        trades = [
            _make_trade(entry=100.0, stop=90.0),  # chasing (10%)
            _make_trade(entry=100.0, stop=90.0),  # chasing
            _make_trade(entry=100.0, stop=99.0),  # not chasing (1%)
            _make_trade(entry=100.0, stop=99.0),  # not chasing
        ]
        score = compute_momentum_chasing(trades)
        assert score == pytest.approx(0.5)

    def test_zero_entry_price_skipped_safely(self):
        trades = [_make_trade(entry=0.0, stop=0.0)]
        score = compute_momentum_chasing(trades)
        assert score == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# compute_anchoring_bias
# ──────────────────────────────────────────────────────────────────────────────
class TestAnchoringBias:
    def test_empty_returns_zero(self):
        assert compute_anchoring_bias([]) == 0.0

    def test_identical_stops_high_anchoring(self):
        # All trades with exactly 5% stop → CV = 0 (max anchoring)
        trades = [_make_trade(entry=100.0, stop=95.0)] * 10
        cv = compute_anchoring_bias(trades)
        assert cv == pytest.approx(0.0, abs=0.01)   # zero variance → anchored

    def test_varied_stops_low_anchoring(self):
        # Stops vary widely: 1%, 5%, 10%, 15%, 20%
        trades = [
            _make_trade(entry=100.0, stop=99.0),
            _make_trade(entry=100.0, stop=95.0),
            _make_trade(entry=100.0, stop=90.0),
            _make_trade(entry=100.0, stop=85.0),
            _make_trade(entry=100.0, stop=80.0),
        ]
        cv = compute_anchoring_bias(trades)
        assert cv > 0.3, "Wide stop variation should produce high CV"

    def test_single_trade_returns_zero(self):
        trades = [_make_trade(entry=100.0, stop=95.0)]
        assert compute_anchoring_bias(trades) == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# analyze_biases (composite)
# ──────────────────────────────────────────────────────────────────────────────
class TestAnalyzeBiases:
    def _make_journal(self, n: int, **kwargs):
        return [_make_trade(**kwargs) for _ in range(n)]

    def test_insufficient_trades_returns_message(self):
        result = analyze_biases(self._make_journal(MIN_TRADES_FOR_ANALYSIS - 1))
        assert 'message' in result
        assert result['total_trades_analyzed'] < MIN_TRADES_FOR_ANALYSIS

    def test_empty_journal_returns_message(self):
        result = analyze_biases([])
        assert 'message' in result

    def test_sufficient_trades_returns_all_keys(self):
        trades = self._make_journal(10, pnl=100, date='2024-01-01', exit_date='2024-01-10')
        result = analyze_biases(trades)
        assert 'bias_scores' in result
        assert 'recommendations' in result
        assert 'summary' in result
        assert 'total_trades_analyzed' in result

    def test_severity_labels_are_valid(self):
        trades = self._make_journal(10, pnl=100, date='2024-01-01', exit_date='2024-01-10')
        result = analyze_biases(trades)
        valid = {'HIGH', 'MODERATE', 'LOW'}
        for key in ['disposition_severity', 'overtrading_severity',
                    'momentum_chasing_severity', 'anchoring_severity']:
            assert result['bias_scores'][key] in valid

    def test_summary_is_non_empty_string(self):
        trades = self._make_journal(10, pnl=-200, date='2024-01-01', exit_date='2024-02-28')
        result = analyze_biases(trades)
        assert isinstance(result['summary'], str)
        assert len(result['summary']) > 0

    def test_result_is_serialisable(self):
        import json
        trades = self._make_journal(10, pnl=500, date='2024-03-01', exit_date='2024-03-05')
        result = analyze_biases(trades)
        # Should not raise
        json.dumps(result, default=str)
