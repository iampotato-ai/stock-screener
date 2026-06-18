import pytest
import sqlite3
import json
import sys
import os

# Ensure the root folder is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app

@pytest.fixture(autouse=True)
def use_test_db(monkeypatch, tmp_path):
    db_file = str(tmp_path / "test_scan_history.db")
    orig_connect = sqlite3.connect

    def mock_connect(database, *args, **kwargs):
        if database == "scan_history.db":
            return orig_connect(db_file, *args, **kwargs)
        return orig_connect(database, *args, **kwargs)

    monkeypatch.setattr("sqlite3.connect", mock_connect)

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
        CREATE TABLE IF NOT EXISTS scan_price_log (
            date TEXT,
            ticker TEXT,
            close REAL,
            swingband TEXT,
            setupLabel TEXT,
            PRIMARY KEY(date, ticker)
        )
    ''')
    conn.commit()
    conn.close()

    # Initialize app with test database
    app = create_app()
    app.config['DATABASE'] = db_file
    with app.app_context():
        from app.database import init_db_standalone
        init_db_standalone(db_file)

    yield db_file

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_swing_trade_lifecycle_smoke(client):
    # 1. Save a scan snapshot
    snapshot_payload = {
        "items": [
            {"ticker": "WELCORP", "close": 100.0, "swingband": "strong", "setupLabel": "Breakout Ready"},
            {"ticker": "TCS", "close": 3500.0, "swingband": "elite", "setupLabel": "Bullish Continuation"}
        ]
    }
    res_snap = client.post("/api/save_snapshot", json=snapshot_payload)
    assert res_snap.status_code == 200
    assert res_snap.get_json()["success"] is True
    assert res_snap.get_json()["saved_count"] == 2
    
    # 2. Add journal entry for one of the snapshot candidates
    journal_payload = {
        "id": "trade-smoke-1",
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
    res_journal = client.post("/api/journal", json=journal_payload)
    assert res_journal.status_code == 200
    
    # 3. Read back stats summary for the backtested ticker
    res_summary = client.get("/api/backtest-summary?ticker=WELCORP")
    assert res_summary.status_code == 200
    summary = res_summary.get_json()
    assert summary["appearance_count"] == 1
    assert summary["first_close"] == 100.0
    
    # 4. Exit the trade
    exit_payload = {
        "id": "trade-smoke-1",
        "exitPrice": 115.0,
        "exitDate": "2026-06-02"
    }
    res_exit = client.put("/api/journal/trade-smoke-1", json=exit_payload)
    assert res_exit.status_code == 200
    
    # Read back and confirm P&L
    res_list = client.get("/api/journal")
    trades = res_list.get_json()
    assert len(trades) == 1
    assert trades[0]["pnl"] == 150.0  # (115 - 100) * 10
    assert trades[0]["rAchieved"] == 1.5  # 150 / 100
