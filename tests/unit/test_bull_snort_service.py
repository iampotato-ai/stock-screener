# tests/unit/test_bull_snort_service.py
"""Unit tests for the Bull Snort service implementation.

These tests verify basic error handling and edge‑case behaviour without requiring
real market data. They patch ``fetch_historical_prices`` to return synthetic
DataFrames.
"""

import pandas as pd
import pytest
from unittest.mock import patch

from app.services.bull_snort_service import compute_bull_snort, screen_bull_snort


def make_df(num_rows: int, close_price: float = 100.0, volume: int = 1000):
    """Create a minimal DataFrame compatible with ``fetch_historical_prices``.
    Columns: Open, High, Low, Close, Volume.
    All numeric columns are filled with constant values.
    """
    data = {
        "Open": [close_price] * num_rows,
        "High": [close_price + 1] * num_rows,
        "Low": [close_price - 1] * num_rows,
        "Close": [close_price] * num_rows,
        "Volume": [volume] * num_rows,
    }
    # Use a simple date range index
    index = pd.date_range(end=pd.Timestamp("2024-01-01"), periods=num_rows, freq="B")
    return pd.DataFrame(data, index=index)


def test_compute_insufficient_data(monkeypatch):
    """``compute_bull_snort`` should return ``None`` when the data frame is too short."""
    short_df = make_df(100)  # < 230 rows needed by the service
    with patch("app.services.bull_snort_service.fetch_historical_prices", return_value=short_df):
        result = compute_bull_snort("TEST.SYMBOL")
        assert result is None


def test_compute_exception_handling(monkeypatch):
    """If ``fetch_historical_prices`` raises, the function should return ``None`` and log the error."""
    with patch("app.services.bull_snort_service.fetch_historical_prices", side_effect=Exception("network error")):
        result = compute_bull_snort("FAIL.SYMBOL")
        assert result is None


def test_screen_empty_symbols(monkeypatch):
    """Screening an empty symbol list should return an empty list without errors."""
    # Patch ``compute_bull_snort`` to ensure it is not called
    with patch("app.services.bull_snort_service.compute_bull_snort") as mock_compute:
        results = screen_bull_snort([])
        assert results == []
        mock_compute.assert_not_called()


def test_has_sufficient_history_false(monkeypatch):
    """_has_sufficient_history should return False for insufficient data."""
    from app.services.bull_snort_service import _has_sufficient_history
    
    # Test with less than 230 rows
    short_df = make_df(100)  # < 230 rows
    with patch("app.services.bull_snort_service.fetch_historical_prices", return_value=short_df):
        result = _has_sufficient_history("TEST.SYMBOL")
        assert result is False

    # Test with empty list
    with patch("app.services.bull_snort_service.fetch_historical_prices", return_value=[]):
        result = _has_sufficient_history("EMPTY.SYMBOL")
        assert result is False


def test_has_sufficient_history_true(monkeypatch):
    """_has_sufficient_history should return True for sufficient data."""
    from app.services.bull_snort_service import _has_sufficient_history
    
    # Test with exactly 230 rows
    exact_df = make_df(230)  # == 230 rows
    with patch("app.services.bull_snort_service.fetch_historical_prices", return_value=exact_df):
        result = _has_sufficient_history("EXACT.SYMBOL")
        assert result is True

    # Test with more than 230 rows
    long_df = make_df(300)  # > 230 rows
    with patch("app.services.bull_snort_service.fetch_historical_prices", return_value=long_df):
        result = _has_sufficient_history("LONG.SYMBOL")
        assert result is True


def test_screen_bull_snort_pre_filter_skips_short_history(monkeypatch):
    """screen_bull_snort should skip symbols with insufficient history."""
    from app.services.bull_snort_service import screen_bull_snort, _has_sufficient_history
    
    # Mock fetch_historical_prices to return short data for "SKIP" and long data for "PASS"
    def mock_fetch(symbol, range_str="2y"):
        if symbol == "SKIP":
            return make_df(100)  # insufficient data
        elif symbol == "PASS":
            return make_df(300)  # sufficient data
        else:
            return make_df(250)  # default sufficient
    
    with patch("app.services.bull_snort_service.fetch_historical_prices", side_effect=mock_fetch):
        # Mock compute_bull_snort to return a dummy result for any symbol
        # This allows us to verify it's not called for skipped symbols
        def mock_compute(symbol, **kwargs):
            return {"symbol": symbol, "final_score": 100}
        
        with patch("app.services.bull_snort_service.compute_bull_snort", side_effect=mock_compute) as mock_compute:
            # Mock current_app for the diagnostic cache
            from unittest.mock import MagicMock
            mock_app = MagicMock()
            mock_app.config = {}
            with patch("app.services.bull_snort_service.current_app", mock_app):
                results = screen_bull_snort(["SKIP", "PASS"])
                
                # Should only get results for "PASS"
                assert len(results) == 1
                assert results[0]["symbol"] == "PASS"
                
                # compute_bull_snort should only be called once (for "PASS")
                mock_compute.assert_called_once()
                call_args = mock_compute.call_args[0][0]  # First positional argument (symbol)
                assert call_args == "PASS"
                
                # Diagnostic cache should contain the skipped symbol
                assert "SKIP" in mock_app.config.get('BULL_SNORT_SKIPPED', set())


def test_screen_bull_snort_diagnostic_cache(monkeypatch):
    """Test that the diagnostic cache is properly updated."""
    from app.services.bull_snort_service import screen_bull_snort
    
    # Mock fetch_historical_prices to return short data for some symbols
    def mock_fetch(symbol, range_str="2y"):
        if symbol in ["SKIP1", "SKIP2"]:
            return make_df(100)  # insufficient data
        else:
            return make_df(300)  # sufficient data
    
    with patch("app.services.bull_snort_service.fetch_historical_prices", side_effect=mock_fetch):
        # Mock compute_bull_snort to return a dummy result
        def mock_compute(symbol, **kwargs):
            return {"symbol": symbol, "final_score": 100}
        
        with patch("app.services.bull_snort_service.compute_bull_snort", side_effect=mock_compute):
            # Mock current_app for the diagnostic cache
            from unittest.mock import MagicMock
            mock_app = MagicMock()
            mock_app.config = {}
            with patch("app.services.bull_snort_service.current_app", mock_app):
                results = screen_bull_snort(["SKIP1", "PASS1", "SKIP2", "PASS2"])
                
                # Should get results for PASS1 and PASS2
                assert len(results) == 2
                result_symbols = [r["symbol"] for r in results]
                assert "PASS1" in result_symbols
                assert "PASS2" in result_symbols
                
                # Diagnostic cache should contain both skipped symbols
                skipped_set = mock_app.config.get('BULL_SNORT_SKIPPED', set())
                assert "SKIP1" in skipped_set
                assert "SKIP2" in skipped_set
                assert len(skipped_set) == 2
