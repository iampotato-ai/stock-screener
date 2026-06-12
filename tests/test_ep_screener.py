import pytest
import sqlite3
import json
import sys
import os
import tempfile
from unittest.mock import patch, MagicMock

# 1. Setup the test DB mock first, before app is imported
db_fd, db_path = tempfile.mkstemp()

orig_connect = sqlite3.connect
def mock_connect(database, *args, **kwargs):
    if database == "scan_history.db":
        return orig_connect(db_path, *args, **kwargs)
    return orig_connect(database, *args, **kwargs)

sqlite3.connect = mock_connect

# Now insert the root path and import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app
app.init_db()
from app import (
    app as flask_app,
    compute_neglect_score,
    compute_catalyst_score,
    compute_repricing_score,
    compute_ep_score,
    assign_ep_type,
    assign_confidence,
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

def test_scoring_helpers():
    # 1. Test Neglect Score
    # Neglect calculation: n_perf_3m, n_perf_6m, n_range, n_vol_rank
    # perf_3m=0 (n_perf_3m=0.5), perf_6m=0 (n_perf_6m=0.5), range=20 (n_range=0.5), vol_rank=0.5 (n_vol_rank=0.5)
    # neglect = 0.35*0.5 + 0.25*0.5 + 0.20*0.5 + 0.20*0.5 = 0.50
    assert compute_neglect_score(0.0, 0.0, 20.0, 0.5) == 0.50
    # Test partial inputs (e.g. IPOs where some metrics are None)
    assert compute_neglect_score(0.0, None, None, None) == 0.50
    
    # 2. Test Catalyst Score
    # event_type = "BLOWOUT_EARNINGS" -> base 0.90
    # revenue_growth >= 100 (+0.10)
    # profit_growth >= 200 (+0.10)
    # consecutive_quarters >= 2 (+0.05)
    # market_cap_cr < 5000 (+0.05)
    # base + bonus = 0.90 + 0.30 = 1.20 -> capped at 1.0
    assert compute_catalyst_score("BLOWOUT_EARNINGS", 120, 250, 3, 3000) == 1.0
    
    # Event with negative base: GUIDANCE_CUT -> -0.80
    assert compute_catalyst_score("GUIDANCE_CUT", 0, 0) == -0.80
    
    # Event with normal beat: STRONG_BEAT -> base 0.70
    assert compute_catalyst_score("STRONG_BEAT", 50, 100, 0, 10000) == 0.80 # 0.70 + 0.05 (rev) + 0.05 (profit) = 0.80
    
    # 3. Test Repricing Score
    # gap_pct=10.0 (n_gap=0.5), rel_volume=5.5 (n_vol=4.5/9=0.5), close_loc=0.5 (n_close=0.5), price_change_pct=7.5 (n_strength=0.5)
    # repricing = 0.30*0.5 + 0.35*0.5 + 0.20*0.5 + 0.15*0.5 = 0.50
    assert compute_repricing_score(10.0, 5.5, 0.5, 7.5, 5.0) == 0.50

    # 4. Test EP Score
    # neglect_score = 0.50, catalyst_score = 0.80, repricing_score = 0.70, liquidity_ok = True
    # raw = 0.25*0.50 + 0.35*0.80 + 0.30*0.70 = 0.125 + 0.280 + 0.210 = 0.615
    assert compute_ep_score(0.50, 0.80, 0.70, True) == 0.615
    # liquidity_ok = False (-0.10 penalty) -> 0.515
    assert compute_ep_score(0.50, 0.80, 0.70, False) == 0.515

def test_assign_ep_type_and_confidence():
    # Test assign_ep_type
    assert assign_ep_type(0.80, "TURNAROUND", 6.0, 10.0) == "Turnaround EP"
    assert assign_ep_type(0.90, "BLOWOUT_EARNINGS", 6.0, 10.0, revenue_growth=120) == "Growth EP"
    assert assign_ep_type(0.60, "ABNORMAL_VOLUME", 6.0, 2.0) == "Volume EP"
    assert assign_ep_type(0.60, "THEME_CATALYST", 4.0, 3.0) == "Story EP"
    assert assign_ep_type(-0.80, "GUIDANCE_CUT", 3.0, -5.0) == "Short EP"
    assert assign_ep_type(0.50, "STRONG_BEAT", 3.0, 2.0, day1_messy=True) == "Delayed EP"
    
    # Test assign_confidence
    # ep_score >= 0.72, catalyst_score >= 0.70, repricing_score >= 0.60 -> HIGH
    assert assign_confidence(0.75, 0.50, 0.75, 0.65) == "HIGH"
    # ep_score >= 0.55 -> MEDIUM
    assert assign_confidence(0.60, 0.50, 0.50, 0.50) == "MEDIUM"
    # Otherwise -> LOW
    assert assign_confidence(0.50, 0.50, 0.50, 0.50) == "LOW"

def test_db_initialization():
    conn = orig_connect(db_path)
    c = conn.cursor()
    
    # Verify that the tables exist
    tables = ["daily_bars", "fundamentals", "corporate_events", "ep_features", "ep_watchlist", "sugar_babies"]
    for t in tables:
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,))
        assert c.fetchone() is not None, f"Table {t} was not created"
        
    conn.close()

