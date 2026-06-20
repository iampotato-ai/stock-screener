import pytest
import sqlite3
import json
import sys
import os
import importlib.util

# Ensure the root folder is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Global variable to hold the loaded monolith app
app = None
db_file = None

@pytest.fixture(autouse=True)
def use_test_db(monkeypatch, tmp_path):
    global app, db_file
    db_file = str(tmp_path / "test_scan_history.db")
    
    # Configure environment BEFORE loading app.py
    monkeypatch.setenv("DATABASE", db_file)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + db_file)

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

    # Load monolithic app from app.py inside the fixture context
    if app is None:
        spec = importlib.util.spec_from_file_location("app_monolith", os.path.abspath(os.path.join(os.path.dirname(__file__), "../app.py")))
        app_monolith = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app_monolith)
        app = app_monolith.app

    # Ensure app configurations are set explicitly
    app.config['DATABASE'] = db_file
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_file

    with app.app_context():
        from app.database import init_db_standalone
        init_db_standalone(db_file)

    yield db_file

@pytest.fixture
def client(use_test_db):
    app.config['TESTING'] = True
    app.config['DATABASE'] = use_test_db
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + use_test_db
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
    assert res_journal.status_code in (200, 201)
    
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
