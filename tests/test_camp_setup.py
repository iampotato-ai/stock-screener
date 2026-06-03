import pytest
import sys
import os

# Ensure the root folder is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import classify_technical_pattern, classify_setup

def test_stage_2_camp_detection():
    # Construct a 75-day history list to have plenty of baseline volume days
    history = []
    # Day 0 to 59: Stage 1 run starting from close=100 up to 153
    # Day 60 to 74 (last 15 days): Consolidation (The Camp)
    
    for i in range(75):
        # Default baseline values
        open_val = 150.0
        high_val = 150.5
        low_val = 149.5
        close_val = 150.0
        volume_val = 1000
        
        # Preceding stage 1 low around day 30 (index 30)
        if i == 30:
            low_val = 100.0
            close_val = 101.0
            
        # Consolidation high at index 63 (inside last 15 days)
        if i == 63:
            high_val = 153.0
            
        # Institutional Days inside the leg-up (between day 30 and 60)
        # e.g., index 35 and 45
        if i in [35, 45]:
            open_val = 140.0
            high_val = 152.0
            low_val = 138.0
            close_val = 150.0
            volume_val = 2000  # volume spike >= 1.6x baseline (1.6 * 1000 = 1600)
            
        # Ensure last 4 days have a high close to flag_high (>= 149.94)
        if i >= 71:
            high_val = 150.5
            low_val = 149.5
            close_val = 150.0
            volume_val = 400  # low volume for dryup (average < 60% AND at least 1 day < 50%)
            
        # Days -12 to -5 (indices 63 to 70): lower lows to ensure min(lows[-4:]) > min(lows[-12:-4])
        if 63 <= i <= 70:
            low_val = 145.0
            high_val = 147.0
            close_val = 146.0
            
        history.append({
            "date": f"2026-05-{i+1:02d}",
            "open": open_val,
            "high": high_val,
            "low": low_val,
            "close": close_val,
            "volume": volume_val
        })

    # Run the technical pattern classifier
    pattern_res = classify_technical_pattern(history)
    assert pattern_res is not None
    assert pattern_res["pattern"] == "Stage 2 Camp"
    assert "A" in pattern_res["grade"]

    # Now verify overlay via classify_setup
    stock = {
        "name": "TESTCAMP",
        "close": 150.0,
        "price_52_week_high": 155.0,
        "relative_volume": 0.5,
        "swingband": "elite",
        "ims_band": "strong",
        "is_inside_bar": False,
        "Perf.1M": 10.0,
        "Perf.W": 2.0,
        "SMA50": 140.0,
        "SMA21": 145.0,
        "days_in_scan": 2,
        "sector": "Technology",
        "pattern_name": pattern_res["pattern"],
        "pattern_grade": pattern_res["grade"]
    }
    
    setup_res = classify_setup(stock)
    assert setup_res["setupLabel"].startswith("Stage 2 Camp")
    assert setup_res["setupConfidence"] == 95
    assert "Stage 2 Camp" in setup_res["setupTags"]

def test_candlestick_priority_classification():
    from unittest.mock import patch
    history = [
        {"open": 100.0, "high": 125.0, "low": 75.0, "close": 100.0, "volume": 1000}
        for _ in range(42)
    ]
    
    # Mock same strength (100): Hammer (priority 4) wins over Doji (priority 1)
    with patch("app.pattern_detection.detect_candlestick_patterns") as mock_detect:
        mock_detect.return_value = {"Doji": 100, "Hammer": 100}
        res = classify_technical_pattern(history)
        assert res["pattern"] == "Hammer"
        assert res["grade"] == "B+"
    
    # Mock different strength: Doji (strength 200) wins over Hammer (strength 100) due to absolute strength
    with patch("app.pattern_detection.detect_candlestick_patterns") as mock_detect2:
        mock_detect2.return_value = {"Doji": 200, "Hammer": 100}
        res2 = classify_technical_pattern(history)
        assert res2["pattern"] == "Doji"
        assert res2["grade"] == "B"
