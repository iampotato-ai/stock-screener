import pytest
import sqlite3
import json
import sys
import os
from datetime import datetime, date

# Ensure the root folder is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app, init_db, classify_momentum_phase, refresh_ipo_metrics

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
    init_db()
    
    # Seed a couple of mock IPO listings into the test DB
    conn = orig_connect(db_file)
    c = conn.cursor()
    c.execute("DELETE FROM ipo_listings")
    c.execute("DELETE FROM ipo_metrics_cache")
    
    seed_test_data = [
        # Mainboard
        ("MOCK1.NS", "Mock Mainboard One", "2026-06-01", 100.0, 120.0, 115.0, "NSE", "IT", 500.0, 10, 20.0),
        # BSE Mainboard
        ("MOCK2.NS", "Mock BSE Two", "2026-05-15", 50.0, 60.0, 58.0, "BSE", "Textiles", 25.0, 1000, 10.0)
    ]
    
    for row in seed_test_data:
        c.execute('''
            INSERT INTO ipo_listings (
                ticker, company_name, listing_date, issue_price, listing_open, listing_close, exchange, sector, issue_size_cr, lot_size, gmp_at_listing
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', row)
        
    conn.commit()
    conn.close()
    
    yield db_file

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_classify_momentum_phase():
    # Rules:
    # Days since <= 10 and return vs issue > 15% -> HOT
    # Days since <= 60 and return vs listing > 5% -> STABLE
    # Return vs listing < -10% -> BROKEN
    # Otherwise -> FADING
    
    # HOT
    assert classify_momentum_phase(days_since=5, current_vs_issue=20, current_vs_listing=10) == "HOT"
    # STABLE (more than 10 days, but <= 60 days, and current vs listing > 5)
    assert classify_momentum_phase(days_since=20, current_vs_issue=20, current_vs_listing=8) == "STABLE"
    # BROKEN (current vs listing < -10)
    assert classify_momentum_phase(days_since=15, current_vs_issue=-15, current_vs_listing=-12) == "BROKEN"
    # FADING (default)
    assert classify_momentum_phase(days_since=20, current_vs_issue=10, current_vs_listing=2) == "FADING"

def test_refresh_ipo_metrics_and_listings_api(client, monkeypatch):
    # Mock fetch_historical_prices to return custom mock history
    def mock_fetch_historical_prices(ticker, range_str="1y"):
        # Returns a list of daily close prices
        # Mock 10 days of history
        # MOCK1: Issue=100.0, Listing=115.0
        # Let's say current price is 150.0 (Gain vs issue = 50%, Gain vs listing = 30%)
        # MOCK2: Issue=50.0, Listing=58.0
        # Let's say current price is 30.0 (Gain vs issue = -40%, Gain vs listing = -48%)
        current = 150.0 if ticker == "MOCK1.NS" else 30.0
        hist = []
        for i in range(10):
            hist.append({
                "open": current - 2,
                "high": current + 5,
                "low": current - 5,
                "close": current,
                "volume": 2000.0,
                "date": f"2026-06-0{i+1}"
            })
        return hist
        
    monkeypatch.setattr("app.fetch_historical_prices", mock_fetch_historical_prices)
    
    # Perform cache refresh
    refresh_ipo_metrics()
    
    # Query Listings API
    res = client.get("/api/ipo/listings")
    assert res.status_code == 200
    data = res.get_json()
    assert "listings" in data
    assert "summary" in data
    assert data["total"] == 2
    
    listings = data["listings"]
    # Sorting can be random due to thread pool executor order, but we can search by ticker
    mock1_metrics = next(item for item in listings if item["ticker"] == "MOCK1.NS")
    mock2_metrics = next(item for item in listings if item["ticker"] == "MOCK2.NS")
    
    # Validate MOCK1 calculations
    assert mock1_metrics["current_price"] == 150.0
    assert mock1_metrics["issue_price"] == 100.0
    assert mock1_metrics["current_vs_issue_pct"] == 50.0
    assert mock1_metrics["current_vs_listing_pct"] == 30.43 # (150 - 115) / 115 * 100
    
    # Validate MOCK2 calculations
    assert mock2_metrics["current_price"] == 30.0
    assert mock2_metrics["issue_price"] == 50.0
    assert mock2_metrics["current_vs_issue_pct"] == -40.0
    assert mock2_metrics["current_vs_listing_pct"] == -48.28 # (30 - 58) / 58 * 100
    assert mock2_metrics["momentum_phase"] == "BROKEN"

def test_api_filters(client, monkeypatch):
    # Mock data refresh
    def mock_fetch_historical_prices(ticker, range_str="1y"):
        current = 150.0 if ticker == "MOCK1.NS" else 30.0
        return [{"open": current, "high": current, "low": current, "close": current, "volume": 1000.0, "date": "2026-06-01"}]
        
    monkeypatch.setattr("app.fetch_historical_prices", mock_fetch_historical_prices)
    refresh_ipo_metrics()
    
    # 1. Test Exchange Filter
    res_nse = client.get("/api/ipo/listings?exchange=NSE")
    assert res_nse.status_code == 200
    assert res_nse.get_json()["total"] == 1
    assert res_nse.get_json()["listings"][0]["ticker"] == "MOCK1.NS"
    
    res_bse = client.get("/api/ipo/listings?exchange=BSE")
    assert res_bse.status_code == 200
    assert res_bse.get_json()["total"] == 1
    assert res_bse.get_json()["listings"][0]["ticker"] == "MOCK2.NS"
    
    # 2. Test Phase Filter
    res_broken = client.get("/api/ipo/listings?phase=BROKEN")
    assert res_broken.status_code == 200
    assert res_broken.get_json()["total"] == 1
    assert res_broken.get_json()["listings"][0]["ticker"] == "MOCK2.NS"

def test_api_detail_and_refresh_smoke(client, monkeypatch):
    def mock_fetch_historical_prices(ticker, range_str="1y"):
        return [{"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1000.0, "date": "2026-06-01"}]
    monkeypatch.setattr("app.fetch_historical_prices", mock_fetch_historical_prices)
    refresh_ipo_metrics()
    
    # Detail API smoke test
    res_detail = client.get("/api/ipo/detail/MOCK1.NS")
    assert res_detail.status_code == 200
    detail = res_detail.get_json()
    assert detail["ticker"] == "MOCK1.NS"
    assert "history" in detail
    
    # Detail API 404 test
    res_404 = client.get("/api/ipo/detail/NONEXISTENT")
    assert res_404.status_code == 404
    
    # Refresh API smoke test
    res_refresh = client.post("/api/ipo/refresh")
    assert res_refresh.status_code == 200
    assert res_refresh.get_json()["success"] is True

def test_volume_filter_and_additional_columns(client, monkeypatch):
    # Mock data refresh with different volumes and changes
    def mock_fetch_historical_prices(ticker, range_str="1y"):
        if ticker == "MOCK1.NS":
            return [
                {"open": 100, "high": 100, "low": 100, "close": 100, "volume": 10000.0, "date": "2026-06-01"},
                {"open": 110, "high": 110, "low": 110, "close": 110, "volume": 200000.0, "date": "2026-06-02"}
            ]
        else:
            return [
                {"open": 50, "high": 50, "low": 50, "close": 50, "volume": 1000.0, "date": "2026-06-01"},
                {"open": 49, "high": 49, "low": 49, "close": 49, "volume": 5000.0, "date": "2026-06-02"}
            ]
            
    monkeypatch.setattr("app.fetch_historical_prices", mock_fetch_historical_prices)
    refresh_ipo_metrics()
    
    # 1. Check columns are serialized
    res = client.get("/api/ipo/listings")
    assert res.status_code == 200
    data = res.get_json()
    listings = data["listings"]
    mock1 = next(item for item in listings if item["ticker"] == "MOCK1.NS")
    mock2 = next(item for item in listings if item["ticker"] == "MOCK2.NS")
    
    assert mock1["volume"] == 200000.0
    assert mock1["change_pct"] == 10.0
    assert mock1["day_low"] == 110.0
    assert mock1["day_high"] == 110.0
    
    assert mock2["volume"] == 5000.0
    assert mock2["change_pct"] == -2.0
    assert mock2["day_low"] == 49.0
    assert mock2["day_high"] == 49.0
    
    # 2. Test Volume Filter > 10K (only MOCK1 should match)
    res_filter = client.get("/api/ipo/listings?min_volume=10k")
    assert res_filter.status_code == 200
    data_filter = res_filter.get_json()
    assert data_filter["total"] == 1
    assert data_filter["listings"][0]["ticker"] == "MOCK1.NS"

def test_sorting_by_day_range_pct(client, monkeypatch):
    def mock_fetch_historical_prices(ticker, range_str="1y"):
        if ticker == "MOCK1.NS":
            # low=100, high=200, close=120 (20%)
            return [{"open": 120, "high": 200, "low": 100, "close": 120, "volume": 1000.0, "date": "2026-06-01"}]
        else:
            # low=50, high=100, close=90 (80%)
            return [{"open": 90, "high": 100, "low": 50, "close": 90, "volume": 1000.0, "date": "2026-06-01"}]
            
    monkeypatch.setattr("app.fetch_historical_prices", mock_fetch_historical_prices)
    refresh_ipo_metrics()
    
    # 1. Sort DESC
    res_desc = client.get("/api/ipo/listings?sort_by=day_range_pct&order=desc")
    assert res_desc.status_code == 200
    listings_desc = res_desc.get_json()["listings"]
    assert len(listings_desc) == 2
    assert listings_desc[0]["ticker"] == "MOCK2.NS"
    assert listings_desc[1]["ticker"] == "MOCK1.NS"
    
    # 2. Sort ASC
    res_asc = client.get("/api/ipo/listings?sort_by=day_range_pct&order=asc")
    assert res_asc.status_code == 200
    listings_asc = res_asc.get_json()["listings"]
    assert len(listings_asc) == 2
    assert listings_asc[0]["ticker"] == "MOCK1.NS"
    assert listings_asc[1]["ticker"] == "MOCK2.NS"


def test_api_age_filters(client, monkeypatch):
    # Mock historical prices to return something basic
    def mock_fetch_historical_prices(ticker, range_str="2y"):
        return [{"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1000.0, "date": "2025-01-01"}]
    monkeypatch.setattr("app.fetch_historical_prices", mock_fetch_historical_prices)

    # Insert an IPO listed 14 months ago (~425 days ago)
    # Today is 2026-06-11, so 14 months ago is around 2025-04-11
    conn = sqlite3.connect("scan_history.db")
    c = conn.cursor()
    
    # Clean first
    c.execute("DELETE FROM ipo_listings WHERE ticker = 'MOCK_OLD.NS'")
    c.execute("DELETE FROM ipo_metrics_cache WHERE ticker = 'MOCK_OLD.NS'")
    
    c.execute('''
        INSERT INTO ipo_listings (
            ticker, company_name, listing_date, issue_price, listing_open, listing_close, exchange, sector, issue_size_cr, lot_size, gmp_at_listing
        ) VALUES ('MOCK_OLD.NS', 'Mock Old Mainboard', '2025-04-11', 100.0, 100.0, 100.0, 'NSE', 'IT', 100.0, 10, 0.0)
    ''')
    conn.commit()
    conn.close()

    refresh_ipo_metrics()

    # Query age filter of 6 months (should exclude MOCK_OLD.NS)
    res_6m = client.get("/api/ipo/listings?days=6m")
    assert res_6m.status_code == 200
    listings_6m = res_6m.get_json()["listings"]
    assert not any(item["ticker"] == "MOCK_OLD.NS" for item in listings_6m)

    # Query age filter of 1 year (should exclude MOCK_OLD.NS)
    res_1y = client.get("/api/ipo/listings?days=1y")
    assert res_1y.status_code == 200
    listings_1y = res_1y.get_json()["listings"]
    assert not any(item["ticker"] == "MOCK_OLD.NS" for item in listings_1y)

    # Query age filter of 18 months (should include MOCK_OLD.NS)
    res_18m = client.get("/api/ipo/listings?days=18m")
    assert res_18m.status_code == 200
    listings_18m = res_18m.get_json()["listings"]
    assert any(item["ticker"] == "MOCK_OLD.NS" for item in listings_18m)

