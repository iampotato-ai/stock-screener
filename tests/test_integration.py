import pytest
import sqlite3
import json
import sys
import os

# Ensure the root folder is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app, init_db

db_file = None

@pytest.fixture(autouse=True)
def use_test_db(monkeypatch, tmp_path):
    global db_file
    db_file = str(tmp_path / "test_scan_history.db")
    orig_connect = getattr(sqlite3, "__original_connect__", sqlite3.connect)
    
    # Initialize the test DB tables
    conn = orig_connect(db_file)
    c = conn.cursor()
    # Create the tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_journal (
            id TEXT PRIMARY KEY,
            ticker TEXT,
            name TEXT,
            date TEXT,
            entry REAL,
            stop REAL,
            target1 REAL,
            target2 REAL,
            target3 REAL,
            riskAmount REAL,
            qty INTEGER,
            status TEXT,
            exitPrice REAL,
            exitDate TEXT,
            pnl REAL,
            rAchieved REAL,
            notes TEXT,
            setupLabel TEXT,
            swingband TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS kronos_forecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            pred_len INTEGER,
            model_type TEXT,
            forecast_json TEXT,
            last_close REAL,
            generated_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS scan_stats (
            date TEXT PRIMARY KEY,
            total_scanned INTEGER,
            green_dots INTEGER,
            orange_dots INTEGER,
            red_dots INTEGER,
            avg_swing_score REAL,
            breadth_ratio REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS market_regime_history (
            date TEXT PRIMARY KEY,
            state TEXT,
            index_level REAL,
            ma20 REAL,
            ma50 REAL,
            breadth_ratio REAL,
            change_reason TEXT
        )
    ''')
    conn.commit()
    conn.close()
    
    # Also call app's native init_db
    init_db()
    
    yield db_file

@pytest.fixture
def client():
    from app.extensions import db
    with app.app_context():
        try:
            db.session.remove()
            db.engine.dispose()
        except Exception as e:
            print(f"[DEBUG] Failed to dispose engine: {e}")
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_journal_crud_integration(client):
    # 1. Add/Create a new trade log
    trade_payload = {
        "id": "trade-test-12345",
        "ticker": "WELCORP",
        "name": "Welspun Corp Limited",
        "date": "2026-05-31",
        "entry": 100.0,
        "stop": 90.0,
        "qty": 10,
        "status": "open",
        "setupLabel": "Breakout Ready",
        "swingband": "strong"
    }
    
    res_create = client.post("/api/journal", json=trade_payload)
    assert res_create.status_code == 200
    assert res_create.get_json()["success"] is True
    
    # 2. Query/Read the trade list
    res_list = client.get("/api/journal")
    assert res_list.status_code == 200
    trades = res_list.get_json()
    assert len(trades) == 1
    assert trades[0]["id"] == "trade-test-12345"
    assert trades[0]["entry"] == 100.0
    assert trades[0]["status"] == "open"
    
    # 3. Update exitPrice (triggers server-side P&L and R computation)
    update_payload = {
        "id": "trade-test-12345",
        "exitPrice": 120.0,
        "exitDate": "2026-06-01"
    }
    res_update = client.put("/api/journal/trade-test-12345", json=update_payload)
    assert res_update.status_code == 200
    updated_data = res_update.get_json()
    assert updated_data["success"] is True
    
    # Read again and check calculated fields
    res_list_2 = client.get("/api/journal")
    trades_2 = res_list_2.get_json()
    assert trades_2[0]["status"] == "closed"
    assert trades_2[0]["exitPrice"] == 120.0
    # pnl = (120 - 100) * 10 = 200.0
    assert trades_2[0]["pnl"] == 200.0
    # rAchieved = 200.0 / ((100 - 90) * 10) = 2.0
    assert trades_2[0]["rAchieved"] == 2.0
    
    # 4. Delete the trade
    res_delete = client.delete("/api/journal/trade-test-12345")
    assert res_delete.status_code == 200
    assert res_delete.get_json()["success"] is True
    
    # Verify list is empty
    res_list_3 = client.get("/api/journal")
    assert len(res_list_3.get_json()) == 0


def test_kronos_forecast_route(client, monkeypatch):
    from datetime import datetime, timedelta
    start_date = datetime(2026, 1, 1)
    mock_history = []
    for i in range(120):
        curr = start_date + timedelta(days=i)
        mock_history.append({
            "date": curr.strftime("%Y-%m-%d"),
            "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 1000
        })
    
    # Track the call counts to verify caching behavior
    predict_call_count = 0
    
    def mock_fetch_historical_prices(ticker, range_str="1y"):
        return mock_history
        
    class MockPredictor:
        def predict(self, df, x_timestamp, y_timestamp, pred_len, T, top_p, sample_count, verbose, return_samples):
            nonlocal predict_call_count
            predict_call_count += 1
            import numpy as np
            samples = np.zeros((sample_count, pred_len, 6))
            for i in range(pred_len):
                samples[:, i, 0] = 100.0 + i  # open
                samples[:, i, 1] = 101.0 + i  # high
                samples[:, i, 2] = 99.0 + i   # low
                samples[:, i, 3] = 101.0 + i  # close
            return samples
            
    def mock_get_kronos_predictor():
        return MockPredictor()
        
    monkeypatch.setattr("app.fetch_historical_prices", mock_fetch_historical_prices)
    monkeypatch.setattr("app.get_kronos_predictor", mock_get_kronos_predictor)
    
    # First invocation: should hit the model and write to SQLite DB
    res1 = client.get("/api/kronos-forecast?ticker=WELCORP&pred_len=5&sample_count=10")
    assert res1.status_code == 200
    data1 = res1.get_json()
    assert len(data1["forecast"]) == 5
    assert data1["forecast"][0]["close"] == 101.0
    assert predict_call_count == 1
    
    # Second invocation: should hit the database cache directly without executing the model again
    res2 = client.get("/api/kronos-forecast?ticker=WELCORP&pred_len=5&sample_count=10")
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert len(data2["forecast"]) == 5
    assert predict_call_count == 1  # Predict count remains 1! Cache hit verified!


def test_ensemble_forecast_route(client, monkeypatch):
    from datetime import datetime, timedelta
    start_date = datetime(2026, 1, 1)
    mock_history = []
    for i in range(120):
        curr = start_date + timedelta(days=i)
        mock_history.append({
            "date": curr.strftime("%Y-%m-%d"),
            "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 1000
        })
    
    def mock_fetch_historical_prices(ticker, range_str="1y"):
        return mock_history
        
    def mock_kronos_predict(ticker, horizon=5):
        return [102.0, 104.0, 106.0, 108.0, 110.0]
        
    def mock_prophet_predict(ticker, horizon=5):
        return [100.0, 101.0, 102.0, 103.0, 104.0]
        
    def mock_arima_predict(ticker, horizon=5):
        return [101.0, 101.0, 101.0, 101.0, 101.0]
        
    monkeypatch.setattr("app.fetch_historical_prices", mock_fetch_historical_prices)
    monkeypatch.setattr("app.kronos_predict", mock_kronos_predict)
    # Mock prophet_predict and arima_predict directly as they run in parallel
    monkeypatch.setattr("app.prophet_predict", mock_prophet_predict)
    monkeypatch.setattr("app.arima_predict", mock_arima_predict)
    
    # Test POST /api/ensemble_forecast (static weights: 0.50, 0.30, 0.20)
    # Expected blended: 0.5*[102,104,106,108,110] + 0.3*[100,101,102,103,104] + 0.2*[101,101,101,101,101]
    # Point 1: 0.5*102 + 0.3*100 + 0.2*101 = 51.0 + 30.0 + 20.2 = 101.2
    payload = {
        "ticker": "WELCORP",
        "horizon": 5,
        "use_dynamic_weights": False
    }
    
    res = client.post("/api/ensemble_forecast", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["ensemble_path"]) == 5
    assert pytest.approx(data["ensemble_path"][0]) == 101.2
    assert "conviction" in data
    assert "agreement_matrix" in data


def test_breadth_history_limit(client):
    # Insert multiple breadth history records
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute("DELETE FROM breadth_history")
    for i in range(15):
        date_str = f"2026-06-{i+1:02d}"
        c.execute("""
            INSERT INTO breadth_history (date, time, advances, declines, unchanged, pct_sma21, pct_sma50, pct_52high, avg_recommend, regime_score, regime_band)
            VALUES (?, '15:30', 200, 100, 50, 0.65, 0.55, 0.45, 1.8, 8, 'Bullish')
        """, (date_str,))
    conn.commit()
    conn.close()

    # Limit to 5
    res = client.get("/api/breadth-history?limit=5")
    assert res.status_code == 200
    data = res.get_json()
    assert "history" in data
    history = data["history"]
    assert len(history) == 5
    # Order should be descending by date
    assert history[0]["date"] == "2026-06-15"
    assert history[4]["date"] == "2026-06-11"

    # Default limit is 30, which should return all 15 we inserted
    res_all = client.get("/api/breadth-history")
    assert res_all.status_code == 200
    data_all = res_all.get_json()
    assert "history" in data_all
    history_all = data_all["history"]
    assert len(history_all) == 15


