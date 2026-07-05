"""
Unit tests for fetcher_utils.py - technical computations.
Tests EMA, MACD, ADX, SuperTrend, volatility, and YoY growth calculations.
"""
import math
import pytest

from app.services.scoring.fetcher_utils import (
    compute_ema, compute_macd, compute_adx, compute_supertrend,
    compute_volatility, compute_yoy_growth, compute_rsi
)


class TestFetcherUtils:
    """Test financial and technical indicator calculation utilities."""

    def test_compute_ema_basic(self):
        """Test EMA calculation with known values."""
        prices = [10, 12, 13, 11, 14, 15, 16, 18, 20, 22]
        ema = compute_ema(prices, 3)

        # First 2 values should be NaN (insufficient data)
        assert math.isnan(ema[0])
        assert math.isnan(ema[1])

        # Third value should be SMA of first 3
        expected_sma = (10 + 12 + 13) / 3  # 11.666...
        assert abs(ema[2] - expected_sma) < 0.001

        # Last value should be a reasonable EMA
        assert not math.isnan(ema[-1])
        assert ema[-1] > 0

    def test_compute_ema_insufficient_data(self):
        """Test EMA with insufficient data."""
        prices = [10, 12]
        ema = compute_ema(prices, 5)

        # All should be NaN since we need at least 5 points
        assert all(math.isnan(x) for x in ema)

    def test_compute_macd_basic(self):
        """Test MACD calculation."""
        # Need sufficient data: slow period (26) + signal period (9) + enough for MACD calculation
        # Let's use 100 data points to be safe
        prices = [float(x) for x in range(10, 110)]  # 100 values from 10 to 109
        macd, signal, hist = compute_macd(prices, 12, 26, 9)

        # Should have some non-NaN values
        assert not all(math.isnan(x) for x in macd)
        assert not all(math.isnan(x) for x in signal)
        assert not all(math.isnan(x) for x in hist)

        # MACD line should be EMA(12) - EMA(26)
        ema_12 = compute_ema(prices, 12)
        ema_26 = compute_ema(prices, 26)
        expected_macd = [e1 - e2 if not (math.isnan(e1) or math.isnan(e2)) else float('nan')
                        for e1, e2 in zip(ema_12, ema_26)]

        # Compare non-NaN values
        valid_count = 0
        for i in range(len(macd)):
            if not (math.isnan(macd[i]) or math.isnan(expected_macd[i])):
                assert abs(macd[i] - expected_macd[i]) < 0.001
                valid_count += 1
        # Should have several valid comparisons
        assert valid_count > 20

    def test_compute_macd_insufficient_data(self):
        """Test MACD with insufficient data."""
        prices = [10, 12]
        macd, signal, hist = compute_macd(prices)

        # All should be NaN
        assert all(math.isnan(x) for x in macd)
        assert all(math.isnan(x) for x in signal)
        assert all(math.isnan(x) for x in hist)

    def test_compute_adx_basic(self):
        """Test ADX calculation with trending data."""
        # Need enough data for ADX calculation (period 14 + smoothing)
        # Create strong trending data with sufficient volatility
        highs = [float(x) for x in range(10, 60)]  # 50 values: 10 to 59
        lows = [float(x - 1) for x in range(10, 60)]  # 9 to 58
        closes = [float(x - 0.5) for x in range(10, 60)]  # 9.5 to 58.5

        adx = compute_adx(highs, lows, closes, 14)

        # Should have some non-NaN values after sufficient period
        # ADX needs period + extra for smoothing, so check after index 25+
        assert not all(math.isnan(x) for x in adx[25:])

        # ADX should be between 0 and 100
        for val in adx:
            if not math.isnan(val):
                assert 0 <= val <= 100

    def test_compute_adx_insufficient_data(self):
        """Test ADX with insufficient data."""
        highs = [10, 11, 12]
        lows = [9, 10, 11]
        closes = [9.5, 10.5, 11.5]
        adx = compute_adx(highs, lows, closes, 14)

        # All should be NaN
        assert all(math.isnan(x) for x in adx)

    def test_compute_supertrend_basic(self):
        """Test Supertrend calculation."""
        # Need enough data for ATR and Supertrend calculation
        # Create trending data with clear direction
        highs = list(range(10, 35))  # 25 values: 10 to 34
        lows = [x - 2 for x in range(10, 35)]  # 8 to 32
        closes = [x - 1 for x in range(10, 35)]  # 9 to 33

        supertrend, direction = compute_supertrend(highs, lows, closes, 10, 3.0)

        # Should have some non-NaN values
        assert not all(math.isnan(x) for x in supertrend)
        assert not all(x == 0 for x in direction)

        # Direction should be either 1 or -1 (not 0) for valid values
        for i, d in enumerate(direction):
            if not math.isnan(supertrend[i]):
                assert d in [1, -1]

    def test_compute_volatility_basic(self):
        """Test volatility calculation."""
        # Create price series with known volatility
        prices = [100, 101, 99, 102, 98, 103, 97, 104, 96, 105]  # Alternating up/down
        vol = compute_volatility(prices, 5)

        # Should be a positive number
        assert vol >= 0
        assert not math.isnan(vol)

    def test_compute_volatility_insufficient_data(self):
        """Test volatility with insufficient data."""
        prices = [100, 101]
        vol = compute_volatility(prices, 5)

        # Should be 0.0 for insufficient data
        assert vol == 0.0

    def test_compute_yoy_growth_basic(self):
        """Test YoY growth calculation."""
        values = [100, 120, 140, 170]  # 20%, 16.67%, 21.43% growth
        yoy = compute_yoy_growth(values)

        # Should be growth from 140 to 170
        expected = (170 - 140) / 140  # 0.2142...
        assert abs(yoy - expected) < 0.001

    def test_compute_yoy_growth_insufficient_data(self):
        """Test YoY growth with insufficient data."""
        values = [100]
        yoy = compute_yoy_growth(values)

        # Should be 0.0 for insufficient data
        assert yoy == 0.0

    def test_compute_yoy_growth_negative(self):
        """Test YoY growth with negative growth."""
        values = [100, 90]  # -10% growth
        yoy = compute_yoy_growth(values)

        # Should be -0.1
        assert abs(yoy - (-0.1)) < 0.001

    def test_compute_rsi_basic(self):
        """Test RSI calculation."""
        # Create data with known RSI characteristics
        prices = [44, 44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.85, 46.08, 45.89,
                  46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64, 46.21]
        rsi = compute_rsi(prices, 14)

        # Should have some non-NaN values
        assert not all(math.isnan(x) for x in rsi)

        # RSI should be between 0 and 100
        for val in rsi:
            if not math.isnan(val):
                assert 0 <= val <= 100

    def test_compute_rsi_insufficient_data(self):
        """Test RSI with insufficient data."""
        prices = [10, 12]
        rsi = compute_rsi(prices, 14)

        # All should be NaN
        assert all(math.isnan(x) for x in rsi)