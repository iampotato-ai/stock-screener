"""
Unit tests for BadgeAwarder.

Each badge's condition is tested at its exact boundary to confirm the
threshold logic works as intended.
"""
import pytest
from app.services.scoring.badges import BadgeAwarder


def _make_score_data(**overrides):
    """Return a minimal score data dict with all badge-related fields."""
    base = {
        'total_score': 70,
        'pillar_scores': {
            'technical': 20,
            'fundamental': 15,
            'momentum': 10,
            'institutional': 10,
            'risk_liquidity': 5,
        },
        'momentum_details': {
            'points_breakdown': {'fresh_breakout': 0, 'relative_strength': 0}
        },
        'institutional_details': {
            'points_breakdown': {'mf_increased': 0, 'fii_buying': 0}
        },
        'fundamental_details': {
            'points_breakdown': {'profit_growth': 0, 'debt_low': 0}
        },
    }
    base.update(overrides)
    return base


class TestBadgeAwarder:
    """Tests for each badge condition boundary."""

    def setup_method(self):
        self.awarder = BadgeAwarder()

    # --- elite_momentum ---

    def test_elite_momentum_awarded_at_95(self):
        data = _make_score_data(total_score=95)
        badges = self.awarder.award_badges(data)
        assert any('Elite Momentum' in b for b in badges)

    def test_elite_momentum_not_awarded_at_94(self):
        data = _make_score_data(total_score=94)
        badges = self.awarder.award_badges(data)
        assert not any('Elite Momentum' in b for b in badges)

    # --- fresh_breakout ---

    def test_fresh_breakout_badge_awarded_when_breakout_2_points(self):
        data = _make_score_data(momentum_details={'points_breakdown': {'fresh_breakout': 2}})
        badges = self.awarder.award_badges(data)
        assert any('Fresh Breakout' in b for b in badges)

    def test_fresh_breakout_badge_not_awarded_when_1_point(self):
        data = _make_score_data(momentum_details={'points_breakdown': {'fresh_breakout': 1}})
        badges = self.awarder.award_badges(data)
        assert not any('Fresh Breakout' in b for b in badges)

    # --- high_relative_strength ---

    def test_high_rs_badge_awarded_at_5_points(self):
        data = _make_score_data(
            momentum_details={'points_breakdown': {'relative_strength': 5}}
        )
        badges = self.awarder.award_badges(data)
        assert any('High Relative Strength' in b for b in badges)

    def test_high_rs_badge_not_awarded_at_4_points(self):
        data = _make_score_data(
            momentum_details={'points_breakdown': {'relative_strength': 4}}
        )
        badges = self.awarder.award_badges(data)
        assert not any('High Relative Strength' in b for b in badges)

    # --- high_quality ---

    def test_high_quality_badge_awarded_when_fundamental_20_and_risk_8(self):
        data = _make_score_data(pillar_scores={
            'fundamental': 20, 'risk_liquidity': 8,
            'technical': 0, 'momentum': 0, 'institutional': 0
        })
        badges = self.awarder.award_badges(data)
        assert any('High Quality' in b for b in badges)

    def test_high_quality_badge_not_awarded_when_fundamental_19(self):
        data = _make_score_data(pillar_scores={
            'fundamental': 19, 'risk_liquidity': 8,
            'technical': 0, 'momentum': 0, 'institutional': 0
        })
        badges = self.awarder.award_badges(data)
        assert not any('High Quality' in b for b in badges)

    # --- market_leader ---

    def test_market_leader_awarded_when_institutional_12_and_score_85(self):
        data = _make_score_data(
            total_score=85,
            pillar_scores={
                'institutional': 12, 'fundamental': 0, 'risk_liquidity': 0,
                'technical': 0, 'momentum': 0
            }
        )
        badges = self.awarder.award_badges(data)
        assert any('Market Leader' in b for b in badges)

    def test_market_leader_not_awarded_when_score_84(self):
        data = _make_score_data(
            total_score=84,
            pillar_scores={
                'institutional': 12, 'fundamental': 0, 'risk_liquidity': 0,
                'technical': 0, 'momentum': 0
            }
        )
        badges = self.awarder.award_badges(data)
        assert not any('Market Leader' in b for b in badges)

    # --- General ---

    def test_returns_empty_list_on_exception_in_condition(self):
        """A bad score_data object should not raise; it should return partial results."""
        # Passing None will cause KeyError in some conditions — these must be caught
        badges = self.awarder.award_badges(None)
        assert isinstance(badges, list)

    def test_no_badges_on_all_zero_scores(self):
        data = _make_score_data(
            total_score=0,
            pillar_scores={'fundamental': 0, 'risk_liquidity': 0, 'technical': 0,
                           'momentum': 0, 'institutional': 0},
            momentum_details={'points_breakdown': {'fresh_breakout': 0, 'relative_strength': 0}},
            institutional_details={'points_breakdown': {'mf_increased': 0, 'fii_buying': 0}},
            fundamental_details={'points_breakdown': {'profit_growth': 0, 'debt_low': 0}},
        )
        badges = self.awarder.award_badges(data)
        assert badges == []
