import pytest
from pattern_detection import detect_candlestick_patterns

def test_detect_doji():
    # A Doji has very small body compared to total range
    history = [
        {"open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 1000},
        {"open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 1000},
        {"open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 1000},
        {"open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 1000},
        {"open": 100.0, "high": 102.0, "low": 98.0, "close": 100.05, "volume": 1000}
    ]
    result = detect_candlestick_patterns(history)
    assert "Doji" in result
    assert result.get("Hammer", 0) == 0, "Hammer must NOT co-fire on a Doji candle"
    assert result.get("Shooting Star", 0) == 0, "Shooting Star must NOT co-fire on a Doji candle"

def test_detect_hammer():
    # Hammer: small body near high, long lower shadow in downtrend
    history = [
        {"open": 105.0, "high": 106.0, "low": 104.0, "close": 104.5, "volume": 1000},
        {"open": 104.5, "high": 105.0, "low": 103.0, "close": 103.5, "volume": 1000},
        {"open": 103.5, "high": 104.0, "low": 102.0, "close": 102.2, "volume": 1000},
        {"open": 102.2, "high": 103.0, "low": 101.0, "close": 101.5, "volume": 1000},
        {"open": 101.8, "high": 102.0, "low": 98.0, "close": 101.4, "volume": 1000}
    ]
    result = detect_candlestick_patterns(history)
    assert "Hammer" in result

def test_detect_shooting_star():
    # Shooting Star: small body near low, long upper shadow in uptrend
    history = [
        {"open": 98.0, "high": 100.0, "low": 97.5, "close": 99.0, "volume": 1000},
        {"open": 99.0, "high": 101.0, "low": 98.5, "close": 100.5, "volume": 1000},
        {"open": 100.5, "high": 102.0, "low": 100.0, "close": 101.8, "volume": 1000},
        {"open": 101.8, "high": 103.0, "low": 101.5, "close": 102.8, "volume": 1000},
        {"open": 102.8, "high": 107.0, "low": 102.5, "close": 102.9, "volume": 1000}
    ]
    result = detect_candlestick_patterns(history)
    assert "Shooting Star" in result

def test_detect_engulfing():
    # Bullish Engulfing
    history = [
        {"open": 100.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1000},
        {"open": 100.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1000},
        {"open": 100.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1000},
        {"open": 100.0, "high": 101.0, "low": 98.0, "close": 99.0, "volume": 1000}, # Red
        {"open": 98.5, "high": 102.5, "low": 98.0, "close": 102.0, "volume": 1000} # Green engulfs
    ]
    result = detect_candlestick_patterns(history)
    assert "Engulfing" in result
    assert result["Engulfing"] == 100

def test_detect_doji_negative():
    # A large-body candle should NOT be labelled Doji
    history = [
        {"open": 100.0, "high": 110.0, "low": 90.0, "close": 100.05, "volume": 1000},
    ] * 4 + [
        {"open": 95.0, "high": 112.0, "low": 89.0, "close": 110.0, "volume": 1000}
    ]
    result = detect_candlestick_patterns(history)
    assert "Doji" not in result

def test_detect_bearish_engulfing():
    history = [
        {"open": 100.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1000},
        {"open": 100.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1000},
        {"open": 100.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1000},
        {"open": 99.0, "high": 103.0, "low": 98.5, "close": 102.0, "volume": 1000},  # Green
        {"open": 103.5, "high": 104.0, "low": 98.0, "close": 98.5, "volume": 1000},  # Red engulfs
    ]
    result = detect_candlestick_patterns(history)
    assert "Engulfing" in result
    assert result["Engulfing"] == -100
