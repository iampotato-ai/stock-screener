"""
Unit tests for Market Brief Service & REST API Endpoints.
"""
import pytest
from datetime import date
from app.extensions import db


@pytest.fixture(autouse=True)
def setup_db(flask_app):
    """Ensure database tables exist before each test."""
    with flask_app.app_context():
        db.create_all()
        yield


def test_market_brief_service_fallback(flask_app):
    """Test MarketBriefService quantitative fallback when AI returns None."""
    with flask_app.app_context():
        from app.services.market_brief_service import market_brief_service
        brief = market_brief_service.get_or_create_daily_brief(force_refresh=True)
        assert brief is not None
        assert "headline" in brief
        assert "macro_summary" in brief
        assert "sector_catalysts" in brief
        assert "top_actionable_stocks" in brief
        assert "brief_date" in brief
        assert brief["brief_date"] == date.today().strftime('%Y-%m-%d')


def test_market_brief_api_get(flask_app):
    """Test GET /api/v1/market-brief endpoint."""
    client = flask_app.test_client()
    response = client.get('/api/v1/market-brief')
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    assert "data" in json_data
    assert "headline" in json_data["data"]


def test_market_brief_api_post_refresh(flask_app):
    """Test POST /api/v1/market-brief/refresh endpoint."""
    client = flask_app.test_client()
    response = client.post('/api/v1/market-brief/refresh')
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "success"
    assert "data" in json_data
