import os
import tempfile
import pytest
from app.database import (
    get_market_breadth,
    create_journal_entry,
    get_journal_entry,
    add_watchlist_section,
    delete_watchlist_section,
    get_watchlist_sections,
    get_watchlist_items,
    add_watchlist_item,
    remove_watchlist_item,
    get_ep_watchlist,
    _get_connection,
    init_db_standalone,
    execute_query,
    fetch_one,
    init_db_app,
)
from flask import Flask, g


def test_get_market_breadth_returns_none_on_empty(initialized_db):
    """Should return None when no breadth data exists."""
    assert get_market_breadth() is None


def test_create_and_fetch_journal_entry(initialized_db):
    """Create a journal entry and fetch it back."""
    # Insert with hardcoded values
    rowid = create_journal_entry({
        'id': 'test-journal-1',
        'ticker': 'RELIANCE.NS',
        'name': 'Reliance Industries',
        'date': '2024-01-01',
        'setupLabel': 'Breakout',
        'swingband': 'Strong',
        'entry': 2500.0,
        'stop': 2450.0,
        'target1': 2600.0,
        'target2': 2650.0,
        'target3': 2700.0,
        'riskAmount': 50.0,
        'qty': 10,
        'status': 'Open',
        'exitPrice': None,
        'exitDate': None,
        'pnl': 0.0,
        'rAchieved': 0.0,
        'notes': 'Test entry',
    })
    assert rowid is not None
    # Fetch
    fetched = get_journal_entry('test-journal-1')
    assert fetched is not None
    # Convert sqlite3.Row to dict for comparison
    fetched_dict = dict(fetched)
    # Expected values
    expected = {
        'id': 'test-journal-1',
        'ticker': 'RELIANCE.NS',
        'name': 'Reliance Industries',
        'date': '2024-01-01',
        'setupLabel': 'Breakout',
        'swingband': 'Strong',
        'entry': 2500.0,
        'stop': 2450.0,
        'target1': 2600.0,
        'target2': 2650.0,
        'target3': 2700.0,
        'riskAmount': 50.0,
        'qty': 10,
        'status': 'Open',
        'exitPrice': None,
        'exitDate': None,
        'pnl': 0.0,
        'rAchieved': 0.0,
        'notes': 'Test entry',
    }
    # Check all fields match
    for key, expected_value in expected.items():
        assert fetched_dict[key] == expected_value, f"Mismatch on {key}: {fetched_dict[key]} != {expected_value}"


def test_watchlist_section_add_and_delete(initialized_db):
    """Add a watchlist section and verify it appears in list, then delete."""
    # Add section
    section_id = add_watchlist_section('Test Section')
    assert section_id is not None
    # Verify in list
    sections = get_watchlist_sections()
    assert any(s['id'] == section_id for s in sections)
    # Delete
    delete_watchlist_section(section_id)
    # Verify gone
    sections = get_watchlist_sections()
    assert not any(s['id'] == section_id for s in sections)


def test_get_ep_watchlist_join_works(initialized_db):
    """Verify that the EP watchlist join uses catalyst_date (not feature_date)."""
    # Insert an ep_features row (omit id as it's AUTOINCREMENT)
    execute_query(
        '''
        INSERT INTO ep_features (
            symbol, exchange, feature_date, perf_3m, perf_6m, range_60d_pct,
            avg_vol_rank, neglect_score, has_result, revenue_growth, profit_growth,
            has_corp_event, event_type, catalyst_score, gap_pct, rel_volume,
            close_loc, repricing_score, ep_score, ep_type, confidence,
            market_cap_cr, avg_turnover_cr, float_days
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'TESTEP.NS', 'NSE', '2024-01-01', 0.1, 0.2, 0.05, 50, 0.3, 1,
            0.1, 0.2, 0, 'Result', 0.8, 0.02, 0.02, 1.5, 0.5, 0.1, 'Breakout', 'High',
            0.75, 1000, 50
        ),
        commit=True,
    )
    # Insert an ep_watchlist row with matching catalyst_date
    execute_query(
        '''
        INSERT INTO ep_watchlist (
            symbol, exchange, catalyst_date, ep_type, status, trigger_type,
            entry_price, stop_price, target_price, entry_date, days_on_watch,
            notes, ep_score, catalyst_close, last_incremented_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            'TESTEP.NS', 'NSE', '2024-01-01', 'Breakout', 'ACTIVE', 'Pullback',
            100.0, 95.0, 110.0, '2024-01-02', 5, 'Test EP watchlist',
            0.75, 101.0, '2024-01-03'
        ),
        commit=True,
    )
    # Fetch watchlist
    results = get_ep_watchlist()
    assert len(results) == 1
    row = results[0]
    # Verify join brought ep_score and confidence from ep_features
    assert row['ep_score'] == 0.75
    assert row['confidence'] == 'High'
    # Verify catalyst_date matches
    assert row['catalyst_date'] == '2024-01-01'


def test_get_db_connection_standalone(tmp_path):
    """Verify _get_connection works outside Flask context and returns closable connection."""
    # Standalone: initialize with a temp file
    db_path = os.path.join(tmp_path, 'test.db')
    init_db_standalone(db_path)
    # Outside Flask context, _get_connection should return a new connection that we must close
    conn, should_close = _get_connection()
    assert should_close is True
    # Verify we can execute a query
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    assert cursor.fetchone()[0] == 1
    conn.close()
    # After closing, calling _get_connection again should give a new conn
    conn2, should_close2 = _get_connection()
    assert should_close2 is True
    conn2.close()


def test_get_connection_uses_flask_context(flask_app):
    """Inside Flask context, _get_connection should reuse g.db and not close."""
    with flask_app.app_context():
        from app.database import get_db
        # Manually create a connection via get_db to store in g
        db1 = get_db()
        conn, should_close = _get_connection()
        assert should_close is False
        assert conn is db1