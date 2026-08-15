"""Unit tests for Multiyear Breakout scanner service."""

import pytest
from datetime import datetime, timedelta
from app.services.multiyear_breakout_service import (
    compute_single_breakout,
    scan_multiyear_breakouts,
)


def _generate_synthetic_history(
    total_years: int = 10,
    ath_years_ago: int = 7,
    ath_price: float = 500.0,
    base_floor: float = 250.0,
    breakout_days_ago: int = 2,
    breakout_price: float = 550.0,
    high_volume_on_breakout: bool = True,
):
    """Generate synthetic daily OHLCV bars for testing."""
    total_days = int(total_years * 252)
    ath_idx = int((total_years - ath_years_ago) * 252)
    breakout_idx = total_days - breakout_days_ago

    base_date = datetime.now() - timedelta(days=int(total_years * 365.25))
    rows = []

    for i in range(total_days):
        dt = base_date + timedelta(days=int(i * 365.25 / 252))
        date_str = dt.strftime("%Y-%m-%d")

        if i < ath_idx:
            # Uptrend towards ATH
            price = 100.0 + (ath_price - 100.0) * (i / ath_idx)
            vol = 100000
        elif i == ath_idx:
            # The historical All-Time High
            price = ath_price
            vol = 200000
        elif i < breakout_idx:
            # Consolidation base below ATH
            phase = (i - ath_idx) / (breakout_idx - ath_idx)
            # Oscillate between base_floor and 85% of ATH
            price = base_floor + (ath_price * 0.85 - base_floor) * (0.5 + 0.5 * (i % 20) / 20)
            vol = 80000
        else:
            # Breakout above ATH
            price = breakout_price + (i - breakout_idx) * 2.0
            vol = 300000 if high_volume_on_breakout else 50000

        rows.append({
            "date": date_str,
            "open": round(price * 0.99, 2),
            "high": round(price * 1.01, 2),
            "low": round(price * 0.98, 2),
            "close": round(price, 2),
            "volume": vol,
        })

    return rows


def _generate_nifty_history(days=2520):
    """Generate synthetic Nifty 50 history."""
    base_date = datetime.now() - timedelta(days=int(days * 365.25 / 252))
    rows = []
    for i in range(days):
        dt = base_date + timedelta(days=int(i * 365.25 / 252))
        price = 10000.0 + i * 5.0
        rows.append({
            "date": dt.strftime("%Y-%m-%d"),
            "open": price,
            "high": price * 1.01,
            "low": price * 0.99,
            "close": price,
            "volume": 1000000,
        })
    return rows


class TestMultiyearBreakoutService:
    """Test suite for compute_single_breakout and scan_multiyear_breakouts."""

    def test_qualifying_breakout(self):
        """A stock breaking out after a 7-year base should qualify."""
        history = _generate_synthetic_history(
            total_years=10,
            ath_years_ago=7,
            ath_price=500.0,
            base_floor=200.0,
            breakout_days_ago=3,
            breakout_price=530.0,
            high_volume_on_breakout=True,
        )
        nifty = _generate_nifty_history()

        result = compute_single_breakout(
            symbol="TESTSTOCK",
            history=history,
            nifty_history=nifty,
            min_base_years=5,
            breakout_window_days=10,
            market_cap_cr=25000.0,
            sector="Technology",
        )

        assert result is not None
        assert result["symbol"] == "TESTSTOCK"
        assert result["current_price"] > 500.0
        assert result["prior_ath_price"] == 500.0
        assert result["years_below_ath"] >= 6.5
        assert result["pct_above_ath"] > 0
        assert result["volume_confirmed"] is True
        assert result["market_cap_cr"] == 25000.0
        assert result["sector"] == "Technology"
        assert result["consolidation_range_pct"] > 0
        assert result["rs_vs_nifty"] is not None

    def test_no_breakout_still_below_ath(self):
        """A stock that has not crossed above its ATH should return None."""
        history = _generate_synthetic_history(
            total_years=10,
            ath_years_ago=7,
            ath_price=500.0,
            base_floor=200.0,
            breakout_days_ago=3,
            breakout_price=450.0,  # Below ATH
        )
        result = compute_single_breakout("BELOW_ATH", history)
        assert result is None

    def test_base_too_short(self):
        """A stock whose ATH was only 2 years ago should fail when min_base_years=5."""
        history = _generate_synthetic_history(
            total_years=5,
            ath_years_ago=2,
            ath_price=500.0,
            base_floor=350.0,
            breakout_days_ago=2,
            breakout_price=520.0,
        )
        result = compute_single_breakout("SHORT_BASE", history, min_base_years=5)
        assert result is None

    def test_insufficient_history(self):
        """A stock with less than min_base_years of total data should return None."""
        short_history = [
            {"date": "2024-01-01", "open": 100, "high": 105, "low": 95, "close": 100, "volume": 1000}
            for _ in range(100)
        ]
        result = compute_single_breakout("SHORT_HIST", short_history, min_base_years=5)
        assert result is None

    def test_empty_history(self):
        """Empty history returns None."""
        result = compute_single_breakout("EMPTY", [])
        assert result is None

    def test_volume_not_confirmed(self):
        """When breakout volume is low, volume_confirmed should be False."""
        history = _generate_synthetic_history(
            total_years=10,
            ath_years_ago=7,
            ath_price=500.0,
            base_floor=200.0,
            breakout_days_ago=3,
            breakout_price=530.0,
            high_volume_on_breakout=False,
        )
        result = compute_single_breakout("LOW_VOL", history, min_base_years=5)
        assert result is not None
        assert result["volume_confirmed"] is False

    def test_scan_multiyear_breakouts_batch(self, monkeypatch):
        """Batch scanner should return sorted qualifying stocks."""
        qualifying_hist = _generate_synthetic_history(
            total_years=12, ath_years_ago=9, ath_price=400.0, breakout_price=420.0
        )
        non_qualifying_hist = _generate_synthetic_history(
            total_years=10, ath_years_ago=7, ath_price=500.0, breakout_price=400.0
        )

        def mock_fetch(symbol):
            if symbol == "^NSEI":
                return _generate_nifty_history()
            if symbol == "QUALIFY":
                return qualifying_hist
            if symbol == "NO_BREAKOUT":
                return non_qualifying_hist
            return None

        monkeypatch.setattr("app.services.multiyear_breakout_service._fetch_max_history", mock_fetch)

        results = scan_multiyear_breakouts(["QUALIFY", "NO_BREAKOUT", "MISSING"], min_base_years=5)
        assert len(results) == 1
        assert results[0]["symbol"] == "QUALIFY"
        assert results[0]["years_below_ath"] >= 8.0
