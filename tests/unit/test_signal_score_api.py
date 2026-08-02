"""
Integration tests for the Signal Score API endpoint.
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client(flask_app):
    """Create a test client from the Flask app fixture."""
    return flask_app.test_client()


class TestSignalScoreAPI:

    @patch("app.services.signal_score.analyze_stock")
    def test_valid_symbol_returns_200(self, mock_analyze, client):
        """GET /api/v1/signal-score/RELIANCE → 200 with snapshot."""
        mock_analyze.return_value = {
            "success": True,
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "signal_score": 72.5,
            "signal_verdict": "Buy",
            "ai_summary": "Test",
            "ai_bull_factors": [],
            "ai_risk_factors": [],
            "news_sentiment": "sent-neutral",
        }
        response = client.get("/api/v1/signal-score/RELIANCE")
        assert response.status_code == 200
        data = response.get_json()
        assert data["symbol"] == "RELIANCE"
        assert data["signal_score"] == 72.5

    @patch("app.services.signal_score.analyze_stock")
    def test_unknown_symbol_returns_404(self, mock_analyze, client):
        """GET /api/v1/signal-score/FAKESYMBOL → 404."""
        mock_analyze.return_value = {
            "success": False,
            "error": "Insufficient price history for FAKESYMBOL (0 bars)",
        }
        response = client.get("/api/v1/signal-score/FAKESYMBOL")
        assert response.status_code == 404

    @patch("app.services.signal_score.analyze_stock")
    def test_service_error_returns_503(self, mock_analyze, client):
        """GET /api/v1/signal-score/X when service fails → 503."""
        mock_analyze.return_value = {
            "success": False,
            "error": "Yahoo Finance unavailable",
        }
        response = client.get("/api/v1/signal-score/X")
        assert response.status_code == 503

    @patch("app.services.signal_score.analyze_stock")
    def test_include_ai_false(self, mock_analyze, client):
        """?include_ai=false should pass include_ai=False to service."""
        mock_analyze.return_value = {"success": True, "symbol": "INFY"}
        client.get("/api/v1/signal-score/INFY?include_ai=false")
        mock_analyze.assert_called_once()
        _, kwargs = mock_analyze.call_args
        assert kwargs.get("include_ai") is False or (
            mock_analyze.call_args[1].get("include_ai") is False
        )

    @patch("app.services.signal_score.analyze_stock")
    def test_exchange_param(self, mock_analyze, client):
        """?exchange=BSE should be passed to service."""
        mock_analyze.return_value = {"success": True, "symbol": "INFY"}
        client.get("/api/v1/signal-score/INFY?exchange=BSE")
        mock_analyze.assert_called_once()
        call_kwargs = mock_analyze.call_args
        assert call_kwargs[1].get("exchange") == "BSE" or call_kwargs.kwargs.get("exchange") == "BSE"

    @patch("app.services.signal_score.analyze_stock")
    def test_nse_prefix_stripped(self, mock_analyze, client):
        """NSE: prefix in symbol should be stripped."""
        mock_analyze.return_value = {"success": True, "symbol": "RELIANCE"}
        client.get("/api/v1/signal-score/NSE:RELIANCE")
        call_args = mock_analyze.call_args
        assert call_args[1].get("symbol") == "RELIANCE" or call_args.kwargs.get("symbol") == "RELIANCE"
