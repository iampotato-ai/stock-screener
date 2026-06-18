"""
Database helper functions for the stock screener application.
This module provides a clean data access layer for all database operations.
"""
import sqlite3
import os
from contextlib import contextmanager
from flask import current_app, g
import logging

logger = logging.getLogger(__name__)

# Module-level variable to store the database path for standalone usage
_DATABASE_PATH = None

def get_db():
    """Get a database connection."""
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def _get_connection():
    """Get a database connection, returning (connection, should_close).
    If in Flask context and a connection exists in g, use it and don't close.
    Otherwise, create a new connection that the caller must close.
    """
    global _DATABASE_PATH
    try:
        from flask import g as flask_g, has_app_context
        if has_app_context() and hasattr(flask_g, 'db'):
            return flask_g.db, False
    except Exception:
        pass

    # If we are here, we are not in Flask context or g.db doesn't exist
    if _DATABASE_PATH is None:
        # Try to get the database path from current_app if available
        try:
            from flask import current_app
            _DATABASE_PATH = current_app.config['DATABASE']
        except Exception:
            raise RuntimeError(
                "Database path not initialized. Call init_db_app() or init_db_standalone() first."
            )

    conn = sqlite3.connect(_DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn, True


def init_db_app():
    """Initialize the database application context version."""
    global _DATABASE_PATH
    _DATABASE_PATH = current_app.config['DATABASE']
    db = get_db()
    _create_tables(db)
    db.commit()
    logger.info("Database initialized with app context")


def init_db_standalone(db_path):
    """Initialize the database standalone version (for scripts)."""
    global _DATABASE_PATH
    _DATABASE_PATH = db_path
    with get_db_connection(db_path) as conn:
        _create_tables(conn)
        conn.commit()
    logger.info("Database initialized standalone")


def _create_tables(conn):
    """Create all database tables."""
    c = conn.cursor()

    # Scan history tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS scan_history (
            date TEXT,
            ticker TEXT,
            UNIQUE(date, ticker)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS scan_price_log (
            date TEXT,
            ticker TEXT,
            close REAL,
            swingband TEXT,
            setupLabel TEXT,
            PRIMARY KEY (date, ticker)
        )
    ''')

    # Check if table breadth_history exists and what its PK is
    c.execute("PRAGMA table_info(breadth_history)")
    columns = c.fetchall()

    needs_recreate = False
    if columns:
        pk_count = sum(1 for col in columns if col[5] > 0)
        if pk_count > 1:
            needs_recreate = True

    if needs_recreate:
        logger.info("Migrating breadth_history to unique date primary key...")
        c.execute("SELECT * FROM breadth_history ORDER BY date ASC, time ASC")
        all_rows = c.fetchall()

        unique_date_rows = {}
        for row in all_rows:
            date_val = row[0]
            unique_date_rows[date_val] = row

        c.execute("DROP TABLE breadth_history")
        c.execute('''
            CREATE TABLE breadth_history (
                date TEXT PRIMARY KEY,
                time TEXT,
                advances INTEGER,
                declines INTEGER,
                unchanged INTEGER,
                pct_sma21 REAL,
                pct_sma50 REAL,
                pct_52high REAL,
                avg_recommend REAL,
                regime_score INTEGER,
                regime_band TEXT
            )
        ''')

        for row in unique_date_rows.values():
            c.execute(
                "INSERT INTO breadth_history VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                row
            )
    else:
        c.execute('''
            CREATE TABLE IF NOT EXISTS breadth_history (
                date TEXT PRIMARY KEY,
                time TEXT,
                advances INTEGER,
                declines INTEGER,
                unchanged INTEGER,
                pct_sma21 REAL,
                pct_sma50 REAL,
                pct_52high REAL,
                avg_recommend REAL,
                regime_score INTEGER,
                regime_band TEXT
            )
        ''')
    # Enable foreign keys
    c.execute("PRAGMA foreign_keys = ON;")

    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlist_sections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        )
    ''')
    try:
        c.execute("ALTER TABLE watchlist_sections ADD COLUMN position INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # position column already exists
    c.execute('''
        CREATE TABLE IF NOT EXISTS watchlist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            UNIQUE(section_id, ticker),
            FOREIGN KEY(section_id) REFERENCES watchlist_sections(id) ON DELETE CASCADE
        )
    ''')
    try:
        c.execute("ALTER TABLE watchlist_items ADD COLUMN position INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # position column already exists
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_journal (
            id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            setupLabel TEXT NOT NULL,
            swingband TEXT NOT NULL,
            entry REAL NOT NULL,
            stop REAL NOT NULL,
            target1 REAL NOT NULL,
            target2 REAL NOT NULL,
            target3 REAL NOT NULL,
            riskAmount REAL NOT NULL,
            qty INTEGER NOT NULL,
            status TEXT NOT NULL,
            exitPrice REAL,
            exitDate TEXT,
            pnl REAL,
            rAchieved REAL,
            notes TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS kronos_forecasts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            pred_len    INTEGER NOT NULL,
            forecast_json TEXT NOT NULL,
            last_close  REAL NOT NULL,
            model_type  TEXT NOT NULL DEFAULT 'kronos'
        )
    ''')
    # Safe migration: add model_type column if upgrading from an older schema
    try:
        c.execute("ALTER TABLE kronos_forecasts ADD COLUMN model_type TEXT NOT NULL DEFAULT 'kronos'")
        # Backfill any existing rows that have NULL model_type (from pre-migration rows)
        c.execute("UPDATE kronos_forecasts SET model_type = 'kronos' WHERE model_type IS NULL")
        logger.info("[DB Migration] Added model_type column to kronos_forecasts")
    except Exception:
        pass  # Column already exists — safe to ignore

    c.execute('''
        CREATE TABLE IF NOT EXISTS rrg_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            week        TEXT NOT NULL,
            sector      TEXT NOT NULL,
            jdk_rs      REAL NOT NULL,
            jdk_rs_momentum REAL NOT NULL,
            score       INTEGER,
            quadrant    TEXT,
            snapped_at  TEXT NOT NULL,
            UNIQUE(week, sector)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS pattern_cache (
            ticker TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            pattern_name TEXT,
            pattern_grade TEXT,
            pattern_desc TEXT,
            candlestick_json TEXT,
            pattern_bias REAL DEFAULT 0.0,
            max_down_vol_10 REAL,
            volume_sma_50 REAL
        )
    ''')
    try:
        c.execute("ALTER TABLE pattern_cache ADD COLUMN candlestick_json TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE pattern_cache ADD COLUMN pattern_bias REAL DEFAULT 0.0")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE pattern_cache ADD COLUMN max_down_vol_10 REAL")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE pattern_cache ADD COLUMN volume_sma_50 REAL")
    except Exception:
        pass

    # ---------- pattern_signals (Phase 2 addition) ----------
    c.execute('''
        CREATE TABLE IF NOT EXISTS pattern_signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT NOT NULL,
            timeframe   TEXT NOT NULL DEFAULT 'D',
            signal_type TEXT NOT NULL,           -- 'candle' | 'chart'
            pattern     TEXT NOT NULL,
            direction   INTEGER NOT NULL,        -- 100 bullish, -100 bearish
            confidence  REAL,                    -- 0.0-1.0 (chart patterns only)
            description TEXT,
            detected_at TEXT NOT NULL,
            bar_date    TEXT                     -- date of the last bar in the signal
        )
    ''')
    # Index for fast per-ticker lookups
    c.execute('CREATE INDEX IF NOT EXISTS idx_pattern_signals_ticker ON pattern_signals (ticker, detected_at DESC)')
    try:
        c.execute("ALTER TABLE pattern_signals ADD COLUMN bar_date TEXT")
    except Exception:
        pass  # already exists

    # ---------- IPO / SME Momentum Tab Tables ----------
    c.execute('''
        CREATE TABLE IF NOT EXISTS ipo_listings (
            ticker          TEXT PRIMARY KEY,
            company_name    TEXT NOT NULL,
            listing_date    TEXT NOT NULL,
            issue_price     REAL,
            listing_open    REAL,
            listing_close   REAL,
            exchange        TEXT DEFAULT 'NSE',
            sector          TEXT,
            issue_size_cr   REAL,
            lot_size        INTEGER,
            gmp_at_listing  REAL,
            added_at        TEXT DEFAULT (datetime('now'))
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ipo_listing_date ON ipo_listings(listing_date DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ipo_exchange ON ipo_listings(exchange)')

    c.execute('''
        CREATE TABLE IF NOT EXISTS ipo_metrics_cache (
            ticker                  TEXT PRIMARY KEY,
            company_name            TEXT NOT NULL,
            listing_date            TEXT NOT NULL,
            exchange                TEXT NOT NULL,
            sector                  TEXT,
            issue_price             REAL,
            listing_gain_pct        REAL,
            current_vs_issue_pct    REAL,
            current_vs_listing_pct  REAL,
            days_since_listing      INTEGER,
            rvol_ratio              REAL,
            above_listing_high      INTEGER,
            drawdown_from_ath       REAL,
            swing_score             INTEGER,
            pattern_name            TEXT,
            momentum_phase          TEXT,
            current_price           REAL,
            volume                  REAL,
            change_pct              REAL,
            day_low                 REAL,
            day_high                REAL,
            is_blue_bar             INTEGER DEFAULT 0,
            is_green_bar            INTEGER DEFAULT 0,
            is_orange_bar           INTEGER DEFAULT 0,
            cached_at               TEXT NOT NULL
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ipo_metrics_phase ON ipo_metrics_cache(momentum_phase)')

    # Run migrations for volume, change_pct, and day range columns
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN volume REAL")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN change_pct REAL")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN day_low REAL")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN day_high REAL")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN is_blue_bar INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN is_green_bar INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE ipo_metrics_cache ADD COLUMN is_orange_bar INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # ---------- Episodic Pivot (EP) Tables ----------
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_bars (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            trade_date      TEXT NOT NULL,
            open            REAL,
            high            REAL,
            low             REAL,
            close           REAL,
            volume          INTEGER,
            delivery_qty    INTEGER,
            delivery_pct    REAL,
            turnover        REAL,
            prev_close      REAL,
            gap_pct         REAL,
            close_loc       REAL,
            atr_14          REAL,
            rel_volume_20   REAL,
            rel_volume_50   REAL,
            price_change_pct REAL,
            intraday_range_pct REAL,
            UNIQUE (symbol, exchange, trade_date)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_daily_bars_symbol_date ON daily_bars (symbol, trade_date DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_daily_bars_date ON daily_bars (trade_date DESC)')

    c.execute('''
        CREATE TABLE IF NOT EXISTS fundamentals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            result_date     TEXT NOT NULL,
            quarter         TEXT,
            revenue         REAL,
            revenue_yoy_pct REAL,
            revenue_qoq_pct REAL,
            net_profit      REAL,
            net_profit_yoy_pct REAL,
            ebitda          REAL,
            ebitda_margin   REAL,
            eps             REAL,
            eps_yoy_pct     REAL,
            guidance_text   TEXT,
            surprise_type   TEXT,
            consecutive_quarters_growth INTEGER,
            source          TEXT,
            UNIQUE (symbol, exchange, quarter)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS corporate_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            event_date      TEXT NOT NULL,
            event_type      TEXT,
            headline        TEXT,
            sentiment       INTEGER,
            catalyst_score  REAL,
            source          TEXT,
            raw_url         TEXT
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_corp_events_symbol_date ON corporate_events (symbol, event_date DESC)')

    c.execute('''
        CREATE TABLE IF NOT EXISTS ep_features (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            feature_date    TEXT NOT NULL,
            perf_3m         REAL,
            perf_6m         REAL,
            range_60d_pct   REAL,
            avg_vol_rank    REAL,
            neglect_score   REAL,
            has_result      INTEGER DEFAULT 0,
            revenue_growth  REAL,
            profit_growth   REAL,
            has_corp_event  INTEGER DEFAULT 0,
            event_type      TEXT,
            catalyst_score  REAL,
            gap_pct         REAL,
            rel_volume      REAL,
            close_loc       REAL,
            repricing_score REAL,
            ep_score        REAL,
            ep_type         TEXT,
            confidence      TEXT,
            market_cap_cr   REAL,
            avg_turnover_cr REAL,
            float_days      REAL,
            UNIQUE (symbol, exchange, feature_date)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ep_features_date ON ep_features (feature_date DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ep_features_score ON ep_features (feature_date DESC, ep_score DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_ep_features_symbol_date ON ep_features (symbol, feature_date DESC)')

    c.execute('''
        CREATE TABLE IF NOT EXISTS ep_watchlist (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            exchange        TEXT NOT NULL,
            catalyst_date   TEXT NOT NULL,
            ep_type         TEXT NOT NULL,
            status          TEXT DEFAULT 'ACTIVE',
            trigger_type    TEXT,
            entry_price     REAL,
            stop_price      REAL,
            target_price    REAL,
            entry_date      TEXT,
            days_on_watch   INTEGER DEFAULT 0,
            notes           TEXT,
            ep_score        REAL,
            catalyst_close  REAL,
            last_incremented_date TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    ''')
    try:
        c.execute("ALTER TABLE ep_watchlist ADD COLUMN catalyst_close REAL")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE ep_watchlist ADD COLUMN last_incremented_date TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE ep_features ADD COLUMN price_change_pct REAL")
    except Exception:
        pass
    try:
        c.execute("""
            UPDATE ep_features
            SET price_change_pct = (
                SELECT db.price_change_pct
                FROM daily_bars db
                WHERE db.symbol = ep_features.symbol
                  AND db.trade_date = ep_features.feature_date
            )
            WHERE price_change_pct IS NULL
              AND EXISTS (
                SELECT 1
                FROM daily_bars db
                WHERE db.symbol = ep_features.symbol
                  AND db.trade_date = ep_features.feature_date
              )
        """)
    except Exception:
        pass

    c.execute('''
        CREATE TABLE IF NOT EXISTS sugar_babies (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT UNIQUE NOT NULL,
            exchange        TEXT NOT NULL,
            added_date      TEXT,
            avg_burst_pct   REAL,
            avg_burst_days  REAL,
            episode_count   INTEGER,
            notes           TEXT,
            is_active       INTEGER DEFAULT 1
        )
    ''')
    # Alter corporate_events for NLP Enhancement
    nlp_columns = [
        ("nlp_sentiment_score", "REAL"),
        ("nlp_category", "TEXT"),
        ("summary", "TEXT"),
        ("impact_magnitude", "REAL")
    ]
    for column_name, column_type in nlp_columns:
        try:
            c.execute(f"ALTER TABLE corporate_events ADD COLUMN {column_name} {column_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists


def close_db(e=None):
    """Close the database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Initialize the database with all required tables."""
    db = get_db()

    # Read schema from schema.sql or create tables here
    # This would typically be handled by Flask-Migrate or similar
    # For now, we'll assume tables are created elsewhere
    logger.info("Database initialized")


@contextmanager
def get_db_connection(db_path=None):
    """Context manager for database connections, inside or outside Flask context."""
    if db_path is None:
        from flask import current_app
        db_path = current_app.config['DATABASE']
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def execute_query(query, params=(), commit=False):
    """Execute a query and return results."""
    conn, should_close = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if commit:
            conn.commit()
            return cursor.lastrowid
        else:
            return cursor.fetchall()
    finally:
        if should_close:
            conn.close()


def fetch_one(query, params=()):
    """Fetch a single row."""
    conn, should_close = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()
    finally:
        if should_close:
            conn.close()


def fetch_all(query, params=()):
    """Fetch all rows."""
    conn, should_close = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        if should_close:
            conn.close()


# ========== SCREENER RELATED FUNCTIONS ==========

def get_latest_scan_results(limit=50):
    """Get latest scan results with optional limit."""
    query = '''
        SELECT s.ticker, s.date, s.close, s.swingband, s.setupLabel
        FROM scan_price_log s
        INNER JOIN (
            SELECT ticker, MAX(date) as max_date
            FROM scan_history
            GROUP BY ticker
        ) latest ON s.ticker = latest.ticker AND s.date = latest.max_date
        ORDER BY s.date DESC
        LIMIT ?
    '''
    return fetch_all(query, (limit,))


def get_stock_details(ticker):
    """Get detailed stock information."""
    # Clean ticker (remove NSE:/BO: prefixes)
    clean_ticker = ticker.replace('NSE:', '').replace('BO:', '')

    # Get latest price data
    price_query = '''
        SELECT date, close, swingband, setupLabel
        FROM scan_price_log
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT 1
    '''
    price_data = fetch_one(price_query, (clean_ticker,))

    # Get fundamentals
    fundamentals_query = '''
        SELECT *
        FROM fundamentals
        WHERE symbol = ?
        ORDER BY result_date DESC
        LIMIT 1
    '''
    fundamentals_data = fetch_one(fundamentals_query, (clean_ticker,))

    # Get EP features
    ep_query = '''
        SELECT *
        FROM ep_features
        WHERE symbol = ?
        ORDER BY feature_date DESC
        LIMIT 1
    '''
    ep_data = fetch_one(ep_query, (clean_ticker,))

    result = {
        'ticker': clean_ticker,
        'price_data': dict(price_data) if price_data else None,
        'fundamentals': dict(fundamentals_data) if fundamentals_data else None,
        'ep_features': dict(ep_data) if ep_data else None
    }

    return result


def refresh_screener_data():
    """Trigger background refresh of screener data."""
    # This would typically trigger a background task
    # For now, we'll just log that refresh was requested
    logger.info("Screener data refresh requested")
    return True


# ========== IPO RELATED FUNCTIONS ==========

def get_ipo_listings(exchange=None, limit=50):
    """Get IPO listings."""
    query = '''
        SELECT il.*, imc.momentum_phase, imc.price_change_pct
        FROM ipo_listings il
        LEFT JOIN ipo_metrics_cache imc ON il.ticker = imc.ticker
    '''
    params = ()

    if exchange:
        query += ' WHERE il.exchange = ?'
        params = (exchange,)

    query += ' ORDER BY il.listing_date DESC LIMIT ?'
    params = params + (limit,) if params else (limit,)

    return fetch_all(query, params)


def get_ipo_details(ticker):
    """Get detailed IPO information."""
    query = '''
        SELECT il.*, imc.*
        FROM ipo_listings il
        LEFT JOIN ipo_metrics_cache imc ON il.ticker = imc.ticker
        WHERE il.ticker = ?
    '''
    return fetch_one(query, (ticker,))


# ========== WATCHLIST RELATED FUNCTIONS ==========

def get_watchlist_sections():
    """Get all watchlist sections."""
    query = '''
        SELECT ws.id, ws.name, COUNT(wi.id) as item_count
        FROM watchlist_sections ws
        LEFT JOIN watchlist_items wi ON ws.id = wi.section_id
        GROUP BY ws.id, ws.name
        ORDER BY ws.position ASC, ws.id ASC
    '''
    return fetch_all(query)


def get_watchlist_items(section_id):
    """Get items in a watchlist section."""
    query = '''
        SELECT wi.id, wi.ticker, wi.position
        FROM watchlist_items wi
        WHERE wi.section_id = ?
        ORDER BY wi.position ASC, wi.id ASC
    '''
    return fetch_all(query, (section_id,))


def add_watchlist_section(name):
    """Add a new watchlist section."""
    import uuid
    section_id = str(uuid.uuid4())
    query = '''
        INSERT OR IGNORE INTO watchlist_sections (id, name)
        VALUES (?, ?)
    '''
    execute_query(query, (section_id, name), commit=True)
    return section_id


def delete_watchlist_section(section_id):
    """Delete a watchlist section."""
    query = 'DELETE FROM watchlist_sections WHERE id = ?'
    return execute_query(query, (section_id,), commit=True)


def add_watchlist_item(section_id, ticker):
    """Add item to watchlist section."""
    # Get max position
    max_pos_query = '''
        SELECT COALESCE(MAX(position), 0) FROM watchlist_items WHERE section_id = ?
    '''
    max_pos = fetch_one(max_pos_query, (section_id,))[0]

    query = '''
        INSERT OR IGNORE INTO watchlist_items (section_id, ticker, position)
        VALUES (?, ?, ?)
    '''
    return execute_query(query, (section_id, ticker.upper(), max_pos + 1), commit=True)


def remove_watchlist_item(section_id, ticker):
    """Remove item from watchlist section."""
    query = '''
        DELETE FROM watchlist_items
        WHERE section_id = ? AND ticker = ?
    '''
    return execute_query(query, (section_id, ticker.upper()), commit=True)


def get_watchlist():
    """Get watchlist with sections and items for API response."""
    sections = get_watchlist_sections()
    result = []
    for section in sections:
        section_id = section['id']
        items = get_watchlist_items(section_id)
        tickers = [item['ticker'] for item in items]
        result.append({
            "id": section_id,
            "name": section['name'],
            "stocks": tickers
        })
    return result


# ========== JOURNAL RELATED FUNCTIONS ==========

def get_journal_entries(limit=50):
    """Get journal entries."""
    query = '''
        SELECT * FROM trade_journal
        ORDER BY date DESC, id DESC
        LIMIT ?
    '''
    return fetch_all(query, (limit,))


def get_journal_entry(entry_id):
    """Get specific journal entry."""
    query = 'SELECT * FROM trade_journal WHERE id = ?'
    return fetch_one(query, (entry_id,))


def create_journal_entry(entry_data):
    """Create a new journal entry."""
    query = '''
        INSERT OR IGNORE INTO trade_journal (
            id, ticker, name, date, setupLabel, swingband, entry, stop,
            target1, target2, target3, riskAmount, qty, status, exitPrice,
            exitDate, pnl, rAchieved, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    params = (
        entry_data.get('id'),
        entry_data.get('ticker'),
        entry_data.get('name'),
        entry_data.get('date'),
        entry_data.get('setupLabel'),
        entry_data.get('swingband'),
        entry_data.get('entry'),
        entry_data.get('stop'),
        entry_data.get('target1'),
        entry_data.get('target2'),
        entry_data.get('target3'),
        entry_data.get('riskAmount'),
        entry_data.get('qty'),
        entry_data.get('status'),
        entry_data.get('exitPrice'),
        entry_data.get('exitDate'),
        entry_data.get('pnl'),
        entry_data.get('rAchieved'),
        entry_data.get('notes')
    )
    return execute_query(query, params, commit=True)


def update_journal_entry(entry_id, updates):
    """Update journal entry."""
    if not updates:
        return False

    fields = ', '.join([f'{k} = ?' for k in updates.keys()])
    query = f'UPDATE trade_journal SET {fields} WHERE id = ?'
    params = list(updates.values()) + [entry_id]

    return execute_query(query, params, commit=True)


def delete_journal_entry(entry_id):
    """Delete journal entry."""
    query = 'DELETE FROM trade_journal WHERE id = ?'
    return execute_query(query, (entry_id,), commit=True)


# ========== MARKET BREADTH FUNCTIONS ==========

def get_market_breadth():
    """Get latest market breadth data."""
    query = '''
        SELECT * FROM breadth_history
        ORDER BY date DESC, time DESC
        LIMIT 1
    '''
    return fetch_one(query)


# ========== NEWS/CORPORATE EVENTS FUNCTIONS ==========

def get_corporate_events(limit=50):
    """Get corporate events."""
    query = '''
        SELECT * FROM corporate_events
        ORDER BY event_date DESC
        LIMIT ?
    '''
    return fetch_all(query, (limit,))


# ========== EP (EPISODIC PIVOT) FUNCTIONS ==========

def get_ep_watchlist(status=None):
    """Get EP watchlist items."""
    query = '''
        SELECT ew.*, ef.ep_score, ef.confidence
        FROM ep_watchlist ew
        LEFT JOIN ep_features ef ON ew.symbol = ef.symbol AND ew.catalyst_date = ef.feature_date
    '''
    params = ()

    if status:
        query += ' WHERE ew.status = ?'
        params = (status,)

    query += ' ORDER BY ew.updated_at DESC'

    return fetch_all(query, params)


def update_ep_watchlist(symbol, update_data):
    """Update EP watchlist item."""
    if not update_data:
        return False

    fields = ', '.join([f'{k} = ?' for k in update_data.keys()])
    query = f'UPDATE ep_watchlist SET {fields}, updated_at = datetime(\'now\') WHERE symbol = ?'
    params = list(update_data.values()) + [symbol]

    return execute_query(query, params, commit=True)


# ========== SUGAR BABIES FUNCTIONS ==========

def get_sugar_babies():
    """Get Sugar Babies rankings."""
    query = '''
        SELECT sb.*, COUNT(ef.id) as episode_count
        FROM sugar_babies sb
        LEFT JOIN ep_features ef ON sb.symbol = ef.symbol AND ef.ep_score >= 0.55
        GROUP BY sb.symbol
        ORDER BY sb.avg_burst_pct DESC
    '''
    return fetch_all(query)


# ========== UTILITY FUNCTIONS ==========

def table_exists(table_name):
    """Check if a table exists."""
    query = '''
        SELECT name FROM sqlite_master
        WHERE type='table' AND name=?
    '''
    result = fetch_one(query, (table_name,))
    return result is not None


def get_table_info(table_name):
    """Get table schema information."""
    query = f'PRAGMA table_info({table_name})'
    return fetch_all(query)