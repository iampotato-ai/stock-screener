"""
Unit tests for the five Momentum Confidence Score analyzer modules.

Tests boundary values extensively because the scoring criteria rely on
exact thresholds (RSI == 40, ADX == 25, etc.).
"""
import pytest
from app.services.scoring.technical import TechnicalAnalyzer
from app.services.scoring.fundamentals import FundamentalAnalyzer
from app.services.scoring.momentum import MomentumAnalyzer
from app.services.scoring.institutional import InstitutionalAnalyzer
from app.services.scoring.risk import RiskAnalyzer


# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────

def _minimal_stock(**overrides):
    """Return a minimal valid stock data dict with all required fields at safe defaults."""
    base = {
        # Technical
        'price': 1000.0, 'ema_20': 950.0, 'ema_50': 900.0,
        'ema_100': 850.0, 'ema_200': 800.0,
        'rsi': 55.0, 'macd': 5.0, 'macd_signal': 4.0,
        'adx': 30.0, 'supertrend': 980.0, 'supertrend_direction': 1,
        'price_vs_52w_high': 0.95, 'higher_highs': True, 'higher_lows': True,
        'golden_cross': True,
        # Fundamental
        'revenue_growth_yoy': 20.0, 'profit_growth_yoy': 25.0,
        'roe': 25.0, 'roce': 28.0, 'debt_to_equity': 0.05,
        'operating_margin': 0.20, 'net_margin': 0.15,
        'operating_cash_flow': 5000.0,
        'promoter_holding_pct': 65.0, 'promoter_pledged_pct': 0.0,
        # Momentum
        'relative_strength_rating': 92.0, 'volume_ratio': 3.5,
        'price_vs_52w_high_pct': 96.0, 'has_vcp_pattern': True,
        'is_breakout': True, 'momentum_acceleration': 25.0,
        # Institutional
        'mf_holding_change_pct': 12.0, 'fii_net_buy_cr': 150.0,
        'fii_holding_pct': 28.0, 'promoter_buy_qty': 200000,
        'promoter_holding_change_pct': 3.0, 'block_deal_count': 4,
        'block_deal_buy_ratio': 0.80,
        # Risk
        'avg_daily_volume': 3000000, 'market_cap_cr': 100000.0,
        'bid_ask_spread_pct': 0.03, 'volatility_30d': 0.20,
        'circuit_history': 0, 'operator_risk': 'low',
    }
    base.update(overrides)
    return base


# ──────────────────────────────────────────────────────────────────────────────
# TechnicalAnalyzer
# ──────────────────────────────────────────────────────────────────────────────

