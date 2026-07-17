import pytest
from unittest.mock import patch, MagicMock
import requests
from app.api.v1.legacy_routes import (
    _scrape_screener_in,
    generate_synthetic_fundamentals,
    fetch_screener_fundamentals
)

# Mock Screener.in HTML
MOCK_SCREENER_HTML = """
<html>
<body>
    <section id="quarters">
        <table>
            <thead>
                <tr>
                    <th>Quarter</th>
                    <th>Jun 2024</th>
                    <th>Sep 2024</th>
                    <th>Dec 2024</th>
                    <th>Mar 2025</th>
                    <th>Jun 2025</th>
                    <th>Sep 2025</th>
                    <th>Dec 2025</th>
                    <th>Mar 2026</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Sales +</td>
                    <td>1,000</td>
                    <td>1,100</td>
                    <td>1,200</td>
                    <td>1,300</td>
                    <td>1,400</td>
                    <td>1,500</td>
                    <td>1,600</td>
                    <td>1,700</td>
                </tr>
                <tr>
                    <td>Net Profit +</td>
                    <td>100</td>
                    <td>110</td>
                    <td>120</td>
                    <td>130</td>
                    <td>140</td>
                    <td>150</td>
                    <td>160</td>
                    <td>170</td>
                </tr>
                <tr>
                    <td>EPS in Rs</td>
                    <td>2.00</td>
                    <td>2.20</td>
                    <td>2.40</td>
                    <td>2.60</td>
                    <td>2.80</td>
                    <td>3.00</td>
                    <td>3.20</td>
                    <td>3.40</td>
                </tr>
            </tbody>
        </table>
    </section>
</body>
</html>
"""

def test_scrape_screener_in_success(monkeypatch):
    """Verify Screener.in HTML parser correctly extracts headers, sales, profit, and EPS."""
    mock_get = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = MOCK_SCREENER_HTML
    mock_get.return_value = mock_resp
    monkeypatch.setattr(requests, "get", mock_get)

    res = _scrape_screener_in("TICKER")
    
    assert res is not None
    assert len(res) == 8
    # Check last quarter mapping
    assert res[-1]["quarter"] == "Mar 2026"
    assert res[-1]["date_key"] == "2026-03-31"
    assert res[-1]["revenue"] == 1700.0
    assert res[-1]["net_profit"] == 170.0
    assert res[-1]["eps"] == 3.4
    assert res[-1]["source"] == "Screener.in"

def test_generate_synthetic_fundamentals():
    """Verify synthetic generator generates valid fallback quarters."""
    res = generate_synthetic_fundamentals("TICKER")
    assert len(res) == 4
    for q in res:
        assert "quarter" in q
        assert "date_key" in q
        assert "revenue" in q
        assert "net_profit" in q
        assert "eps" in q
        assert q["source"] == "Synthetic Generator"
        assert q["revenue"] > 0
        assert q["net_profit"] > 0
        assert q["eps"] > 0

def test_fetch_screener_fundamentals_layered_fallback(monkeypatch):
    """Verify fetch_screener_fundamentals fallbacks appropriately."""
    # Scenario 1: Screener.in succeeds
    mock_scrape = MagicMock(return_value=[{"quarter": "Jun 2026", "revenue": 100}])
    monkeypatch.setattr("app.api.v1.legacy_routes._scrape_screener_in", mock_scrape)
    
    res = fetch_screener_fundamentals("TICKER")
    assert len(res) == 1
    assert res[0]["revenue"] == 100
    
    # Scenario 2: Screener.in fails, Yahoo Finance succeeds
    mock_scrape.return_value = None
    mock_yfinance_df = MagicMock()
    mock_yfinance_df.empty = False
    import pandas as pd
    import datetime
    
    # Mock dataframe with quarterly statement data
    cols = [pd.Timestamp("2026-03-31")]
    data = {
        cols[0]: [100000000.0, 10000000.0, 1.5]
    }
    df = pd.DataFrame(data, index=["Total Revenue", "Net Income", "Basic EPS"])
    
    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.quarterly_income_stmt = df
        mock_ticker_cls.return_value = mock_ticker
        
        res = fetch_screener_fundamentals("TICKER")
        assert len(res) == 1
        assert res[0]["revenue"] == 10.0 # 100M Rs / 10M = 10.0 Cr
        assert res[0]["net_profit"] == 1.0 # 10M Rs / 10M = 1.0 Cr
        assert res[0]["eps"] == 1.5
        assert res[0]["source"] == "Yahoo Finance"

    # Scenario 3: All fail, falls back to Synthetic
    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.quarterly_income_stmt = None
        mock_ticker_cls.return_value = mock_ticker
        
        res = fetch_screener_fundamentals("TICKER")
        assert len(res) == 4
        assert res[0]["source"] == "Synthetic Generator"
