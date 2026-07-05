"""
Unit tests for the score_calculator background job.

Tests the feature flag guard, batch processing, and summary logging.
"""
import pytest
import os
from unittest.mock import patch, MagicMock, call


class TestCalculateAllScores:
    """Tests for calculate_all_scores background job."""

    def _make_app_mock(self):
        """Create a minimal Flask app that supports context manager usage."""
        from flask import Flask
        app = Flask(__name__)
        app.config['TESTING'] = True
        return app

    def test_feature_flag_disabled_skips_job(self, monkeypatch):
        """When flag is False, the service must never be called."""
        monkeypatch.setenv('ENABLE_MOMENTUM_SCORE_CALCULATION', 'false')
        mock_app = self._make_app_mock()

        with patch('app.services.scoring_service.MomentumConfidenceScoreService') as MockService:
            from app.tasks.score_calculator import calculate_all_scores
            calculate_all_scores(mock_app)
            MockService.assert_not_called()

    def test_feature_flag_enabled_runs_job(self, monkeypatch):
        """When flag is True, the service must be instantiated and symbols iterated."""
        monkeypatch.setenv('ENABLE_MOMENTUM_SCORE_CALCULATION', 'true')
        monkeypatch.setenv('DAILY_SCORE_BATCH_SIZE', '500')

        mock_service = MagicMock()
        mock_service.calculate_score_for_stock.return_value = {'success': True}

        mock_app = self._make_app_mock()

        with patch('app.services.scoring_service.MomentumConfidenceScoreService', return_value=mock_service), \
             patch('app.database.get_nse_symbols', return_value=['RELIANCE', 'TCS']), \
             patch('app.services.screener_service.screener_service.get_scan_results', return_value=[{'ticker': 'RELIANCE'}, {'ticker': 'TCS'}]), \
             patch('time.sleep'):
            from app.tasks.score_calculator import calculate_all_scores
            calculate_all_scores(mock_app)

        assert mock_service.calculate_score_for_stock.call_count == 2

    def test_partial_failures_do_not_stop_run(self, monkeypatch):
        """A failure on one symbol must not abort the rest of the batch."""
        monkeypatch.setenv('ENABLE_MOMENTUM_SCORE_CALCULATION', 'true')
        monkeypatch.setenv('DAILY_SCORE_BATCH_SIZE', '500')

        mock_service = MagicMock()
        # First symbol raises, second succeeds
        mock_service.calculate_score_for_stock.side_effect = [
            Exception("Connection error"),
            {'success': True},
        ]

        mock_app = self._make_app_mock()

        with patch('app.services.scoring_service.MomentumConfidenceScoreService', return_value=mock_service), \
             patch('app.database.get_nse_symbols', return_value=[{'ticker': 'BADINPUT'}, {'ticker': 'TCS'}]), \
             patch('app.services.screener_service.screener_service.get_scan_results', return_value=[]), \
             patch('time.sleep'):
            from app.tasks.score_calculator import calculate_all_scores
            calculate_all_scores(mock_app)

        # Both symbols must have been attempted
        assert mock_service.calculate_score_for_stock.call_count == 2

    def test_feature_flag_case_insensitive(self, monkeypatch):
        """Flag check must accept 'True', 'TRUE', 'true'."""
        monkeypatch.setenv('ENABLE_MOMENTUM_SCORE_CALCULATION', 'TRUE')
        mock_service = MagicMock()
        mock_service.calculate_score_for_stock.return_value = {'success': True}

        mock_app = self._make_app_mock()

        with patch('app.services.scoring_service.MomentumConfidenceScoreService', return_value=mock_service), \
             patch('app.database.get_nse_symbols', return_value=[{'ticker': 'WIPRO'}]), \
             patch('app.services.screener_service.screener_service.get_scan_results', return_value=[]), \
             patch('time.sleep'):
            from app.tasks.score_calculator import calculate_all_scores
            calculate_all_scores(mock_app)

        assert mock_service.calculate_score_for_stock.call_count == 1
