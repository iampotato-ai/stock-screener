"""
Unit tests for India-Specific Fear & Greed Service.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from app.services.fear_greed_service import fear_greed_service, FearGreedService
from app.models import FearGreedHistory


def test_get_rating_label():
    service = FearGreedService()
    assert service.get_rating_label(15) == "Extreme Fear"
    assert service.get_rating_label(24) == "Extreme Fear"
    assert service.get_rating_label(25) == "Fear"
    assert service.get_rating_label(44) == "Fear"
    assert service.get_rating_label(45) == "Neutral"
    assert service.get_rating_label(55) == "Neutral"
    assert service.get_rating_label(56) == "Greed"
    assert service.get_rating_label(75) == "Greed"
    assert service.get_rating_label(76) == "Extreme Greed"
    assert service.get_rating_label(100) == "Extreme Greed"


def test_compute_fear_greed_index_mocked(flask_app):
    with flask_app.app_context():
        with patch.object(fear_greed_service, '_fetch_vix_data', return_value=15.0):
            with patch.object(fear_greed_service, '_fetch_nifty_momentum', return_value=60.0):
                with patch.object(fear_greed_service, '_fetch_breadth_data', return_value={
                    'strength': 50.0,
                    'breadth': 55.0,
                    'ad_momentum': 52.0
                }):
                    result = fear_greed_service.compute_fear_greed_index()
                    assert "score" in result
                    assert "label" in result
                    assert "sub_indicators" in result
                    assert 0 <= result["score"] <= 100
                    assert result["label"] in ["Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"]


def test_save_and_get_latest_fear_greed(flask_app):
    with flask_app.app_context():
        from app import db
        db.create_all()
        snapshot = {
            "score": 68,
            "label": "Greed",
            "timestamp": datetime.utcnow().isoformat(),
            "sub_indicators": {
                "momentum": 70.0,
                "strength": 65.0,
                "breadth": 60.0,
                "volatility": 75.0,
                "ad_momentum": 70.0
            }
        }
        fear_greed_service.save_fear_greed_snapshot(snapshot)

        latest = fear_greed_service.get_latest_fear_greed()
        assert latest is not None
        assert latest["score"] == 68
        assert latest["label"] == "Greed"
        assert "subIndicators" in latest
