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

def test_detect_chart_patterns_empty():
    from pattern_detection import detect_chart_patterns
    assert detect_chart_patterns([]) == []
    assert detect_chart_patterns([{"close": 100}] * 10) == []

def test_candle_pattern_bias():
    from pattern_detection import candle_pattern_bias
    
    # Neutral bias when empty
    assert candle_pattern_bias({}, []) == 0.0
    
    # Bullish candlestick pattern fires (Hammer is MED_BULL -> +0.4)
    assert abs(candle_pattern_bias({"Hammer": 100}, []) - 0.4) < 1e-6
    
    # Multiple bullish patterns (Morning Star HIGH_BULL (+0.6) + Hammer (+0.4) = 1.0)
    assert abs(candle_pattern_bias({"Hammer": 100, "Morning Star": 100}, []) - 1.0) < 1e-6
    
    # Bearish candlestick patterns (Shooting Star MED_BEAR -> -0.4)
    assert abs(candle_pattern_bias({"Shooting Star": -100}, []) - (-0.4)) < 1e-6
    
    # Chart pattern: Double Bottom (+ conf * 0.6 -> 0.9 * 0.6 = 0.54)
    assert abs(candle_pattern_bias({}, [{"pattern": "Double Bottom", "direction": 100, "confidence": 0.9}]) - 0.54) < 1e-6
    
    # Chart pattern: VCP (+ conf * 0.6 -> 0.8 * 0.6 = 0.48)
    assert abs(candle_pattern_bias({}, [{"pattern": "VCP", "direction": 100, "confidence": 0.8}]) - 0.48) < 1e-6
    
    # Composite bias (Hammer (+0.4) + Double Bottom (0.9 * 0.6 = 0.54) = 0.94)
    assert abs(candle_pattern_bias({"Hammer": 100}, [{"pattern": "Double Bottom", "direction": 100, "confidence": 0.9}]) - 0.94) < 1e-6

def test_detect_chart_patterns_double_bottom():
    from pattern_detection import detect_chart_patterns
    history = []
    for i in range(60):
        val = 100.0
        if i == 15:
            val = 90.0
        elif i == 30:
            val = 98.0
        elif i == 45:
            val = 90.2
        elif i > 45:
            val = 90.2 + (i - 45) * 0.5
        history.append({
            "open": val - 0.2,
            "high": val + 0.5,
            "low": val - 0.5,
            "close": val,
            "volume": 1000
        })
    results = detect_chart_patterns(history)
    assert isinstance(results, list)

def test_detect_three_black_crows():
    from pattern_detection import detect_candlestick_patterns
    history = [
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000},
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000},
        {"open": 102.0, "high": 102.2, "low": 97.8, "close": 98.0, "volume": 1000},
        {"open": 98.0, "high": 98.2, "low": 93.8, "close": 94.0, "volume": 1000},
        {"open": 94.0, "high": 94.2, "low": 89.8, "close": 90.0, "volume": 1000}
    ]
    result = detect_candlestick_patterns(history)
    assert "Three Black Crows" in result
    assert result["Three Black Crows"] == -100

def test_detect_morning_star_relaxed_gap():
    from pattern_detection import detect_candlestick_patterns
    history = [
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000},
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000},
        {"open": 100.0, "high": 101.0, "low": 95.0, "close": 96.0, "volume": 1000},
        {"open": 95.8, "high": 96.0, "low": 94.5, "close": 95.0, "volume": 1000},
        {"open": 96.2, "high": 99.5, "low": 96.0, "close": 99.0, "volume": 1000}
    ]
    result = detect_candlestick_patterns(history)
    assert "Morning Star" in result
    assert result["Morning Star"] == 100

def test_candle_pattern_bias_engulfing_collision():
    from pattern_detection import candle_pattern_bias
    candle_results = {
        "Bullish Engulfing": 100,
        "Bearish Engulfing": -100,
        "Engulfing": 100
    }
    bias = candle_pattern_bias(candle_results, [])
    assert abs(bias - 0.0) < 1e-6

def test_detect_chart_patterns_short_history():
    from pattern_detection import detect_chart_patterns
    history = [{"close": 100} for _ in range(19)]
    assert detect_chart_patterns(history) == []
