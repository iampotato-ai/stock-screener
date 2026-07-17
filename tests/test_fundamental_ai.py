import pytest
from unittest.mock import patch
from app import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@patch("app.api.v1.ai_analysis.ai_service.analyze_fundamentals")
def test_analyze_fundamentals_endpoint_success(mock_analyze, client):
    # Set up mock response
    mock_analyze.return_value = {
        "verdict": "GARP",
        "score": 82,
        "summary": "Adani Green Energy's growth outweighs its valuation concerns."
    }

    payload = {
        "metrics": {
            "pe_ratio": 20.0,
            "roe": 15.0,
            "profit_growth": 25.0
        }
    }

    resp = client.post("/api/v1/analyze/fundamentals", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["verdict"] == "GARP"
    assert data["score"] == 82
    assert "valuation concerns" in data["summary"]
    mock_analyze.assert_called_once_with(payload["metrics"])

def test_analyze_fundamentals_endpoint_missing_metrics(client):
    resp = client.post("/api/v1/analyze/fundamentals", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
