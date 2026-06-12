import pytest
import sqlite3
import json
import os
import tempfile
import sys
from unittest.mock import patch, MagicMock

# 1. Setup the test DB mock first
db_fd, db_path = tempfile.mkstemp()

orig_connect = sqlite3.connect

@pytest.fixture(autouse=True)
def patch_sqlite(monkeypatch):
    def mock_connect(database, *args, **kwargs):
        if database == "scan_history.db":
            return orig_connect(db_path, *args, **kwargs)
        return orig_connect(database, *args, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", mock_connect)
    app.init_db()

# Now insert root path and import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app

from app import (
    app as flask_app,
    compute_ep_score,
    compute_catalyst_score,
    assign_ep_type,
    refresh_ep_screener
)

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
    c.execute("DELETE FROM ep_watchlist")
    c.execute("DELETE FROM sugar_babies")
    c.execute("DELETE FROM ep_features")
    conn.commit()
    conn.close()

def test_short_ep_scoring():
    # Guidance cut catalyst score should be negative
    cat_score = compute_catalyst_score("GUIDANCE_CUT", None, None)
    assert cat_score == -0.80
    
    # EP score should use absolute catalyst score, so it scores highly
    ep_score = compute_ep_score(neglect_score=0.60, catalyst_score=cat_score, repricing_score=0.70)
    assert ep_score > 0.55
    
    # EP type should be Short EP
    ep_type = assign_ep_type(cat_score, "GUIDANCE_CUT", 3.0, -5.0)
    assert ep_type == "Short EP"

def test_watchlist_apis(client):
    # Try adding to watchlist with stop and notes
    res = client.post("/api/ep/watchlist", json={
        "symbol": "TESTSTK",
        "exchange": "NSE",
        "stop_price": 120.50,
        "notes": "Testing watchlist POST"
    })
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data.get("success") is True
    
    # Check details endpoint returns watchlist state
    # First mock detail features row in ep_features
    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("""
        INSERT INTO ep_features (symbol, exchange, feature_date, ep_score, ep_type, confidence)
        VALUES ('TESTSTK', 'NSE', '2026-06-12', 0.75, 'Growth EP', 'HIGH')
    """)
    conn.commit()
    conn.close()
    
    res = client.get("/api/ep/TESTSTK/detail")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data.get("watchlist_status") == "ACTIVE"
    assert data.get("watchlist_stop") == 120.50
    assert data.get("watchlist_notes") == "Testing watchlist POST"
    assert data.get("is_sugar_baby") == 0
    
    # Trigger watchlist manually
    res = client.post("/api/ep/watchlist/trigger", json={"symbol": "TESTSTK"})
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data.get("success") is True
    
    # Verify it is now TRIGGERED
    res = client.get("/api/ep/TESTSTK/detail")
    data = json.loads(res.data)
    assert data.get("watchlist_status") == "TRIGGERED"
    
    # Re-add/Update watchlist
    res = client.post("/api/ep/watchlist", json={
        "symbol": "TESTSTK",
        "exchange": "NSE",
        "stop_price": 125.00,
        "notes": "Testing watchlist update"
    })
    # Since existing active watchlist is TRIGGERED (not ACTIVE), this inserts a new ACTIVE watchlist entry!
    assert res.status_code == 200
    res = client.get("/api/ep/TESTSTK/detail")
    data = json.loads(res.data)
    assert data.get("watchlist_status") == "ACTIVE"
    assert data.get("watchlist_stop") == 125.00
    assert data.get("watchlist_notes") == "Testing watchlist update"

    # Remove (delete) watchlist
    res = client.post("/api/ep/watchlist/delete", json={"symbol": "TESTSTK"})
    assert res.status_code == 200
    res = client.get("/api/ep/TESTSTK/detail")
    data = json.loads(res.data)
    assert data.get("watchlist_status") == "EXPIRED"

def test_sugar_babies_api(client):
    # Mock detail features row in ep_features so detail call doesn't 404
    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("""
        INSERT INTO ep_features (symbol, exchange, feature_date, ep_score, ep_type, confidence)
        VALUES ('TESTSTK', 'NSE', '2026-06-12', 0.75, 'Growth EP', 'HIGH')
    """)
    conn.commit()
    conn.close()

    # Add to Sugar Babies
    res = client.post("/api/ep/sugar-babies", json={
        "symbol": "TESTSTK",
        "exchange": "NSE",
        "notes": "Sweetest baby"
    })
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data.get("success") is True
    
    # Check details
    res = client.get("/api/ep/TESTSTK/detail")
    data = json.loads(res.data)
    assert data.get("is_sugar_baby") == 1
    
    # Remove from Sugar Babies
    res = client.post("/api/ep/sugar-babies", json={
        "symbol": "TESTSTK",
        "is_active": 0
    })
    assert res.status_code == 200
    res = client.get("/api/ep/TESTSTK/detail")
    data = json.loads(res.data)
    assert data.get("is_sugar_baby") == 0

@patch("app.fetch_historical_prices")
@patch("requests.post")
def test_nightly_delayed_ep_triggers(mock_post, mock_fetch_prices):
    # Setup mock active watchlist
    conn = orig_connect(db_path)
    c = conn.cursor()
    
    # 1. Red-to-Green candidate
    c.execute("""
        INSERT INTO ep_watchlist (symbol, exchange, catalyst_date, ep_type, status, ep_score, entry_price)
        VALUES ('RTGSTOCK', 'NSE', '2026-06-01', 'Growth EP', 'ACTIVE', 0.70, 100.0)
    """)
    # 2. Range Breakout candidate
    c.execute("""
        INSERT INTO ep_watchlist (symbol, exchange, catalyst_date, ep_type, status, ep_score, entry_price)
        VALUES ('BOSTOCK', 'NSE', '2026-06-01', 'Growth EP', 'ACTIVE', 0.70, 100.0)
    """)
    # 3. Level Reclaim candidate
    c.execute("""
        INSERT INTO ep_watchlist (symbol, exchange, catalyst_date, ep_type, status, ep_score, entry_price)
        VALUES ('RECSTOCK', 'NSE', '2026-06-01', 'Growth EP', 'ACTIVE', 0.70, 100.0)
    """)
    # 4. Short EP Failed Bounce candidate
    c.execute("""
        INSERT INTO ep_watchlist (symbol, exchange, catalyst_date, ep_type, status, ep_score, entry_price)
        VALUES ('SHORTSTOCK', 'NSE', '2026-06-01', 'Short EP', 'ACTIVE', 0.70, 100.0)
    """)
    
    conn.commit()
    conn.close()

    # Define mock histories
    # A bar has: date, open, high, low, close, volume
    # RTG: Open < Prev Close (98 < 100), Close > Prev Close (102 > 100), Rel Vol >= 1.5
    rtg_history = [{"date": f"2026-06-{i:02d}", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000} for i in range(1, 21)]
    rtg_history.append({"date": "2026-06-21", "open": 98.0, "high": 103.0, "low": 97.0, "close": 102.0, "volume": 2000}) # 2.0x volume

    # BO: Consolidation range < 8% for 5 days. Today close > 5-day high. Volume >= 2.0x
    bo_history = [{"date": f"2026-06-{i:02d}", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000} for i in range(1, 21)]
    bo_history.append({"date": "2026-06-21", "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 3000}) # 3.0x volume
    
    # REC: Prev Close < catalyst_close (98 < 100), Today Close >= catalyst_close * 0.995 (100 >= 99.5), Rel Vol >= 1.5
    rec_history = [{"date": f"2026-06-{i:02d}", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000} for i in range(1, 20)]
    rec_history.append({"date": "2026-06-20", "open": 98.0, "high": 99.0, "low": 97.0, "close": 98.0, "volume": 1000}) # prev close 98
    rec_history.append({"date": "2026-06-21", "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.5, "volume": 2000}) # today close 100.5, 2.0x volume

    # Short: Today Close < Prev Close (97 < 100), Rel Vol >= 1.2
    short_history = [{"date": f"2026-06-{i:02d}", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000} for i in range(1, 21)]
    short_history.append({"date": "2026-06-21", "open": 100.0, "high": 101.0, "low": 96.0, "close": 97.0, "volume": 1500}) # 1.5x volume

    def side_effect(ticker, range_str="6mo"):
        if "RTGSTOCK" in ticker:
            return rtg_history
        elif "BOSTOCK" in ticker:
            return bo_history
        elif "RECSTOCK" in ticker:
            return rec_history
        elif "SHORTSTOCK" in ticker:
            return short_history
        return []
        
    mock_fetch_prices.side_effect = side_effect
    
    # Mock TradingView POST response
    mock_tv_response = MagicMock()
    mock_tv_response.json.return_value = {"data": []}
    mock_post.return_value = mock_tv_response
    
    # Run EOD refresh
    refresh_ep_screener()
    
    # Check trigger statuses in DB
    conn = orig_connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT symbol, status, trigger_type, entry_price FROM ep_watchlist ORDER BY symbol")
    results = c.fetchall()
    conn.close()
    
    # Map results
    res_dict = {r[0]: {"status": r[1], "trigger": r[2], "entry": r[3]} for r in results}
    
    assert res_dict["RTGSTOCK"]["status"] == "TRIGGERED"
    assert res_dict["RTGSTOCK"]["trigger"] == "RED_TO_GREEN"
    assert res_dict["RTGSTOCK"]["entry"] == 102.0
    
    assert res_dict["BOSTOCK"]["status"] == "TRIGGERED"
    assert res_dict["BOSTOCK"]["trigger"] == "RANGE_BREAKOUT"
    assert res_dict["BOSTOCK"]["entry"] == 104.0
    
    assert res_dict["RECSTOCK"]["status"] == "TRIGGERED"
    assert res_dict["RECSTOCK"]["trigger"] == "RECLAIM"
    assert res_dict["RECSTOCK"]["entry"] == 100.5
    
    assert res_dict["SHORTSTOCK"]["status"] == "TRIGGERED"
    assert res_dict["SHORTSTOCK"]["trigger"] == "FAILED_BOUNCE"
    assert res_dict["SHORTSTOCK"]["entry"] == 97.0
