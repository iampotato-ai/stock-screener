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
