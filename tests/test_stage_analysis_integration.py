import pytest
from app import create_app
from app.services.stage_analyzer.scheduler import _run_stage_analysis_job

# Dummy data for fetch_historical_prices
DUMMY_HISTORY = [{"close": 100 + i} for i in range(60)]  # 60 days of closing prices


@pytest.fixture
def app(monkeypatch):
    # Override heavy dependencies on the target scheduler module
    monkeypatch.setattr("app.services.stage_analyzer.scheduler.get_nse_symbols", lambda: ["RELIANCE"])
    monkeypatch.setattr("app.services.stage_analyzer.scheduler.fetch_historical_prices", lambda symbol: DUMMY_HISTORY)
    # Mock the analysis engine to return a predictable payload
    monkeypatch.setattr("app.services.stage_analyzer.scheduler.analyze", lambda data: {"symbol": data["ticker"], "sma21": data["SMA21"], "sma50": data["SMA50"]})
    # Create Flask app with testing config disabled for background tasks
    cfg_overrides = {
        "TESTING": False,
        "ENABLE_BACKGROUND_TASKS": True,
        "STAGE_ANALYSIS_ENABLED": True,
        "STAGE_ANALYSIS_HOUR": 0,
        "STAGE_ANALYSIS_MINUTE": 0,
    }
    app = create_app(overrides=cfg_overrides)
    return app


def test_stage_analysis_job_populates_results(app):
    # Run the core job directly
    _run_stage_analysis_job(app)
    results = app.config.get("STAGE_ANALYSIS_RESULTS", {})
    assert "RELIANCE" in results, "Stage analysis results should contain the sample symbol"
    payload = results["RELIANCE"]
    # Verify payload contains expected keys from the mocked analyze function
    assert payload["symbol"] == "RELIANCE"
    assert isinstance(payload["sma21"], float) or isinstance(payload["sma21"], int)
    assert isinstance(payload["sma50"], float) or isinstance(payload["sma50"], int)


def test_stage_analysis_history_endpoint(app, monkeypatch):
    # Mock database results for 5 days of RELIANCE history
    mock_db_rows = [
        {"symbol": "RELIANCE", "trade_date": "2026-07-10", "close": 100.0},
        {"symbol": "RELIANCE", "trade_date": "2026-07-11", "close": 101.0},
        {"symbol": "RELIANCE", "trade_date": "2026-07-12", "close": 102.0},
        {"symbol": "RELIANCE", "trade_date": "2026-07-13", "close": 103.0},
        {"symbol": "RELIANCE", "trade_date": "2026-07-14", "close": 104.0},
    ]
    monkeypatch.setattr("app.database.fetch_all", lambda sql, params=(): mock_db_rows)
    
    # Request the stage analyzer history endpoint
    with app.test_client() as client:
        response = client.get("/api/v1/stage-analyzer/history")
        assert response.status_code == 200
        data = response.get_json()
        
        # Verify history is populated
        assert isinstance(data, dict)
        # Should have data for the dates
        assert "2026-07-14" in data
        assert "Stage 1" in data["2026-07-14"] or "Stage 2" in data["2026-07-14"] or "Stage 3" in data["2026-07-14"] or "Stage 4" in data["2026-07-14"]