@patch("requests.post")
@patch("app.fetch_historical_prices")
@patch("app.fetch_screener_fundamentals")
@patch("app.fetch_nse_announcements")
def test_refresh_ep_screener(mock_fetch_announcements, mock_fetch_fundamentals, mock_fetch_prices, mock_post):
    # Setup mock TradingView response
    mock_tv_response = MagicMock()
    mock_tv_response.json.return_value = {
        "data": [
            {
                "s": "NSE:MOCKSTOCK",
                "d": [
                    "MOCKSTOCK",
                    "Mock Stock description",
                    100.0,      # close
                    5.0,        # change
                    3000000.0,  # volume
                    10000000000.0, # market_cap_basic
                    100000.0,   # average_volume
                    "Technology Services" # sector
                ]
            }
        ]
    }
    mock_post.return_value = mock_tv_response
    
    # Setup mock history: 150 daily bars to calculate metrics
    mock_history = []
    import datetime
    base_date = datetime.date(2026, 6, 11)
    
    # Generate 149 standard bars
    for i in range(149):
        date_str = (base_date - datetime.timedelta(days=150-i)).strftime("%Y-%m-%d")
        if i < 50:
            c_price = 130.0
        elif i < 100:
            c_price = 115.0
        else:
            c_price = 100.0
        mock_history.append({
            "date": date_str,
            "open": c_price - 2.0,
            "high": c_price + 2.0,
            "low": c_price - 3.0,
            "close": c_price,
            "volume": 100000.0
        })
        
    # Generate breakout bar for the last day
    today_date_str = base_date.strftime("%Y-%m-%d")
    mock_history.append({
        "date": today_date_str,
        "open": 105.0,
        "high": 115.0,
        "low": 104.0,
        "close": 112.0,
        "volume": 3000000.0 # 6x relative volume
    })
    
    mock_fetch_prices.return_value = mock_history

    # Mock fundamentals fetch
    mock_fetch_fundamentals.return_value = [
        {"quarter": "Jun 2025", "date_key": "2025-06-30", "revenue": 100.0, "net_profit": 10.0, "eps": 1.0},
        {"quarter": "Sep 2025", "date_key": "2025-09-30", "revenue": 110.0, "net_profit": 12.0, "eps": 1.2},
        {"quarter": "Dec 2025", "date_key": "2025-12-30", "revenue": 120.0, "net_profit": 15.0, "eps": 1.5},
        {"quarter": "Mar 2026", "date_key": "2026-03-31", "revenue": 130.0, "net_profit": 18.0, "eps": 1.8},
        {"quarter": "Jun 2026", "date_key": "2026-06-30", "revenue": 260.0, "net_profit": 40.0, "eps": 4.0} # YoY rev +160%, YoY net profit +300%
    ]
    
    # Mock announcements fetch
    mock_fetch_announcements.return_value = [
        {
            "symbol": "MOCKSTOCK",
            "desc": "Capex expansion of manufacturing plant capacity",
            "attchmntText": "capex expansion plant",
            "an_dt": "2026-06-11 11:00:00",
            "sort_date": "2026-06-11 11:00:00",
            "seq_id": "999999",
            "attchmntFile": "http://example.com/capex.pdf"
        }
    ]
    
    # Clear database tables before run
    conn = orig_connect(db_path)
    c = conn.cursor()
    c.execute("DELETE FROM daily_bars")
    c.execute("DELETE FROM fundamentals")
    c.execute("DELETE FROM corporate_events")
    c.execute("DELETE FROM ep_features")
    c.execute("DELETE FROM ep_watchlist")
    conn.commit()
    conn.close()
    
    # Run refresh
    refresh_ep_screener()
    
    # Verify DB state
    conn = orig_connect(db_path)
    c = conn.cursor()
    
    # Check that daily_bars are populated
    c.execute("SELECT COUNT(*) FROM daily_bars WHERE symbol='MOCKSTOCK'")
    assert c.fetchone()[0] > 0

    # Check fundamentals table has entries
    c.execute("SELECT quarter, revenue, net_profit_yoy_pct, surprise_type FROM fundamentals WHERE symbol='MOCKSTOCK' ORDER BY result_date DESC")
    funds = c.fetchall()
    assert len(funds) == 5
    assert funds[0][0] == "Jun 2026"
    assert funds[0][1] == 260.0
    assert funds[0][2] == 300.0 # YoY net profit growth: (40 - 10)/10 * 100 = 300%
    assert funds[0][3] == "BLOWOUT_EARNINGS"

    # Check corporate_events table has the capex event
    c.execute("SELECT event_type, headline, catalyst_score FROM corporate_events WHERE symbol='MOCKSTOCK'")
    events = c.fetchall()
    assert len(events) == 1
    assert events[0][0] == "CAPEX_EXPANSION"
    assert "Capex expansion" in events[0][1]
    assert events[0][2] == 0.45
    
    # Check ep_features
    c.execute("""
        SELECT symbol, ep_score, ep_type, confidence, market_cap_cr,
               has_result, revenue_growth, profit_growth, has_corp_event, event_type, catalyst_score
        FROM ep_features WHERE symbol='MOCKSTOCK'
    """)
    feat = c.fetchone()
    assert feat is not None
    assert feat[0] == "MOCKSTOCK"
    assert feat[1] > 0.0  # ep_score should be populated and > 0
    assert feat[2] == "Story EP" # Capex is a Story EP
    assert feat[3] in ("HIGH", "MEDIUM", "LOW")
    assert feat[4] == 1000.0  # 10000000000.0 / 10000000 = 1000 Cr (TV India scanner returns INR directly)
    assert feat[5] == 1 # has_result
    assert feat[6] == 160.0 # revenue_growth: (260 - 100)/100 = 160%
    assert feat[7] == 300.0 # profit_growth: (40 - 10)/10 = 300%
    assert feat[8] == 1 # has_corp_event
    assert feat[9] == "CAPEX_EXPANSION"
    # catalyst_score: base 0.45 + 0.10 (rev >= 100) + 0.10 (profit >= 200) + 0.05 (mktcap < 5000 Cr) = 0.70
    # Note: the small-cap bonus now fires correctly because mktcap_cr = 1000 Cr < 5000 Cr.
    # Previously the buggy USD_TO_INR * 83.5 inflated it to 83 500 Cr, silently suppressing this bonus.
    assert feat[10] == 0.70
    
    # Check ep_watchlist since ep_score will be high
    c.execute("SELECT symbol, ep_type, status FROM ep_watchlist WHERE symbol='MOCKSTOCK'")
    wl = c.fetchone()
    assert wl is not None
    assert wl[0] == "MOCKSTOCK"
    assert wl[1] == "Story EP"
    assert wl[2] == "ACTIVE"
    
    conn.close()

