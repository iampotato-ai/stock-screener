import os
import sys
import sqlite3
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# Setup base paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Create a temporary database for test isolation
db_fd, db_path = tempfile.mkstemp()

# Store original connect to redirect requests
orig_connect = getattr(sqlite3, "__original_connect__", sqlite3.connect)

# Import the module under test
from app.api.v1.legacy_routes import run_historical_backfill

@pytest.fixture(autouse=True)
def setup_teardown_db():
    """Initializes the database schema for ep_features and daily_bars before each test."""
    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS daily_bars")
    c.execute("DROP TABLE IF EXISTS ep_features")
    c.execute("DROP TABLE IF EXISTS ipo_listings")
    c.execute("DROP TABLE IF EXISTS ep_watchlist")
    c.execute("DROP TABLE IF EXISTS fundamentals")
    
    c.execute('''
        CREATE TABLE daily_bars (
            symbol TEXT, exchange TEXT, trade_date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
            prev_close REAL, gap_pct REAL, close_loc REAL, price_change_pct REAL, intraday_range_pct REAL,
            atr_14 REAL, rel_volume_20 REAL, rel_volume_50 REAL, delivery_qty REAL, delivery_pct REAL
        )
    ''')
    c.execute('''
        CREATE TABLE ep_features (
            symbol TEXT, exchange TEXT, feature_date TEXT, perf_3m REAL, perf_6m REAL, range_60d_pct REAL, avg_vol_rank REAL,
            neglect_score REAL, has_result INTEGER, revenue_growth REAL, profit_growth REAL, has_corp_event INTEGER,
            event_type TEXT, catalyst_score REAL, gap_pct REAL, rel_volume REAL, close_loc REAL, repricing_score REAL,
            ep_score REAL, ep_type TEXT, confidence TEXT, market_cap_cr REAL, avg_turnover_cr REAL, float_days REAL,
            price_change_pct REAL
        )
    ''')
    c.execute('''
        CREATE TABLE fundamentals (
            symbol TEXT, result_date TEXT, quarter TEXT, revenue_yoy_pct REAL, revenue_qoq_pct REAL,
            net_profit_yoy_pct REAL, surprise_type TEXT, consecutive_quarters_growth INTEGER
        )
    ''')
    conn.commit()
    conn.close()
    yield
    # Cleanup DB rows
    conn = orig_connect(db_path)
    conn.execute("DELETE FROM daily_bars")
    conn.execute("DELETE FROM ep_features")
    conn.commit()
    conn.close()

@pytest.fixture(scope="session", autouse=True)
def cleanup_temp_db():
    yield
    try:
        os.close(db_fd)
        os.unlink(db_path)
    except Exception:
        pass

@patch("app.api.v1.legacy_routes.fetch_historical_prices")
def test_backfill_cache_hits(mock_fetch):
    """Test that run_historical_backfill uses local daily_bars cache and skips network fetching."""
    # Seed 60 bars in database for MOCKSTK
    conn = orig_connect(db_path)
    c = conn.cursor()
    
    # Let's seed 60 bars (need >= 50 for cache hits)
    import datetime
    base_date = datetime.date(2026, 1, 1)
    for i in range(60):
        dt_str = (base_date + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        c.execute('''
            INSERT INTO daily_bars (symbol, exchange, trade_date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("MOCKSTK", "NSE", dt_str, 100.0, 105.0, 99.0, 104.0, 10000.0))
    conn.commit()
    conn.close()

    # Trigger backfill for MOCKSTK
    run_historical_backfill(symbols=["MOCKSTK"], start_date="2026-01-01", end_date="2026-03-01")

    # Assert that fetch_historical_prices was NEVER called (since it hit the local database cache)
    assert mock_fetch.call_count == 0

@patch("app.api.v1.legacy_routes.fetch_historical_prices")
def test_backfill_cache_miss_falls_back_to_yfinance(mock_fetch):
    """Test that run_historical_backfill falls back to Yahoo Finance when the symbol has no cache."""
    mock_fetch.return_value = [
        {"date": "2026-06-01", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1000.0}
    ]

    # Trigger backfill for a symbol with zero local bars
    run_historical_backfill(symbols=["FRESHSTK"], start_date="2026-06-01", end_date="2026-06-02")

    # Assert that fetch_historical_prices was called to fetch the history
    assert mock_fetch.call_count >= 1
    assert mock_fetch.call_args[0][0] == "FRESHSTK"

def test_cli_argument_parsing():
    """Test that the run_universe_backfill CLI script runs argument parsing correctly."""
    from scripts.run_universe_backfill import main
    # Mock sys.argv to test parse_args
    with patch("sys.argv", ["run_universe_backfill.py", "--symbols", "MOCKSTK", "--start-date", "2026-01-01"]):
        with patch("app.api.v1.legacy_routes.run_historical_backfill") as mock_backfill:
            main()
            assert mock_backfill.call_count == 1
            assert mock_backfill.call_args[1]["symbols"] == ["MOCKSTK"]
            assert mock_backfill.call_args[1]["start_date"] == "2026-01-01"
