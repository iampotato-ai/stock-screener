import pytest
import sqlite3
import json
import os
import tempfile
import sys
from unittest.mock import patch, MagicMock

# 1. Setup the test DB mock first
db_fd, db_path = tempfile.mkstemp()

orig_connect = getattr(sqlite3, "__original_connect__", sqlite3.connect)

# Set PYTEST_CURRENT_TEST env var BEFORE importing app so init_scheduler's
# guard fires and the background scheduler does NOT start.
# This prevents the IPO warmup one-shot job (fires 10s after import) from
# writing to the database and causing 'database is locked' during tests.
os.environ.setdefault('PYTEST_CURRENT_TEST', 'test_phase3_delayed_ep.py::setup')

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

# Force TESTING=True immediately so no background tasks run in any subsequent
# test client or app_context that might be pushed.
flask_app.config['TESTING'] = True

# Shut down background scheduler if it started despite the env guard.
# This is a fallback for environments where the guard may have been bypassed.
if hasattr(flask_app, 'scheduler') and flask_app.scheduler:
    try:
        flask_app.scheduler.shutdown(wait=False)
    except Exception:
        pass
# Also check APScheduler's running attribute in case it's a direct reference
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    import gc
    for obj in gc.get_objects():
        if isinstance(obj, BackgroundScheduler) and obj.running:
            try:
                obj.shutdown(wait=False)
            except Exception:
                pass
except Exception:
    pass



@pytest.fixture(autouse=True)
def patch_sqlite(monkeypatch):
    from app.database import init_db_standalone
    from app.extensions import db
    init_db_standalone(db_path)
    # Dispose SQLAlchemy engine pool to release any open connections
    # so subsequent raw sqlite3 connections don't hit a lock
    try:
        with flask_app.app_context():
            db.session.remove()
            db.engine.dispose()
    except Exception:
        pass

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
    from app.extensions import db
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
    flask_app.config['DATABASE'] = db_path
    flask_app.config['TESTING'] = True
    with flask_app.app_context():
        try:
            db.session.remove()
            db.engine.dispose()
            db.create_all()
            # Dispose again after create_all to release the pool connection
            db.engine.dispose()
        except Exception:
            pass
    with flask_app.test_client() as client:
        yield client
    # Teardown: release engine pool after each test that uses this fixture
    try:
        with flask_app.app_context():
            db.session.remove()
            db.engine.dispose()
    except Exception:
        pass

@pytest.fixture(autouse=True)
def clean_db(patch_sqlite):
    # Use timeout=30 so raw connection waits if SQLAlchemy pool hasn't fully
    # released its connection yet (race between engine.dispose() and OS unlock)
    conn = orig_connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")  # ensure WAL so reads don't block writes
    c = conn.cursor()
    c.execute("DELETE FROM ep_watchlist")
    c.execute("DELETE FROM sugar_babies")
    c.execute("DELETE FROM ep_features")
    conn.commit()
    conn.close()

def test_short_ep_scoring():
    # Guidance cut catalyst score should be negative
    cat_score = compute_catalyst_score("GUIDANCE_CUT", None, None, 0, None)
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
    res = client.post("/api/ep/watchlist/remove", json={"symbol": "TESTSTK"})
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

