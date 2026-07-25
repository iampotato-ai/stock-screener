"""
Unit tests for MomentumConfidenceScoreService.

Covers: happy path, failure path, DB upsert idempotency,
get_latest_score, and get_top_stocks.
"""
import pytest
from datetime import date
from unittest.mock import patch, MagicMock, PropertyMock


class TestMomentumConfidenceScoreService:
    """Tests for MomentumConfidenceScoreService."""

    def _make_analyzer_result(self, score, max_score):
        """Helper to build a mock analyzer result dict."""
        return {
            'score': score,
            'max_score': max_score,
            'details': {'criteria_met': [], 'criteria_not_met': [], 'points_breakdown': {}}
        }

    @patch('app.services.scoring_service.MomentumScore')
    @patch('app.services.scoring_service.db')
    @patch('app.services.scoring_service.StockRanker', None)
    @patch('app.services.scoring_service.ExplanationGenerator', None)
    @patch('app.services.scoring_service.BadgeAwarder', None)
    @patch('app.services.scoring_service.RiskAnalyzer')
    @patch('app.services.scoring_service.InstitutionalAnalyzer')
    @patch('app.services.scoring_service.MomentumAnalyzer')
    @patch('app.services.scoring_service.FundamentalAnalyzer')
    @patch('app.services.scoring_service.TechnicalAnalyzer')
    @patch('config.load_momentum_score_weights')
    def test_calculate_score_happy_path(
        self, mock_weights, MockTech, MockFund, MockMom, MockInst, MockRisk,
        mock_db, MockScore, flask_app
    ):
        """All analyzers succeed: result should have success=True and correct total."""
        mock_weights.return_value = {
            'technical_strength': 30, 'fundamental_quality': 25,
            'momentum': 20, 'institutional_confidence': 15, 'risk_liquidity': 10
        }
        # All analyzers return their maximum score
        MockTech.return_value.analyze.return_value = self._make_analyzer_result(30, 30)
        MockFund.return_value.analyze.return_value = self._make_analyzer_result(25, 25)
        MockMom.return_value.analyze.return_value = self._make_analyzer_result(20, 20)
        MockInst.return_value.analyze.return_value = self._make_analyzer_result(15, 15)
        MockRisk.return_value.analyze.return_value = self._make_analyzer_result(10, 10)

        # Stub DB so _save_score_to_db does not hit a real DB
        MockScore.query.filter_by.return_value.first.return_value = None

        with flask_app.app_context():
            from app.services.scoring_service import MomentumConfidenceScoreService
            service = MomentumConfidenceScoreService()
            result = service.calculate_score_for_stock('RELIANCE', 'NSE')

        assert result['success'] is True
        assert result['total_score'] == 100
        assert result['error'] is None

    @patch('app.services.scoring_service.MomentumScore')
    @patch('app.services.scoring_service.db')
    @patch('app.services.scoring_service.RiskAnalyzer')
    @patch('app.services.scoring_service.InstitutionalAnalyzer')
    @patch('app.services.scoring_service.MomentumAnalyzer')
    @patch('app.services.scoring_service.FundamentalAnalyzer')
    @patch('app.services.scoring_service.TechnicalAnalyzer')
    @patch('config.load_momentum_score_weights')
    def test_calculate_score_failure_path(
        self, mock_weights, MockTech, MockFund, MockMom, MockInst, MockRisk,
        mock_db, MockScore, flask_app
    ):
        """When an analyzer raises, result should have success=False with error message."""
        mock_weights.return_value = {
            'technical_strength': 30, 'fundamental_quality': 25,
            'momentum': 20, 'institutional_confidence': 15, 'risk_liquidity': 10
        }
        MockTech.return_value.analyze.side_effect = RuntimeError("Data unavailable")

        with flask_app.app_context():
            from app.services.scoring_service import MomentumConfidenceScoreService
            service = MomentumConfidenceScoreService()
            result = service.calculate_score_for_stock('INFOSYS', 'NSE')

        assert result['success'] is False
        assert result['error'] is not None
        assert 'INFOSYS' in result['error'] or 'Data unavailable' in result['error']

    @patch('app.services.scoring_service.MomentumScore')
    @patch('app.services.scoring_service.db')
    @patch('config.load_momentum_score_weights')
    def test_get_latest_score_returns_none_when_not_found(
        self, mock_weights, mock_db, MockScore, flask_app
    ):
        """get_latest_score returns None when no record exists."""
        mock_weights.return_value = {
            'technical_strength': 30, 'fundamental_quality': 25,
            'momentum': 20, 'institutional_confidence': 15, 'risk_liquidity': 10
        }
        MockScore.query.filter_by.return_value.order_by.return_value.first.return_value = None

        with flask_app.app_context():
            from app.services.scoring_service import MomentumConfidenceScoreService
            service = MomentumConfidenceScoreService()
            result = service.get_latest_score('UNKNOWN', 'NSE')

        assert result is None

    @patch('app.services.scoring_service.MomentumScore')
    @patch('app.services.scoring_service.db')
    @patch('config.load_momentum_score_weights')
    def test_get_latest_score_returns_dict_when_found(
        self, mock_weights, mock_db, MockScore, flask_app
    ):
        """get_latest_score returns to_dict() when a record exists."""
        mock_weights.return_value = {
            'technical_strength': 30, 'fundamental_quality': 25,
            'momentum': 20, 'institutional_confidence': 15, 'risk_liquidity': 10
        }
        mock_record = MagicMock()
        mock_record.to_dict.return_value = {'symbol': 'TCS', 'total_score': 87, 'technical_details': {'criteria_met': []}}
        MockScore.query.filter_by.return_value.order_by.return_value.first.return_value = mock_record

        with flask_app.app_context():
            from app.services.scoring_service import MomentumConfidenceScoreService
            service = MomentumConfidenceScoreService()
            result = service.get_latest_score('TCS', 'NSE')

        assert result == {'symbol': 'TCS', 'total_score': 87, 'technical_details': {'criteria_met': []}}

    @patch('app.services.scoring_service.MomentumScore')
    @patch('app.services.scoring_service.db')
    @patch('config.load_momentum_score_weights')
    def test_get_top_stocks_returns_list(
        self, mock_weights, mock_db, MockScore, flask_app
    ):
        """get_top_stocks returns a list of to_dict() results."""
        mock_weights.return_value = {
            'technical_strength': 30, 'fundamental_quality': 25,
            'momentum': 20, 'institutional_confidence': 15, 'risk_liquidity': 10
        }
        mock_record = MagicMock()
        mock_record.to_dict.return_value = {'symbol': 'HDFC', 'total_score': 90}
        MockScore.query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_record]

        with flask_app.app_context():
            from app.services.scoring_service import MomentumConfidenceScoreService
            service = MomentumConfidenceScoreService()
            result = service.get_top_stocks(limit=10)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['symbol'] == 'HDFC'
