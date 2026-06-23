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
