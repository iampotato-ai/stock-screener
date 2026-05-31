import pytest
from forecast_math import compute_atr_pct, compute_forecast_metrics

# Helper fixtures
history_flat = [{"high": 100.0, "low": 98.0, "close": 99.0} for _ in range(30)]
history_trending = [{"high": 90.0 + i, "low": 88.0 + i, "close": 89.0 + i} for i in range(30)]

def test_compute_atr_pct():
    # Constant ranges: high - low = 2.0, close changes by 1.0 each day.
    # tr = max(high-low, high-prev_close, low-prev_close) = max(2.0, 90-89, 88-89) = 2.0
    # atr over window 14 should be 2.0
    # last close is 118.0
    # expected atr_pct = (2.0 / 118.0) * 100 = 1.6949%
    atr_pct = compute_atr_pct(history_trending, window=14)
    assert pytest.approx(atr_pct, 0.01) == 1.6949

def test_compute_forecast_metrics_bullish():
    # Strictly rising forecast
    forecast = [
        {"close": 120.0, "high": 121.0, "low": 119.0},
        {"close": 122.0, "high": 123.0, "low": 121.0},
        {"close": 124.0, "high": 125.0, "low": 123.0},
        {"close": 126.0, "high": 127.0, "low": 125.0},
        {"close": 128.0, "high": 129.0, "low": 127.0},
    ]
    last_close = 118.0
    
    bias, confidence, metrics = compute_forecast_metrics(forecast, last_close, history_trending)
    
    print("Bullish Bias:", bias)
    print("Bullish Confidence:", confidence)
    print("Bullish Metrics:", metrics)
    
    assert bias in ["Strong Breakout", "Bullish Continuation"]
    assert confidence >= 25 and confidence <= 92
    assert metrics["return_pct"] > 0
    assert metrics["max_drawdown_pct"] >= 0.0  # Min is 120, which is > 118 (drawdown = 120-118 > 0)
    assert metrics["consistency_pct"] == 100.0

def test_compute_forecast_metrics_bearish():
    # Strictly falling forecast
    forecast = [
        {"close": 116.0, "high": 117.0, "low": 115.0},
        {"close": 114.0, "high": 115.0, "low": 113.0},
        {"close": 112.0, "high": 113.0, "low": 111.0},
        {"close": 110.0, "high": 111.0, "low": 109.0},
        {"close": 108.0, "high": 109.0, "low": 107.0},
    ]
    last_close = 118.0
    
    bias, confidence, metrics = compute_forecast_metrics(forecast, last_close, history_trending)
    
    print("Bearish Bias:", bias)
    assert bias in ["Bearish Pressure", "Strong Downtrend"]
    assert metrics["return_pct"] < 0
    assert metrics["max_drawdown_pct"] < 0

def test_compute_forecast_metrics_empty():
    bias, confidence, metrics = compute_forecast_metrics([], 100.0, history_trending)
    assert bias is None
    assert confidence == 0
    assert metrics == {}
