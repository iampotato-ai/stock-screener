"""
Integration tests for Fear & Greed API endpoints.
"""
from unittest.mock import patch


def test_get_fear_greed_index_api(flask_app):
    with flask_app.app_context():
        from app import db
        db.create_all()
    client = flask_app.test_client()
    with patch('app.services.fear_greed_service.fear_greed_service._fetch_vix_data', return_value=20.0):
        with patch('app.services.fear_greed_service.fear_greed_service._fetch_nifty_momentum', return_value=55.0):
            response = client.get('/api/v1/fear-greed-index')
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert "score" in data["data"]
            assert "label" in data["data"]


def test_refresh_fear_greed_index_api(flask_app):
    with flask_app.app_context():
        from app import db
        db.create_all()
    client = flask_app.test_client()
    with patch('app.services.fear_greed_service.fear_greed_service._fetch_vix_data', return_value=80.0):
        with patch('app.services.fear_greed_service.fear_greed_service._fetch_nifty_momentum', return_value=80.0):
            response = client.post('/api/v1/fear-greed-index/refresh')
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert "refreshed" in data["message"].lower()
            assert data["data"]["score"] > 50