def test_api_endpoints(client):
    # Setup some dummy data in DB
    conn = orig_connect(db_path)
    c = conn.cursor()
    
    c.execute("DELETE FROM ep_features")
    c.execute("DELETE FROM ep_watchlist")
    c.execute("DELETE FROM sugar_babies")
    
    # Insert mock ep_features
    c.execute('''
        INSERT INTO ep_features (
            symbol, exchange, feature_date, perf_3m, perf_6m, range_60d_pct, avg_vol_rank,
            neglect_score, has_result, revenue_growth, profit_growth, has_corp_event,
            event_type, catalyst_score, gap_pct, rel_volume, close_loc, repricing_score,
            ep_score, ep_type, confidence, market_cap_cr, avg_turnover_cr, float_days
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        "EPSTOCK", "NSE", "2026-06-11", 5.0, 10.0, 15.0, 0.4,
        0.60, 0, 0.0, 0.0, 0,
        "ABNORMAL_VOLUME", 0.60, 4.0, 5.0, 0.80, 0.70,
        0.65, "Volume EP", "MEDIUM", 800.0, 5.0, 0.0
    ))
    
    # Insert mock watchlist
    c.execute('''
        INSERT INTO ep_watchlist (
            symbol, exchange, catalyst_date, ep_type, status, ep_score, entry_price, stop_price
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', ("EPSTOCK", "NSE", "2026-06-11", "Volume EP", "ACTIVE", 0.65, 120.0, 110.0))
    
    # Insert mock sugar_babies
    c.execute('''
        INSERT INTO sugar_babies (
            symbol, exchange, added_date, avg_burst_pct, avg_burst_days, episode_count, notes, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', ("SUGARSTOCK", "NSE", "2026-06-11", 45.0, 12, 3, "Super breakout stock", 1))
    
    conn.commit()
    conn.close()
    
    # Test GET /api/ep/today
    res = client.get("/api/ep/today?min_score=0.55")
    assert res.status_code == 200
    data = res.get_json()
    assert "listings" in data
    assert len(data["listings"]) == 1
    assert data["listings"][0]["symbol"] == "EPSTOCK"
    assert data["latest_date"] == "2026-06-11"
    
    # Test GET /api/ep/today with filter that matches nothing
    res = client.get("/api/ep/today?ep_type=Growth EP")
    assert res.status_code == 200
    assert len(res.get_json()["listings"]) == 0
    
    # Test GET /api/ep/watchlist
    res = client.get("/api/ep/watchlist")
    assert res.status_code == 200
    data = res.get_json()
    assert "watchlist" in data
    assert len(data["watchlist"]) == 1
    assert data["watchlist"][0]["symbol"] == "EPSTOCK"
    
    # Test GET /api/ep/sugar-babies
    res = client.get("/api/ep/sugar-babies")
    assert res.status_code == 200
    data = res.get_json()
    assert "sugar_babies" in data
    assert len(data["sugar_babies"]) == 1
    assert data["sugar_babies"][0]["symbol"] == "SUGARSTOCK"
    
    # Test GET /api/ep/<symbol>/detail
    # Since detail route calls fetch_historical_prices, we mock it to prevent external fetch
    with patch("app.fetch_historical_prices") as mock_fetch:
        mock_fetch.return_value = [{"date": "2026-06-11", "open": 100, "high": 110, "low": 99, "close": 108, "volume": 10000}]
        res = client.get("/api/ep/EPSTOCK/detail")
        assert res.status_code == 200
        data = res.get_json()
        assert data["symbol"] == "EPSTOCK"
        assert "history" in data
        assert len(data["history"]) == 1
        assert "corporate_events" in data
        assert "fundamentals" in data
        
    # Test POST /api/ep/refresh
    with patch("app.refresh_ep_screener") as mock_refresh:
        res = client.post("/api/ep/refresh")
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert "Background EP refresh started" in data["message"]
        
        # Test GET /api/ep/refresh/status
        res_status = client.get("/api/ep/refresh/status")
        assert res_status.status_code == 200
        assert "running" in res_status.get_json()


def test_fetch_screener_fundamentals_parsing():
    mock_html = """
    <div id="quarters">
        <table>
            <thead>
                <tr>
                    <th>Quarters</th>
                    <th data-date-key="2025-03-31">Mar 2025</th>
                    <th data-date-key="2025-06-30">Jun 2025</th>
                    <th data-date-key="2025-09-30">Sep 2025</th>
                    <th data-date-key="2025-12-30">Dec 2025</th>
                    <th data-date-key="2026-03-31">Mar 2026</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td class="text">Sales</td>
                    <td>100</td>
                    <td>110</td>
                    <td>120</td>
                    <td>130</td>
                    <td>200</td>
                </tr>
                <tr>
                    <td class="text">Net Profit</td>
                    <td>10</td>
                    <td>12</td>
                    <td>15</td>
                    <td>(5)</td>
                    <td>25</td>
                </tr>
                <tr>
                    <td class="text">EPS in Rs</td>
                    <td>1.0</td>
                    <td>1.2</td>
                    <td>1.5</td>
                    <td>-0.5</td>
                    <td>2.5</td>
                </tr>
            </tbody>
        </table>
    </div>
    """
    
    class MockResponse:
        def __init__(self, content):
            self.content = content.encode('utf-8')
        def read(self):
            return self.content
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("urllib.request.urlopen", return_value=MockResponse(mock_html)):
        res = app.fetch_screener_fundamentals("MOCK")
        assert len(res) == 5
        assert res[0]["quarter"] == "Mar 2025"
        assert res[0]["date_key"] == "2025-03-31"
        assert res[0]["revenue"] == 100.0
        assert res[0]["net_profit"] == 10.0
        assert res[0]["eps"] == 1.0
        assert res[3]["net_profit"] == -5.0 # parentheses check


def test_compute_yoy_metrics_logic():
    quarters = [
        {"quarter": "Mar 2025", "date_key": "2025-03-31", "revenue": 100.0, "net_profit": 10.0, "eps": 1.0},
        {"quarter": "Jun 2025", "date_key": "2025-06-30", "revenue": 110.0, "net_profit": 12.0, "eps": 1.2},
        {"quarter": "Sep 2025", "date_key": "2025-09-30", "revenue": 120.0, "net_profit": 15.0, "eps": 1.5},
        {"quarter": "Dec 2025", "date_key": "2025-12-30", "revenue": 80.0, "net_profit": -5.0, "eps": -0.5},
        {"quarter": "Mar 2026", "date_key": "2026-03-31", "revenue": 210.0, "net_profit": 25.0, "eps": 2.5}
    ]
    res = app.compute_yoy_metrics(quarters)
    mar_2026 = res[4]
    assert mar_2026["revenue_yoy_pct"] == 110.0
    assert mar_2026["net_profit_yoy_pct"] == 150.0
    assert mar_2026["eps_yoy_pct"] == 150.0
    assert mar_2026["surprise_type"] == "BLOWOUT_EARNINGS"

    quarters_turnaround = [
        {"quarter": "Mar 2025", "date_key": "2025-03-31", "revenue": 100.0, "net_profit": -5.0, "eps": -0.5},
        {"quarter": "Jun 2025", "date_key": "2025-06-30", "revenue": 110.0, "net_profit": 12.0, "eps": 1.2},
        {"quarter": "Sep 2025", "date_key": "2025-09-30", "revenue": 120.0, "net_profit": 15.0, "eps": 1.5},
        {"quarter": "Dec 2025", "date_key": "2025-12-30", "revenue": 130.0, "net_profit": 10.0, "eps": 1.0},
        {"quarter": "Mar 2026", "date_key": "2026-03-31", "revenue": 130.0, "net_profit": 15.0, "eps": 1.5}
    ]
    res_ta = app.compute_yoy_metrics(quarters_turnaround)
    mar_ta = res_ta[4]
    assert mar_ta["surprise_type"] == "TURNAROUND"

    # Test MISS cascade coverage (one of revenue/profit YoY negative)
    quarters_miss = [
        {"quarter": "Mar 2025", "date_key": "2025-03-31", "revenue": 100.0, "net_profit": 10.0, "eps": 1.0},
        {"quarter": "Jun 2025", "date_key": "2025-06-30", "revenue": 110.0, "net_profit": 12.0, "eps": 1.2},
        {"quarter": "Sep 2025", "date_key": "2025-09-30", "revenue": 120.0, "net_profit": 15.0, "eps": 1.5},
        {"quarter": "Dec 2025", "date_key": "2025-12-30", "revenue": 130.0, "net_profit": 10.0, "eps": 1.0},
        {"quarter": "Mar 2026", "date_key": "2026-03-31", "revenue": 90.0, "net_profit": 15.0, "eps": 1.5} # YoY rev -10%, YoY net profit +50%
    ]
    res_miss = app.compute_yoy_metrics(quarters_miss)
    mar_miss = res_miss[4]
    assert mar_miss["revenue_yoy_pct"] == -10.0
    assert mar_miss["surprise_type"] == "MISS"