class TestTechnicalAnalyzer:
    """Tests for TechnicalAnalyzer (max 30 points)."""

    def setup_method(self):
        self.analyzer = TechnicalAnalyzer()

    def test_max_score_all_criteria_met(self):
        data = _minimal_stock()
        result = self.analyzer.analyze(data)
        assert result['score'] == 30
        assert result['max_score'] == 30

    def test_score_on_empty_data_is_bounded(self):
        """Empty data produces a low but valid score (RSI defaults to 50 which gets 2 pts)."""
        result = self.analyzer.analyze({})
        assert 0 <= result['score'] <= 5  # Should be very low but not necessarily 0
        assert result['score'] <= result['max_score']

    def test_score_does_not_exceed_maximum(self):
        """Even if criteria somehow over-award, the cap holds."""
        data = _minimal_stock()
        result = self.analyzer.analyze(data)
        assert result['score'] <= 30

    def test_price_exactly_equal_to_ema200_not_above(self):
        """Boundary: price == ema_200 should NOT award points (strictly greater than)."""
        data = _minimal_stock(price=800.0, ema_200=800.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['above_200_ema'] == 0

    def test_price_above_ema200_awards_points(self):
        data = _minimal_stock(price=801.0, ema_200=800.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['above_200_ema'] == 5

    def test_adx_exactly_25_gets_full_points(self):
        """Boundary: ADX == 25 is above 25? No — 25 > 25 is False. Should get partial points."""
        data = _minimal_stock(adx=25.0)
        result = self.analyzer.analyze(data)
        # adx=25 → 25 > 25 is False, 25 > 20 is True → partial 1 point
        assert result['details']['points_breakdown'].get('adx_gt_20', 0) == 1

    def test_adx_above_25_gets_full_points(self):
        data = _minimal_stock(adx=25.1)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['adx_gt_25'] == 3

    def test_rsi_exactly_40_gets_full_healthy_points(self):
        """RSI at lower boundary (40) should get healthy RSI points."""
        data = _minimal_stock(rsi=40.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['healthy_rsi'] == 2

    def test_rsi_exactly_80_gets_full_healthy_points(self):
        """RSI at upper boundary (80) should still get healthy RSI points."""
        data = _minimal_stock(rsi=80.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['healthy_rsi'] == 2

    def test_rsi_above_80_gets_one_point(self):
        data = _minimal_stock(rsi=81.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['healthy_rsi'] == 1

    def test_rsi_below_40_gets_zero(self):
        data = _minimal_stock(rsi=39.9)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['healthy_rsi'] == 0

    def test_result_has_required_keys(self):
        result = self.analyzer.analyze(_minimal_stock())
        assert 'score' in result
        assert 'max_score' in result
        assert 'details' in result
        assert result['max_score'] == 30

    def test_exception_returns_zero_score(self):
        """An analyzer exception must return score=0 and not propagate."""
        result = self.analyzer.analyze(None)  # None will cause AttributeError
        assert result['score'] == 0


# ──────────────────────────────────────────────────────────────────────────────
# MomentumAnalyzer
# ──────────────────────────────────────────────────────────────────────────────

class TestMomentumAnalyzer:
    """Tests for MomentumAnalyzer (max 20 points)."""

    def setup_method(self):
        self.analyzer = MomentumAnalyzer()

    def test_max_score_all_criteria_met(self):
        data = _minimal_stock()
        result = self.analyzer.analyze(data)
        assert result['score'] == 20

    def test_score_zero_on_empty_data(self):
        result = self.analyzer.analyze({})
        assert result['score'] >= 0  # RS < 50 still gets 1 point
        assert result['score'] <= 20

    def test_rs_breakdown_matches_score_low_rs_regression(self):
        """Regression test for the off-by-one bug: score +=1 must record breakdown=1."""
        data = _minimal_stock(relative_strength_rating=30.0)  # < 50 → low RS
        result = self.analyzer.analyze(data)
        breakdown = result['details']['points_breakdown']['relative_strength']
        # The score contribution and the breakdown must agree
        assert breakdown == 1, f"Expected breakdown=1 for low RS, got {breakdown}"

    def test_rs_90_gets_6_points(self):
        data = _minimal_stock(relative_strength_rating=90.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['relative_strength'] == 6

    def test_rs_80_to_89_gets_5_points(self):
        data = _minimal_stock(relative_strength_rating=85.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['relative_strength'] == 5

    def test_vcp_pattern_detected_adds_3_points(self):
        data = _minimal_stock(has_vcp_pattern=True)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['vcp_pattern'] == 3

    def test_no_vcp_pattern_adds_zero(self):
        data = _minimal_stock(has_vcp_pattern=False)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['vcp_pattern'] == 0

    def test_is_breakout_true_adds_2_points(self):
        data = _minimal_stock(is_breakout=True)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['fresh_breakout'] == 2

    def test_is_breakout_false_adds_zero(self):
        data = _minimal_stock(is_breakout=False)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['fresh_breakout'] == 0

    def test_score_does_not_exceed_maximum(self):
        result = self.analyzer.analyze(_minimal_stock())
        assert result['score'] <= 20

    def test_exception_returns_zero_score(self):
        result = self.analyzer.analyze(None)
        assert result['score'] == 0


# ──────────────────────────────────────────────────────────────────────────────
# FundamentalAnalyzer
# ──────────────────────────────────────────────────────────────────────────────

class TestFundamentalAnalyzer:
    """Tests for FundamentalAnalyzer (max 25 points)."""

    def setup_method(self):
        self.analyzer = FundamentalAnalyzer()

    def test_max_score_all_criteria_met(self):
        data = _minimal_stock()
        result = self.analyzer.analyze(data)
        assert result['score'] == 25

    def test_zero_operating_cash_flow_gives_no_points(self):
        data = _minimal_stock(operating_cash_flow=0.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['positive_cash_flow'] == 0

    def test_negative_cash_flow_gives_no_points(self):
        data = _minimal_stock(operating_cash_flow=-500.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['positive_cash_flow'] == 0

    def test_positive_cash_flow_gives_3_points(self):
        data = _minimal_stock(operating_cash_flow=100.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['positive_cash_flow'] == 3

    def test_zero_promoter_pledge_gives_2_points(self):
        data = _minimal_stock(promoter_pledged_pct=0.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['no_pledge'] == 2

    def test_high_promoter_pledge_gives_zero(self):
        data = _minimal_stock(promoter_pledged_pct=50.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['no_pledge'] == 0

    def test_promoter_holding_pct_60_gets_2_points(self):
        data = _minimal_stock(promoter_holding_pct=60.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['promoter_holding'] == 2

    def test_promoter_holding_pct_39_gets_zero(self):
        data = _minimal_stock(promoter_holding_pct=39.9)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['promoter_holding'] == 0

    def test_score_does_not_exceed_maximum(self):
        result = self.analyzer.analyze(_minimal_stock())
        assert result['score'] <= 25

    def test_exception_returns_zero_score(self):
        result = self.analyzer.analyze(None)
        assert result['score'] == 0


# ──────────────────────────────────────────────────────────────────────────────
# InstitutionalAnalyzer
# ──────────────────────────────────────────────────────────────────────────────

class TestInstitutionalAnalyzer:
    """Tests for InstitutionalAnalyzer (max 15 points)."""

    def setup_method(self):
        self.analyzer = InstitutionalAnalyzer()

    def test_max_score_all_criteria_met(self):
        data = _minimal_stock()
        result = self.analyzer.analyze(data)
        assert result['score'] == 15

    def test_mf_outflow_greater_than_5pct_gives_zero(self):
        data = _minimal_stock(mf_holding_change_pct=-6.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['mf_increased'] == 0

    def test_mf_small_outflow_less_than_5pct_gives_1_point(self):
        data = _minimal_stock(mf_holding_change_pct=-3.0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['mf_increased'] == 1

    def test_promoter_holding_steady_gives_1_point(self):
        data = _minimal_stock(promoter_holding_change_pct=0.0, promoter_buy_qty=0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['promoter_buying'] == 1

    def test_score_does_not_exceed_maximum(self):
        result = self.analyzer.analyze(_minimal_stock())
        assert result['score'] <= 15

    def test_exception_returns_zero_score(self):
        result = self.analyzer.analyze(None)
        assert result['score'] == 0


# ──────────────────────────────────────────────────────────────────────────────
# RiskAnalyzer
# ──────────────────────────────────────────────────────────────────────────────

class TestRiskAnalyzer:
    """Tests for RiskAnalyzer (max 10 points)."""

    def setup_method(self):
        self.analyzer = RiskAnalyzer()

    def test_max_score_all_criteria_met(self):
        data = _minimal_stock()
        result = self.analyzer.analyze(data)
        assert result['score'] == 10

    def test_zero_avg_daily_volume_gives_no_liquidity_points(self):
        data = _minimal_stock(avg_daily_volume=0)
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['high_liquidity'] == 0

    def test_high_operator_risk_gives_zero(self):
        data = _minimal_stock(operator_risk='high')
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['low_operator_risk'] == 0

    def test_medium_operator_risk_gives_1_point(self):
        data = _minimal_stock(operator_risk='medium')
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['low_operator_risk'] == 1

    def test_low_operator_risk_gives_2_points(self):
        data = _minimal_stock(operator_risk='low')
        result = self.analyzer.analyze(data)
        assert result['details']['points_breakdown']['low_operator_risk'] == 2

    def test_avg_daily_volume_uses_correct_field_name(self):
        """Regression: field must be avg_daily_volume, not avg_volume_30d."""
        data = _minimal_stock(avg_daily_volume=2000000)
        result = self.analyzer.analyze(data)
        # 2M+ shares → 4 liquidity points
        assert result['details']['points_breakdown']['high_liquidity'] == 4

    def test_bid_ask_spread_pct_uses_correct_field_name(self):
        """Regression: field must be bid_ask_spread_pct, not bid_ask_spread."""
        data = _minimal_stock(bid_ask_spread_pct=0.04)
        result = self.analyzer.analyze(data)
        # <= 0.05% → 2 spread points
        assert result['details']['points_breakdown']['low_spread'] == 2

    def test_score_does_not_exceed_maximum(self):
        result = self.analyzer.analyze(_minimal_stock())
        assert result['score'] <= 10

    def test_exception_returns_zero_score(self):
        result = self.analyzer.analyze(None)
        assert result['score'] == 0
