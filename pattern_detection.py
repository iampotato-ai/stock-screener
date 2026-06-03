import numpy as np

# Try importing TA-Lib, otherwise fallback to pure-python candlestick detection
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False

def detect_candlestick_patterns(history):
    """
    Detects candlestick patterns on daily price history (requires at least 5 candles).
    Returns a dictionary of matched patterns at the latest index: {pattern_name: direction}
    direction: 100 for bullish, -100 for bearish, 0 for neutral
    """
    if not history or len(history) < 5:
        return {}

    opens = np.array([float(day["open"]) for day in history], dtype=np.float64)
    highs = np.array([float(day["high"]) for day in history], dtype=np.float64)
    lows = np.array([float(day["low"]) for day in history], dtype=np.float64)
    closes = np.array([float(day["close"]) for day in history], dtype=np.float64)

    results = {}

    if TALIB_AVAILABLE:
        try:
            # 1. Hammer (Bullish Reversal)
            hammer = talib.CDLHAMMER(opens, highs, lows, closes)
            if hammer[-1] != 0:
                results["Hammer"] = int(hammer[-1])

            # 2. Engulfing (Bullish/Bearish Reversal)
            engulfing = talib.CDLENGULFING(opens, highs, lows, closes)
            if engulfing[-1] != 0:
                results["Engulfing"] = int(engulfing[-1])

            # 3. Morning Star (Bullish Reversal)
            morning = talib.CDLMORNINGSTAR(opens, highs, lows, closes)
            if morning[-1] != 0:
                results["Morning Star"] = int(morning[-1])

            # 4. Evening Star (Bearish Reversal)
            evening = talib.CDLEVENINGSTAR(opens, highs, lows, closes)
            if evening[-1] != 0:
                results["Evening Star"] = int(evening[-1])

            # 5. Doji (Neutral/Consolidation)
            doji = talib.CDLDOJI(opens, highs, lows, closes)
            if doji[-1] != 0:
                results["Doji"] = 100  # Map to positive signal

            # 6. Shooting Star (Bearish Reversal)
            shooting = talib.CDLSHOOTINGSTAR(opens, highs, lows, closes)
            if shooting[-1] != 0:
                results["Shooting Star"] = int(shooting[-1])
        except Exception:
            # Fallback in case of runtime failure
            results = _detect_candlestick_fallback(opens, highs, lows, closes)
    else:
        results = _detect_candlestick_fallback(opens, highs, lows, closes)

    return results

def _detect_candlestick_fallback(opens, highs, lows, closes):
    """
    Pure-python implementation of major candlestick patterns.
    """
    results = {}
    n = len(closes)
    if n < 3:
        return results

    # Get latest candles (index -1, -2, -3)
    o0, h0, l0, c0 = opens[-1], highs[-1], lows[-1], closes[-1]
    o1, h1, l1, c1 = opens[-2], highs[-2], lows[-2], closes[-2]
    o2, h2, l2, c2 = opens[-3], highs[-3], lows[-3], closes[-3]

    body0 = abs(c0 - o0)
    range0 = h0 - l0
    if range0 == 0:
        range0 = 1e-5

    # 1. Doji (Neutral)
    if body0 <= 0.1 * range0:
        results["Doji"] = 100

    # 2. Hammer (Bullish Reversal in Downtrend)
    lower_shadow = min(o0, c0) - l0
    upper_shadow = h0 - max(o0, c0)
    # Hammer shape
    is_hammer_shape = lower_shadow >= 2 * body0 and upper_shadow <= 0.1 * range0 and body0 > 0
    # Short-term downtrend proxy (price trending lower on last 3 days)
    is_downtrend = c1 < c2 or c0 < c1
    if is_hammer_shape and is_downtrend:
        results["Hammer"] = 100

    # 3. Shooting Star (Bearish Reversal in Uptrend)
    upper_shadow0 = h0 - max(o0, c0)
    lower_shadow0 = min(o0, c0) - l0
    is_star_shape = upper_shadow0 >= 2 * body0 and lower_shadow0 <= 0.1 * range0 and body0 > 0
    is_uptrend = c1 > c2 or c0 > c1
    if is_star_shape and is_uptrend:
        results["Shooting Star"] = -100

    # 4. Bullish Engulfing (Bullish Reversal)
    is_prev_bearish = c1 < o1
    is_curr_bullish = c0 > o0
    is_engulfing_bull = o0 <= c1 and c0 >= o1 and (c0 - o0) > abs(c1 - o1)
    if is_prev_bearish and is_curr_bullish and is_engulfing_bull and is_downtrend:
        results["Engulfing"] = 100

    # 5. Bearish Engulfing (Bearish Reversal)
    is_prev_bullish = c1 > o1
    is_curr_bearish = c0 < o0
    is_engulfing_bear = o0 >= c1 and c0 <= o1 and (o0 - c0) > abs(c1 - o1)
    if is_prev_bullish and is_curr_bearish and is_engulfing_bear and is_uptrend:
        results["Engulfing"] = -100

    # 6. Morning Star (Bullish Reversal - 3 candles)
    body2 = abs(c2 - o2)
    body1 = abs(c1 - o1)
    is_c2_bearish = c2 < o2
    is_c1_small = body1 <= 0.25 * body2
    is_c0_bullish = c0 > o0
    is_c0_halfway = c0 >= (c2 + 0.5 * body2)
    # Gap down on star body
    is_gap_down = max(o1, c1) < c2
    if is_c2_bearish and is_c1_small and is_c0_bullish and is_c0_halfway and is_gap_down:
        results["Morning Star"] = 100

    # 7. Evening Star (Bearish Reversal - 3 candles)
    is_c2_bullish = c2 > o2
    is_c1_small_star = body1 <= 0.25 * body2
    is_c0_bearish = c0 < o0
    is_c0_halfway_down = c0 <= (c2 - 0.5 * body2)
    # Gap up on star body
    is_gap_up = min(o1, c1) > c2
    if is_c2_bullish and is_c1_small_star and is_c0_bearish and is_c0_halfway_down and is_gap_up:
        results["Evening Star"] = -100

    return results
