"""
Integration tests for Insider Transactions API endpoints.
"""
import pytest
from unittest.mock import patch


@pytest.fixture
def client(flask_app):
    """Create a test client from the Flask app fixture."""
    return flask_app.test_client()


class TestInsiderAPI:

    @patch("app.services.insider_service.get_stock_insider_summary")
    def test_single_stock_insider_endpoint(self, mock_summary, client):
        """GET /api/v1/insider-transactions/RELIANCE → 200 with JSON."""
        mock_summary.return_value = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "insider_score": 75.0,
            "metrics": {
                "net_promoter_buy_30d": 14.5,
                "net_promoter_buy_90d": 32.1,
                "bulk_deal_count_30d": 2,
            },
            "badges": ["🔥 PROMOTER BUY"],
            "recent_transactions": [],
            "success": True,
        }
        res = client.get("/api/v1/insider-transactions/RELIANCE")
        assert res.status_code == 200
        data = res.get_json()
        assert data["symbol"] == "RELIANCE"
        assert data["insider_score"] == 75.0
        assert "🔥 PROMOTER BUY" in data["badges"]

    @patch("app.services.insider_service.get_batch_insider_summary")
    def test_batch_insider_summary_endpoint(self, mock_batch, client):
        """GET /api/v1/insider-transactions/summary?symbols=RELIANCE,INFY → 200."""
        mock_batch.return_value = {
            "RELIANCE": {"insider_score": 75.0, "badges": ["🔥 PROMOTER BUY"], "net_promoter_buy_30d": 14.5},
            "INFY": {"insider_score": 50.0, "badges": [], "net_promoter_buy_30d": 0.0},
        }
        res = client.get("/api/v1/insider-transactions/summary?symbols=RELIANCE,INFY")
        assert res.status_code == 200
        data = res.get_json()
        assert "RELIANCE" in data
        assert "INFY" in data

    def test_batch_missing_symbols_returns_400(self, client):
        """GET /api/v1/insider-transactions/summary without symbols → 400."""
        res = client.get("/api/v1/insider-transactions/summary")
        assert res.status_code == 400