@patch("app.send_telegram_alert")
@patch("app.fetch_historical_prices")
@patch("requests.post")
def test_nightly_delayed_ep_triggers(mock_post, mock_fetch_prices, mock_send_alert):
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
    # 5. Level Reclaim with None catalyst close (manual add, should NOT trigger)
    c.execute("""
        INSERT INTO ep_watchlist (symbol, exchange, catalyst_date, ep_type, status, ep_score, entry_price)
        VALUES ('RECSTOCKNONE', 'NSE', '2026-06-01', 'Growth EP', 'ACTIVE', 0.70, NULL)
    """)
    # 6. Active Sugar Baby whose episode_count should update nightly
    c.execute("""
        INSERT INTO sugar_babies (symbol, exchange, added_date, episode_count, is_active)
        VALUES ('RTGSTOCK', 'NSE', '2026-06-01', 0, 1)
    """)
    # Insert a mock ep_feature for RTGSTOCK so it has 1 episode
    c.execute("""
        INSERT INTO ep_features (symbol, exchange, feature_date, ep_score, ep_type, confidence)
        VALUES ('RTGSTOCK', 'NSE', '2026-06-12', 0.75, 'Growth EP', 'HIGH')
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
        elif "RECSTOCKNONE" in ticker:
            return rec_history
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
    
    # Verify catalyst_close = None did NOT trigger reclaim, remaining ACTIVE
    assert res_dict["RECSTOCKNONE"]["status"] == "ACTIVE"
    assert res_dict["RECSTOCKNONE"]["trigger"] is None
    
    # Verify Sugar Babies episode_count nightly update
    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("SELECT episode_count FROM sugar_babies WHERE symbol = 'RTGSTOCK'")
    sb_count = c.fetchone()[0]
    conn.close()
    assert sb_count == 1
    
    # Verify Telegram alerts were sent for the 4 triggered setups
    assert mock_send_alert.call_count == 4


@patch("app.send_telegram_alert")
@patch("app.fetch_historical_prices")
@patch("app.fetch_screener_fundamentals")
@patch("app.fetch_nse_announcements")
@patch("requests.post")
def test_high_confidence_alert(mock_post, mock_fetch_announcements, mock_fetch_fundamentals, mock_fetch_prices, mock_send_alert):
    # Setup mock TradingView response with a stock
    mock_tv_response = MagicMock()
    mock_tv_response.json.return_value = {
        "data": [
            {
                "s": "NSE:HIGHSTK",
                "d": [
                    "HIGHSTK",
                    "High confidence mock stock",
                    112.0,      # close
                    12.0,        # change
                    3000000.0,  # volume
                    10000000000.0, # market_cap_basic
                    100000.0,   # average_volume
                    "Technology Services" # sector
                ]
            },
            {
                "s": "NSE:STK2",
                "d": ["STK2", "S2", 100.0, 0, 0, 100000000.0, 20000.0, "Technology Services"]
            },
            {
                "s": "NSE:STK3",
                "d": ["STK3", "S3", 100.0, 0, 0, 100000000.0, 30000.0, "Technology Services"]
            },
            {
                "s": "NSE:STK4",
                "d": ["STK4", "S4", 100.0, 0, 0, 100000000.0, 40000.0, "Technology Services"]
            },
            {
                "s": "NSE:STK5",
                "d": ["STK5", "S5", 100.0, 0, 0, 100000000.0, 50000.0, "Technology Services"]
            }
        ]
    }
    mock_post.return_value = mock_tv_response

    # Generate valid historical dates
    import datetime
    base_dt = datetime.date(2026, 6, 20)
    mock_history = []
    for i in range(149):
        d = base_dt - datetime.timedelta(days=150-i)
        # Descending price to simulate neglect
        c_val = 140.0 if i < 90 else 100.0
        mock_history.append({
            "date": d.strftime("%Y-%m-%d"),
            "open": c_val - 2.0,
            "high": c_val + 2.0,
            "low": c_val - 3.0,
            "close": c_val,
            "volume": 100000.0
        })
    # Breakout bar: gap 10%, rel volume 30x (3000000), close loc 1.0 (close=high), price change 12%
    mock_history.append({
        "date": "2026-06-21",
        "open": 110.0,
        "high": 112.0,
        "low": 110.0,
        "close": 112.0,
        "volume": 3000000.0
    })
    mock_fetch_prices.return_value = mock_history

    # Mock fundamentals for blowout earnings (5 quarters to allow YoY calculation)
    mock_fetch_fundamentals.return_value = [
        {"quarter": "Jun 2025", "date_key": "2025-06-30", "revenue": 100.0, "net_profit": 10.0, "eps": 1.0},
        {"quarter": "Sep 2025", "date_key": "2025-09-30", "revenue": 110.0, "net_profit": 12.0, "eps": 1.2},
        {"quarter": "Dec 2025", "date_key": "2025-12-30", "revenue": 120.0, "net_profit": 15.0, "eps": 1.5},
        {"quarter": "Mar 2026", "date_key": "2026-03-31", "revenue": 130.0, "net_profit": 18.0, "eps": 1.8},
        {"quarter": "Jun 2026", "date_key": "2026-06-30", "revenue": 260.0, "net_profit": 40.0, "eps": 4.0} # YoY rev +160%, YoY net profit +300%
    ]
    mock_fetch_announcements.return_value = []

    # Run refresh
    refresh_ep_screener()

    # Query DB features for debugging
    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("SELECT ep_score, confidence, neglect_score, catalyst_score, repricing_score, ep_type FROM ep_features WHERE symbol = 'HIGHSTK'")
    row = c.fetchone()
    print("DEBUG HIGHSTK feature row:", row)
    conn.close()

    # Assert that send_telegram_alert was called with a new HIGH confidence EP message
    assert mock_send_alert.call_count >= 1
    found_high_alert = False
    for call in mock_send_alert.call_args_list:
        msg = call[0][0]
        if "New HIGH Confidence EP Detected" in msg and "HIGHSTK" in msg:
            found_high_alert = True
            break
    assert found_high_alert, "Should send Telegram alert for HIGH confidence EP candidate"


@patch("app.send_telegram_alert")
@patch("app.fetch_historical_prices")
@patch("app.fetch_screener_fundamentals")
@patch("app.fetch_nse_announcements")
@patch("requests.post")
def test_transaction_isolation(mock_post, mock_fetch_announcements, mock_fetch_fundamentals, mock_fetch_prices, mock_send_alert):
    # STK_OK and STK_FAIL candidates
    mock_tv_response = MagicMock()
    mock_tv_response.json.return_value = {
        "data": [
            {
                "s": "NSE:STK_OK",
                "d": ["STK_OK", "STK_OK desc", 100.0, 0, 100000.0, 100000000.0, 20000.0, "Tech"]
            },
            {
                "s": "NSE:STK_FAIL",
                "d": ["STK_FAIL", "STK_FAIL desc", 100.0, 0, 100000.0, 100000000.0, 30000.0, "Tech"]
            }
        ]
    }
    mock_post.return_value = mock_tv_response

    # Mock historical prices: STK_OK succeeds, STK_FAIL throws exception
    def side_effect(ticker, range_str="6mo"):
        if "STK_OK" in ticker:
            import datetime
            base_dt = datetime.date(2026, 6, 20)
            mock_history = []
            for i in range(150):
                d = base_dt - datetime.timedelta(days=150-i)
                mock_history.append({
                    "date": d.strftime("%Y-%m-%d"),
                    "open": 98.0,
                    "high": 102.0,
                    "low": 97.0,
                    "close": 100.0,
                    "volume": 100000.0
                })
            return mock_history
        elif "STK_FAIL" in ticker:
            raise ValueError("Simulated network failure for STK_FAIL")
        return []

    mock_fetch_prices.side_effect = side_effect
    mock_fetch_fundamentals.return_value = []
    mock_fetch_announcements.return_value = []

    # Run EOD refresh - should not crash because STK_FAIL's exception is caught
    refresh_ep_screener()

    # Query DB to check if STK_OK features were successfully committed
    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("SELECT symbol FROM ep_features WHERE symbol = 'STK_OK'")
    ok_row = c.fetchone()
    c.execute("SELECT symbol FROM ep_features WHERE symbol = 'STK_FAIL'")
    fail_row = c.fetchone()
    conn.close()

    assert ok_row is not None
    assert ok_row[0] == "STK_OK"
    assert fail_row is None


@patch("app.send_telegram_alert")
@patch("app.fetch_historical_prices")
@patch("app.fetch_screener_fundamentals")
@patch("app.fetch_nse_announcements")
@patch("requests.post")
def test_catalyst_close_no_drift(mock_post, mock_fetch_announcements, mock_fetch_fundamentals, mock_fetch_prices, mock_send_alert):
    # 1. Detect stock first time at close=100.0
    mock_tv_response = MagicMock()
    mock_tv_response.json.return_value = {
        "data": [
            {
                "s": "NSE:DRIFTSTK",
                "d": ["DRIFTSTK", "Drift stock", 100.0, 0, 100000.0, 100000000.0, 20000.0, "Tech"]
            }
        ]
    }
    mock_post.return_value = mock_tv_response

    import datetime
    base_dt = datetime.date(2026, 6, 20)
    
    # We will return a history ending at close=100.0 first
    history_1 = []
    for i in range(149):
        d = base_dt - datetime.timedelta(days=150-i)
        history_1.append({"date": d.strftime("%Y-%m-%d"), "open": 98.0, "high": 102.0, "low": 97.0, "close": 100.0, "volume": 10000.0})
    history_1.append({"date": "2026-06-20", "open": 105.0, "high": 110.0, "low": 104.0, "close": 110.0, "volume": 100000.0}) # EP! Score >= 0.55

    # Fundamentals to make score high
    mock_fetch_fundamentals.return_value = [
        {"quarter": "Jun 2025", "date_key": "2025-06-30", "revenue": 100.0, "net_profit": 10.0, "eps": 1.0},
        {"quarter": "Jun 2026", "date_key": "2026-06-30", "revenue": 200.0, "net_profit": 30.0, "eps": 3.0}
    ]
    mock_fetch_announcements.return_value = []
    mock_fetch_prices.return_value = history_1

    # First run: inserts DRIFTSTK into watchlist as ACTIVE
    refresh_ep_screener()

    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("SELECT catalyst_close, entry_price, status FROM ep_watchlist WHERE symbol = 'DRIFTSTK'")
    row = c.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == 110.0  # catalyst_close
    assert row[1] == 110.0  # entry_price
    assert row[2] == "ACTIVE"

    # 2. Second run: stock scans again but price has moved to 120.0
    history_2 = list(history_1)
    history_2.append({"date": "2026-06-21", "open": 115.0, "high": 125.0, "low": 114.0, "close": 120.0, "volume": 100000.0}) # EP again
    mock_fetch_prices.return_value = history_2

    refresh_ep_screener()

    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("SELECT catalyst_close, entry_price, catalyst_date FROM ep_watchlist WHERE symbol = 'DRIFTSTK'")
    row = c.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == 110.0  # catalyst_close must NOT drift!
    # entry_price should also not change (remain original close of 110.0)
    assert row[1] == 110.0
    # catalyst_date must also not drift (remain 2026-06-20)
    assert row[2] == "2026-06-20"


@patch("app.send_telegram_alert")
@patch("app.fetch_historical_prices")
@patch("requests.post")
def test_days_on_watch_idempotent(mock_post, mock_fetch_prices, mock_send_alert):
    mock_tv_response = MagicMock()
    mock_tv_response.json.return_value = {"data": []}
    mock_post.return_value = mock_tv_response
    mock_fetch_prices.return_value = []

    # Insert an ACTIVE watchlist item with last_incremented_date as NULL
    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("""
        INSERT INTO ep_watchlist (symbol, exchange, catalyst_date, ep_type, status, ep_score, entry_price, days_on_watch, last_incremented_date)
        VALUES ('IDEMPSTOCK', 'NSE', '2026-06-01', 'Growth EP', 'ACTIVE', 0.70, 100.0, 5, NULL)
    """)
    conn.commit()
    conn.close()

    # First run today: increments days_on_watch to 6, sets last_incremented_date to date('now')
    refresh_ep_screener()

    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("SELECT days_on_watch, last_incremented_date FROM ep_watchlist WHERE symbol = 'IDEMPSTOCK'")
    row1 = c.fetchone()
    conn.close()

    assert row1[0] == 6
    assert row1[1] is not None

    # Second run today: should NOT increment again
    refresh_ep_screener()

    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("SELECT days_on_watch, last_incremented_date FROM ep_watchlist WHERE symbol = 'IDEMPSTOCK'")
    row2 = c.fetchone()
    conn.close()

    assert row2[0] == 6  # still 6!


@patch("app.send_telegram_alert")
@patch("app.fetch_historical_prices")
@patch("app.fetch_screener_fundamentals")
@patch("app.fetch_nse_announcements")
@patch("requests.post")
def test_high_confidence_alert_no_duplicates(mock_post, mock_fetch_announcements, mock_fetch_fundamentals, mock_fetch_prices, mock_send_alert):
    # Clear databases for isolation
    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("DELETE FROM ep_watchlist")
    c.execute("DELETE FROM ep_features")
    conn.commit()
    conn.close()

    mock_tv_response = MagicMock()
    mock_tv_response.json.return_value = {
        "data": [
            {
                "s": "NSE:ALERTSHOT",
                "d": ["ALERTSHOT", "Alert stock", 112.0, 12.0, 3000000.0, 10000000000.0, 100000.0, "Tech"]
            }
        ]
    }
    mock_post.return_value = mock_tv_response

    import datetime
    base_dt = datetime.date(2026, 6, 20)
    mock_history = []
    for i in range(149):
        d = base_dt - datetime.timedelta(days=150-i)
        mock_history.append({"date": d.strftime("%Y-%m-%d"), "open": 98.0, "high": 102.0, "low": 97.0, "close": 100.0, "volume": 100000.0})
    mock_history.append({"date": "2026-06-21", "open": 110.0, "high": 112.0, "low": 110.0, "close": 112.0, "volume": 3000000.0})
    mock_fetch_prices.return_value = mock_history

    mock_fetch_fundamentals.return_value = [
        {"quarter": "Jun 2025", "date_key": "2025-06-30", "revenue": 100.0, "net_profit": 10.0, "eps": 1.0},
        {"quarter": "Jun 2026", "date_key": "2026-06-30", "revenue": 200.0, "net_profit": 30.0, "eps": 3.0}
    ]
    mock_fetch_announcements.return_value = []

    # First run (new detection) - should trigger one alert
    refresh_ep_screener()
    assert mock_send_alert.call_count == 1

    # Reset alert mock
    mock_send_alert.reset_mock()

    # Second run (already exists) - should NOT send alert again
    refresh_ep_screener()
    assert mock_send_alert.call_count == 0

