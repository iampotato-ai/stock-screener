import pytest
import sqlite3
import sys
import os

# Ensure the root folder is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app, init_db, analyze_single_stock

db_file = None

@pytest.fixture(autouse=True)
def use_test_db(monkeypatch, tmp_path):
    global db_file
    db_file = str(tmp_path / "test_scan_history_vol.db")
    orig_connect = getattr(sqlite3, "__original_connect__", sqlite3.connect)
    
    def mock_connect(database, *args, **kwargs):
        if database and "scan_history.db" in database:
            return orig_connect(db_file, *args, **kwargs)
        return orig_connect(database, *args, **kwargs)
        
    monkeypatch.setattr("sqlite3.connect", mock_connect)
    
    # Run migrations and setup tables
    init_db()
    yield db_file

def test_volume_alert_calculations(monkeypatch):
    # Construct a historical list of 60 days
    # Let's make average volume around 100,000
    # Down-days will have volume 50,000 to 80,000
    # Last day (today) will be simulated in the endpoint, but let's test analyze_single_stock first
    history = []
    for i in range(60):
        # Even indices: up days; Odd indices: down days
        is_up = (i % 2 == 0)
        close_val = 100.0 + (i if is_up else -i * 0.5)
        history.append({
            "date": f"2026-01-{i+1:02d}",
            "open": 99.0 if is_up else 101.0,
            "high": 105.0,
            "low": 95.0,
            "close": close_val,
            "volume": 120000 if is_up else 80000
        })
    
    # Mock fetch_historical_prices
    def mock_fetch_historical_prices(ticker, range_str="6mo"):
        return history

    monkeypatch.setattr("app.fetch_historical_prices", mock_fetch_historical_prices)
    
    stock = {"clean_ticker": "MOCKVOL", "name": "Mock Vol Stock"}
    analyze_single_stock(stock)
    
    # Verify thresholds are calculated and assigned to stock
    assert "volume_sma_50" in stock
    assert "max_down_vol_10" in stock
    
    # SMA50 of volume: the last 50 days have volumes of alternating 120000 (up) and 80000 (down)
    # Average of last 50 alternating is exactly 100,000
    assert stock["volume_sma_50"] == pytest.approx(100000.0)
    
    # Last 10 down-days: all down-days have volume of 80000
    # Highest of last 10 down-day volumes must be 80000
    assert stock["max_down_vol_10"] == pytest.approx(80000.0)
    
    # Verify cached values match
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute("SELECT max_down_vol_10, volume_sma_50 FROM pattern_cache WHERE ticker = 'MOCKVOL'")
    row = c.fetchone()
    conn.close()
    
    assert row is not None
    assert row[0] == pytest.approx(80000.0)
    assert row[1] == pytest.approx(100000.0)
