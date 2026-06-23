# tests/unit/test_bull_snort_api.py
"""API tests for Bull Snort endpoints.
These tests verify the Flask routes, feature flag gating, and error handling.
"""

import pytest
from unittest.mock import patch


@pytest.fixture
def client(flask_app):
    """Flask test client fixture."""
    with flask_app.test_client() as client:
        yield client


def test_single_success(client, monkeypatch):
    # Enable feature flag
    client.application.config['ENABLE_BULL_SNORT'] = True
    dummy_result = {"symbol": "TEST", "final_score": 85}
    with patch("app.services.bull_snort_service.compute_bull_snort", return_value=dummy_result):
        resp = client.get("/api/bull_snort/single?symbol=TEST")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"] == dummy_result


def test_single_missing_symbol(client):
    client.application.config['ENABLE_BULL_SNORT'] = True
    resp = client.get("/api/bull_snort/single")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert "Missing 'symbol'" in data["error"]


def test_single_feature_disabled(client):
    client.application.config['ENABLE_BULL_SNORT'] = False
    resp = client.get("/api/bull_snort/single?symbol=ANY")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["error"] == "Bull Snort feature disabled"


def test_screen_success(client, monkeypatch):
    client.application.config['ENABLE_BULL_SNORT'] = True
    dummy_results = [{"symbol": "A", "final_score": 70}, {"symbol": "B", "final_score": 85}]
    with patch("app.services.bull_snort_service.screen_bull_snort", return_value=dummy_results):
        resp = client.post("/api/bull_snort/screen", json={"symbols": ["A", "B"]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"] == dummy_results

def test_screen_invalid_payload(client):
    client.application.config['ENABLE_BULL_SNORT'] = True
    # Not JSON
    resp = client.post("/api/bull_snort/screen", data="notjson")
    assert resp.status_code == 400
    # Missing symbols list
    resp = client.post("/api/bull_snort/screen", json={"foo": "bar"})
    assert resp.status_code == 400
    # Symbols not list
    resp = client.post("/api/bull_snort/screen", json={"symbols": "notalist"})
    assert resp.status_code == 400

def test_screen_feature_disabled(client):
    client.application.config['ENABLE_BULL_SNORT'] = False
    resp = client.post("/api/bull_snort/screen", json={"symbols": []})
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["error"] == "Bull Snort feature disabled"


def test_screen_get_success(client):
    client.application.config['ENABLE_BULL_SNORT'] = True
    # Clear cache to force a fresh run
    client.application.config['BULL_SNORT_CACHE'] = None
    dummy_results = [{"symbol": "C", "final_score": 77}]
    
    with patch("app.database.get_nse_symbols", return_value=["C"]):
        with patch("app.services.bull_snort_service.screen_bull_snort", return_value=dummy_results) as mock_screen:
            resp = client.get("/api/bull_snort/screen?vol_avg_period=20&vol_surge_min=3.0")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["data"] == dummy_results
            mock_screen.assert_called_once_with(
                symbols=["C"],
                vol_avg_period=20,
                vol_surge_min=3.0,
                close_position_min=0.65,
                min_gap_history=10.0,
                max_current_gap=5.0
            )


def test_screen_get_cached(client):
    client.application.config['ENABLE_BULL_SNORT'] = True
    cached_data = [{"symbol": "CACHED", "final_score": 90}]
    client.application.config['BULL_SNORT_CACHE'] = {
        'data': cached_data,
        'count': 1,
        'refreshed': '2026-06-23T12:00:00'
    }
    
    # Under default parameters, it should return the cache directly without calling the service
    with patch("app.services.bull_snort_service.screen_bull_snort") as mock_screen:
        resp = client.get("/api/bull_snort/screen")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"] == cached_data
        mock_screen.assert_not_called()


def test_screen_post_body_parameters(client):
    client.application.config['ENABLE_BULL_SNORT'] = True
    dummy_results = [{"symbol": "D", "final_score": 88}]
    
    with patch("app.services.bull_snort_service.screen_bull_snort", return_value=dummy_results) as mock_screen:
        # Pass parameters inside the JSON body rather than query parameters
        resp = client.post(
            "/api/bull_snort/screen",
            json={
                "symbols": ["D"],
                "vol_avg_period": 50,
                "vol_surge_min": 4.5,
                "close_position_min": 0.8
            }
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"] == dummy_results
        mock_screen.assert_called_once_with(
            symbols=["D"],
            vol_avg_period=50,
            vol_surge_min=4.5,
            close_position_min=0.8,
            min_gap_history=10.0,
            max_current_gap=5.0
        )


def test_screen_invalid_parameter_types(client):
    client.application.config['ENABLE_BULL_SNORT'] = True
    resp = client.get("/api/bull_snort/screen?vol_avg_period=invalid")
    assert resp.status_code == 400
    assert "error" in resp.get_json()

