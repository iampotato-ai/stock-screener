import pytest
import sqlite3
import json
import os
import tempfile
import sys
import time
from unittest.mock import patch, MagicMock

# Setup the test DB mock first
db_fd, db_path = tempfile.mkstemp()
orig_connect = sqlite3.connect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app
from app import app as flask_app

@pytest.fixture(autouse=True)
def patch_sqlite(monkeypatch):
    def mock_connect(database, *args, **kwargs):
        if database == "scan_history.db":
            return orig_connect(db_path, *args, **kwargs)
        return orig_connect(database, *args, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", mock_connect)
    app.init_db()

@pytest.fixture(scope="module", autouse=True)
def cleanup_temp_db():
    yield
    try:
        os.close(db_fd)
        os.unlink(db_path)
    except OSError:
        pass

@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def clean_db(patch_sqlite):
    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("DELETE FROM ep_features")
    c.execute("DELETE FROM daily_bars")
    c.execute("DELETE FROM fundamentals")
    c.execute("DELETE FROM ep_watchlist")
    c.execute("DELETE FROM rrg_history")
    c.execute("DELETE FROM ipo_listings")
    conn.commit()
    conn.close()

def generate_mock_history(symbol, start_val=100.0, num_days=150, trend=0.0):
    """Generates contiguous mock yfinance-style daily price bar history."""
    history = []
    curr_val = start_val
    import datetime
    base_date = datetime.date(2026, 1, 1)
    for i in range(num_days):
        d_str = (base_date + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        curr_val += trend
        history.append({
            "date": d_str,
            "open": curr_val - 1.0,
            "high": curr_val + 2.0,
            "low": curr_val - 2.0,
            "close": curr_val,
            "volume": 500000
        })
    return history

@patch("app.fetch_historical_prices")
def test_backtest_prep_api(mock_fetch_prices, client):
    # Setup mock yfinance historical response
    mock_history = generate_mock_history("NSE:TESTPREP", start_val=100.0, num_days=60)
    mock_fetch_prices.return_value = mock_history

    # Pre-seed watchlist or ipo listings so it has a symbol to process
    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("INSERT INTO ep_watchlist (symbol, exchange, catalyst_date, ep_type) VALUES ('TESTPREP', 'NSE', '2026-01-01', 'Volume EP')")
    conn.commit()
    conn.close()

    # Trigger prepare POST API
    res = client.post("/api/ep/backtest/prepare", json={
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "symbols": "TESTPREP"
    })
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data.get("success") is True

    # Allow thread initialization time
    time.sleep(0.15)

    # Poll status API until it finishes
    attempts = 0
    running = True
    while running and attempts < 30:
        time.sleep(0.2)
        res_status = client.get("/api/ep/backtest/prep_status")
        assert res_status.status_code == 200
        status_data = json.loads(res_status.data)
        running = status_data.get("running", False)
        attempts += 1

    # Verify that preparation finished successfully and populated db
    res_status = client.get("/api/ep/backtest/prep_status")
    status_data = json.loads(res_status.data)
    assert status_data.get("running") is False
    assert status_data.get("error") is None
    assert status_data.get("processed") >= 1

    # Check that daily_bars are inserted
    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM daily_bars WHERE symbol = 'TESTPREP'")
    count = c.fetchone()[0]
    conn.close()
    assert count > 0

def test_ep_backtest_simulation_engine(client):
    # Seed db with daily bars for a candidate stock: 25 prior days and 60 forward days
    # Symbol: BTEST
    # EP Date: 2026-02-01 (index 25)
    # Entry Date: 2026-02-02 (index 26)
    conn = orig_connect(db_path)
    c = conn.cursor()
    
    # 1. Seed candidate record
    c.execute("""
        INSERT INTO ep_features (symbol, exchange, feature_date, ep_score, ep_type, confidence, gap_pct, rel_volume, close_loc)
        VALUES ('BTEST', 'NSE', '2026-02-01', 0.82, 'Growth EP', 'HIGH', 5.0, 4.0, 0.9)
    """)
    
    # 2. Seed daily bars
    import datetime
    base_date = datetime.date(2026, 1, 1)
    
    # Generate 100 bars starting at ₹100, trailing up to ₹130
    for i in range(100):
        t_date = (base_date + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        close_price = 100.0 + (i * 0.3)
        open_price = close_price - 0.5
        high_price = close_price + 1.0
        low_price = close_price - 1.5
        
        c.execute("""
            INSERT INTO daily_bars (symbol, exchange, trade_date, open, high, low, close, volume, prev_close, gap_pct, close_loc, atr_14)
            VALUES (?, 'NSE', ?, ?, ?, ?, ?, 1000000, 100.0, 2.0, 0.8, 2.0)
        """, (
            'BTEST', t_date, open_price, high_price, low_price, close_price
        ))
        
    conn.commit()
    conn.close()
    
    # Trigger backtest POST API with FIXED_PCT exit rule (take profit +20%)
    res = client.post("/api/ep/backtest", json={
        "ep_type": "all",
        "from_date": "2026-01-01",
        "to_date": "2026-05-31",
        "min_ep_score": 0.55,
        "entry_rule": "DAY1_OPEN",
        "stop_rule": "DAY1_LOW",
        "exit_rule": "FIXED_PCT",
        "position_size_pct": 10.0,
        "capital": 1000000.0
    })
    
    assert res.status_code == 200
    data = json.loads(res.data)
    
    assert "summary" in data
    assert "equity_curve" in data
    assert "trades" in data
    
    summary = data["summary"]
    assert summary["total_trades"] == 1
    assert len(data["trades"]) == 1
    assert data["trades"][0]["symbol"] == "BTEST"
    assert data["trades"][0]["ep_type"] == "Growth EP"
    assert data["trades"][0]["ep_date"] == "2026-02-01"
    
    # Trigger backtest with 20D_MA exit rule
    res_ma = client.post("/api/ep/backtest", json={
        "ep_type": "all",
        "from_date": "2026-01-01",
        "to_date": "2026-05-31",
        "min_ep_score": 0.55,
        "entry_rule": "DAY1_OPEN",
        "stop_rule": "DAY1_LOW",
        "exit_rule": "20D_MA",
        "position_size_pct": 5.0,
        "capital": 1000000.0
    })
    assert res_ma.status_code == 200
    data_ma = json.loads(res_ma.data)
    assert data_ma["summary"]["total_trades"] == 1

def test_themes_and_rotation_apis(client):
    conn = orig_connect(db_path)
    c = conn.cursor()
    
    # Setup mock ep_features for today
    # Latest date is 2026-06-12
    c.execute("""
        INSERT INTO ep_features (symbol, exchange, feature_date, ep_score, ep_type, confidence, gap_pct, rel_volume, close_loc, neglect_score, catalyst_score, repricing_score, market_cap_cr)
        VALUES ('STORYSTK', 'NSE', '2026-06-12', 0.85, 'Story EP', 'HIGH', 10.0, 5.0, 0.9, 0.5, 0.8, 0.8, 500.0)
    """)
    c.execute("""
        INSERT INTO ep_features (symbol, exchange, feature_date, ep_score, ep_type, confidence, gap_pct, rel_volume, close_loc, neglect_score, catalyst_score, repricing_score, market_cap_cr)
        VALUES ('VOLSTK', 'NSE', '2026-06-12', 0.75, 'Volume EP', 'MEDIUM', 5.0, 4.0, 0.7, 0.4, 0.6, 0.7, 600.0)
    """)
    c.execute("""
        INSERT INTO ep_features (symbol, exchange, feature_date, ep_score, ep_type, confidence, gap_pct, rel_volume, close_loc, neglect_score, catalyst_score, repricing_score, market_cap_cr)
        VALUES ('GROWTHSTK', 'NSE', '2026-06-12', 0.90, 'Growth EP', 'HIGH', 8.0, 6.0, 0.8, 0.6, 0.9, 0.9, 700.0)
    """)
    
    # Setup sectors in ipo_listings
    c.execute("""
        INSERT INTO ipo_listings (ticker, company_name, sector, listing_date)
        VALUES ('STORYSTK', 'Story Corp', 'Green Energy', '2026-01-01')
    """)
    c.execute("""
        INSERT INTO ipo_listings (ticker, company_name, sector, listing_date)
        VALUES ('VOLSTK', 'Vol Corp', 'Green Energy', '2026-01-01')
    """)
    c.execute("""
        INSERT INTO ipo_listings (ticker, company_name, sector, listing_date)
        VALUES ('GROWTHSTK', 'Growth Corp', 'Green Energy', '2026-01-01')
    """)
    
    # Setup sector rotation in rrg_history
    c.execute("""
        INSERT INTO rrg_history (sector, jdk_rs, jdk_rs_momentum, score, quadrant, week, snapped_at)
        VALUES ('Green Energy', 102.5, 99.5, 85.0, 'Weakening', '2026-W24', '2026-06-12 18:00:00')
    """)
    
    # Setup watchlist item to overlay count
    c.execute("""
        INSERT INTO ep_watchlist (symbol, exchange, catalyst_date, ep_type, status)
        VALUES ('STORYSTK', 'NSE', '2026-06-12', 'Story EP', 'ACTIVE')
    """)
    
    conn.commit()
    conn.close()
    
    # 1. Test /api/ep/themes
    res_themes = client.get("/api/ep/themes")
    assert res_themes.status_code == 200
    themes_data = json.loads(res_themes.data)
    assert "themes" in themes_data
    assert len(themes_data["themes"]) == 1
    assert themes_data["themes"][0]["theme"] == "Green Energy"
    assert themes_data["themes"][0]["count"] == 2
    assert themes_data["themes"][0]["avg_score"] == 0.80
    assert "STORYSTK" in themes_data["themes"][0]["symbols"]
    assert "VOLSTK" in themes_data["themes"][0]["symbols"]
    assert "GROWTHSTK" not in themes_data["themes"][0]["symbols"]
    
    # Test /api/ep/themes with ?types=all
    res_themes_all = client.get("/api/ep/themes?types=all")
    assert res_themes_all.status_code == 200
    themes_all_data = json.loads(res_themes_all.data)
    assert len(themes_all_data["themes"]) == 1
    assert themes_all_data["themes"][0]["count"] == 3
    assert "GROWTHSTK" in themes_all_data["themes"][0]["symbols"]
    
    # 2. Test /api/ep/sector-rotation
    res_rot = client.get("/api/ep/sector-rotation")
    assert res_rot.status_code == 200
    rot_data = json.loads(res_rot.data)
    assert "rotation" in rot_data
    assert len(rot_data["rotation"]) == 1
    assert rot_data["rotation"][0]["sector"] == "Green Energy"
    assert rot_data["rotation"][0]["quadrant"] == "Weakening"
    assert rot_data["rotation"][0]["active_ep_count"] == 1
