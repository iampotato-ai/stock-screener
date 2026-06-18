# pattern_detection.py (v2 — full replacement)
import numpy as np

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False


# ─────────────────────────────────────────────────────────────
# SECTION 1: Candlestick Patterns (TA-Lib + pure-Python fallback)
# ─────────────────────────────────────────────────────────────

# All 15 patterns relevant to NSE swing setups.
# Grouped by reversal type so it's easy to add/remove patterns.
_TALIB_CANDLE_FUNCTIONS = [
    # Bullish Reversals
    ("Hammer",            "talib.CDLHAMMER"),
    ("Inverted Hammer",   "talib.CDLINVERTEDHAMMER"),
    ("Bullish Engulfing", "talib.CDLENGULFING"),        # direction checked at call site
    ("Morning Star",      "talib.CDLMORNINGSTAR"),
    ("Piercing Line",     "talib.CDLPIERCING"),
    ("Three White Soldiers", "talib.CDL3WHITESOLDIERS"),
    ("Bullish Harami",    "talib.CDLHARAMI"),           # direction checked at call site
    ("Tweezer Bottom",    "talib.CDLTWEEZERBOT"),
    # Bearish Reversals
    ("Shooting Star",     "talib.CDLSHOOTINGSTAR"),
    ("Bearish Engulfing", "talib.CDLENGULFING"),        # same func, opposite sign
    ("Evening Star",      "talib.CDLEVENINGSTAR"),
    ("Three Black Crows", "talib.CDL3BLACKCROWS"),
    ("Bearish Harami",    "talib.CDLHARAMI"),           # same func, opposite sign
    ("Tweezer Top",       "talib.CDLTWEEZERTOP"),
    # Neutral / Indecision
    ("Doji",              "talib.CDLDOJI"),
]


def detect_candlestick_patterns(history):
    """
    Detects candlestick patterns on daily price history (requires at least 5 candles).
    Returns a dict of matched patterns at the latest index:
        { pattern_name: direction }   direction ∈ {100, -100}
    Unchanged public signature — fully backward-compatible.
    """
    if not history or len(history) < 5:
        return {}

    opens  = np.array([float(d["open"])  for d in history], dtype=np.float64)
    highs  = np.array([float(d["high"])  for d in history], dtype=np.float64)
    lows   = np.array([float(d["low"])   for d in history], dtype=np.float64)
    closes = np.array([float(d["close"]) for d in history], dtype=np.float64)

    if TALIB_AVAILABLE:
        res = _detect_talib(opens, highs, lows, closes)
    else:
        res = _detect_candlestick_fallback(opens, highs, lows, closes)

    if "Bullish Engulfing" in res:
        res["Engulfing"] = 100
    elif "Bearish Engulfing" in res:
        res["Engulfing"] = -100

    return res


def _detect_talib(opens, highs, lows, closes):
    results = {}
    try:
        # --- Bullish ---
        if talib.CDLHAMMER(opens, highs, lows, closes)[-1] > 0:
            results["Hammer"] = 100
        if talib.CDLINVERTEDHAMMER(opens, highs, lows, closes)[-1] > 0:
            results["Inverted Hammer"] = 100
        eng = talib.CDLENGULFING(opens, highs, lows, closes)[-1]
        if eng == 100:
            results["Bullish Engulfing"] = 100
        elif eng == -100:
            results["Bearish Engulfing"] = -100
        if talib.CDLMORNINGSTAR(opens, highs, lows, closes)[-1] > 0:
            results["Morning Star"] = 100
        if talib.CDLPIERCING(opens, highs, lows, closes)[-1] > 0:
            results["Piercing Line"] = 100
        if talib.CDL3WHITESOLDIERS(opens, highs, lows, closes)[-1] > 0:
            results["Three White Soldiers"] = 100
        harami = talib.CDLHARAMI(opens, highs, lows, closes)[-1]
        if harami == 100:
            results["Bullish Harami"] = 100
        elif harami == -100:
            results["Bearish Harami"] = -100
        if talib.CDLTWEEZERBOT(opens, highs, lows, closes)[-1] > 0:
            results["Tweezer Bottom"] = 100
        # --- Bearish ---
        if talib.CDLSHOOTINGSTAR(opens, highs, lows, closes)[-1] != 0:
            results["Shooting Star"] = -100
        if talib.CDLEVENINGSTAR(opens, highs, lows, closes)[-1] != 0:
            results["Evening Star"] = -100
        if talib.CDL3BLACKCROWS(opens, highs, lows, closes)[-1] != 0:
            results["Three Black Crows"] = -100
        if talib.CDLTWEEZERTOP(opens, highs, lows, closes)[-1] != 0:
            results["Tweezer Top"] = -100
        # --- Neutral ---
        if talib.CDLDOJI(opens, highs, lows, closes)[-1] != 0:
            results["Doji"] = 100
    except Exception:
        results = _detect_candlestick_fallback(opens, highs, lows, closes)
    return results


def _detect_candlestick_fallback(opens, highs, lows, closes):
    """
    Pure-Python fallback — extends v1 with new patterns.
    """
    results = {}
    n = len(closes)
    if n < 3:
        return results

    o0, h0, l0, c0 = opens[-1], highs[-1], lows[-1], closes[-1]
    o1, h1, l1, c1 = opens[-2], highs[-2], lows[-2], closes[-2]
    o2, h2, l2, c2 = opens[-3], highs[-3], lows[-3], closes[-3]

    body0  = abs(c0 - o0)
    body1  = abs(c1 - o1)
    body2  = abs(c2 - o2)
    range0 = h0 - l0
    if range0 <= 1e-4:
        return results

    # 1. Doji
    if body0 <= 0.1 * range0:
        results["Doji"] = 100

    # 2. Hammer
    lower_shadow = min(o0, c0) - l0
    upper_shadow = h0 - max(o0, c0)
    if lower_shadow >= 2 * body0 and upper_shadow <= 0.1 * range0 and body0 > 0:
        if c1 < c2 and c0 <= c1:
            results["Hammer"] = 100

    # 3. Shooting Star
    if (h0 - max(o0, c0)) >= 2 * body0 and (min(o0, c0) - l0) <= 0.1 * range0 and body0 > 0:
        if c1 > c2 and c0 >= c1:
            results["Shooting Star"] = -100

    # 4. Bullish Engulfing
    if c1 < o1 and c0 > o0 and o0 <= c1 and c0 >= o1 and (c0 - o0) > abs(c1 - o1) and c1 < c2:
        results["Bullish Engulfing"] = 100

    # 5. Bearish Engulfing
    if c1 > o1 and c0 < o0 and o0 >= c1 and c0 <= o1 and (o0 - c0) > abs(c1 - o1) and c1 > c2:
        results["Bearish Engulfing"] = -100

    # 6. Morning Star (3-candle)
    if (c2 < o2 and abs(c1-o1) <= 0.25*body2 and c0 > o0 and
            c0 >= (c2 + 0.5*body2) and max(o1, c1) <= min(o2, c2) * 1.005):
        results["Morning Star"] = 100

    # 7. Evening Star (3-candle)
    if (c2 > o2 and abs(c1-o1) <= 0.25*body2 and c0 < o0 and
            c0 <= (c2 - 0.5*body2) and min(o1, c1) >= max(o2, c2) * 0.995):
        results["Evening Star"] = -100

    # 8. Piercing Line
    # Prior day bearish; today opens below prior low, closes above midpoint of prior body
    if n >= 2:
        prior_mid = (o1 + c1) / 2
        if c1 < o1 and o0 < l1 and c0 > prior_mid and c0 < o1:
            results["Piercing Line"] = 100

    # 9. Three White Soldiers — simplified: 3 consecutive bullish closes, each > prev close
    if n >= 3:
        if (c0 > c1 > c2 and
                c0 > o0 and c1 > o1 and c2 > o2 and
                abs(c0-o0) > 0.5*(h0-l0) and abs(c1-o1) > 0.5*(h1-l1)):
            results["Three White Soldiers"] = 100

    # 10. Bullish Harami
    if c1 < o1 and c0 > o0 and o0 > c1 and c0 < o1 and body0 < 0.5 * body1:
        results["Bullish Harami"] = 100

    # 11. Three Black Crows
    if n >= 3:
        if (c0 < c1 < c2 and
                c0 < o0 and c1 < o1 and c2 < o2 and
                abs(c0 - o0) > 0.5 * (h0 - l0) and abs(c1 - o1) > 0.5 * (h1 - l1)):
            results["Three Black Crows"] = -100

    return results


# ─────────────────────────────────────────────────────────────
# SECTION 2: Chart Structure Patterns (pure-Python, no TA-Lib dep)
# ─────────────────────────────────────────────────────────────

def detect_chart_patterns(history, lookback=60):
    """
    Detects higher-order chart structures from OHLCV history.

    Parameters
    ----------
    history  : list of dicts with keys open/high/low/close/volume
    lookback : int  number of recent candles to analyse (default 60)

    Returns
    -------
    list of dicts:
        [{ "pattern": str, "direction": int (100/-100),
           "confidence": float (0-1), "start_idx": int, "end_idx": int,
           "description": str }]
    """
    if not history or len(history) < 20:
        return []

    data = history[-lookback:]
    closes = np.array([float(d["close"]) for d in data])
    highs  = np.array([float(d["high"])  for d in data])
    lows   = np.array([float(d["low"])   for d in data])
    vols   = np.array([float(d.get("volume", 0) or 0) for d in data])
    n = len(closes)

    found = []
    found += _detect_double_top(highs, closes, n)
    found += _detect_double_bottom(lows, closes, n)
    found += _detect_vcp(highs, lows, closes, vols, n)
    found += _detect_bull_flag(highs, lows, closes, vols, n)
    return found


# ── Double Top ──────────────────────────────────────────────

def _detect_double_top(highs, closes, n, tolerance=0.03):
    """
    Two swing highs within `tolerance` of each other, followed by a close
    below the trough between them (neckline break).
    """
    results = []
    peaks = _find_swing_highs(highs, window=5)
    if len(peaks) < 2:
        return results

    p1_idx, p2_idx = peaks[-2], peaks[-1]
    p1, p2 = highs[p1_idx], highs[p2_idx]

    if abs(p1 - p2) / max(p1, p2) > tolerance:
        return results

    # Neckline = trough between the two peaks
    trough_region = closes[p1_idx:p2_idx]
    if len(trough_region) == 0:
        return results
    neckline = trough_region.min()

    # Pattern confirmed if latest close breaks neckline
    if closes[-1] < neckline:
        conf = 1 - abs(p1 - p2) / max(p1, p2) / tolerance
        results.append({
            "pattern": "Double Top",
            "direction": -100,
            "confidence": round(min(conf, 0.95), 2),
            "start_idx": p1_idx,
            "end_idx": n - 1,
            "description": f"Two peaks near {p1:.2f}/{p2:.2f}; neckline {neckline:.2f} broken"
        })
    return results


# ── Double Bottom ────────────────────────────────────────────

def _detect_double_bottom(lows, closes, n, tolerance=0.03):
    """Mirror of Double Top — two swing lows within tolerance, neckline breakout."""
    results = []
    troughs = _find_swing_lows(lows, window=5)
    if len(troughs) < 2:
        return results

    t1_idx, t2_idx = troughs[-2], troughs[-1]
    t1, t2 = lows[t1_idx], lows[t2_idx]

    if abs(t1 - t2) / max(t1, t2) > tolerance:
        return results

    peak_region = closes[t1_idx:t2_idx]
    if len(peak_region) == 0:
        return results
    neckline = peak_region.max()

    if closes[-1] > neckline:
        conf = 1 - abs(t1 - t2) / max(t1, t2) / tolerance
        results.append({
            "pattern": "Double Bottom",
            "direction": 100,
            "confidence": round(min(conf, 0.95), 2),
            "start_idx": t1_idx,
            "end_idx": n - 1,
            "description": f"Two troughs near {t1:.2f}/{t2:.2f}; neckline {neckline:.2f} broken"
        })
    return results


# ── Volatility Contraction Pattern (VCP) ────────────────────

def _detect_vcp(highs, lows, closes, vols, n, min_contractions=2):
    """
    Simplified VCP: price range and volume each contract across at least
    `min_contractions` successive pivot swings within the last 30 bars.
    Returns bullish signal when the latest close is near the pivot high
    and volume is below 10-day average.
    """
    results = []
    if n < 20:
        return results

    segment = 30
    h_seg = highs[-segment:]
    l_seg = lows[-segment:]
    v_seg = vols[-segment:]
    c_seg = closes[-segment:]

    chunk = max(segment // 5, 4)
    ranges = []
    avg_vols = []
    for i in range(0, segment, chunk):
        end = min(i + chunk, segment)
        ranges.append(h_seg[i:end].max() - l_seg[i:end].min())
        avg_vols.append(v_seg[i:end].mean())

    # Check monotone contraction across at least min_contractions steps
    contractions = sum(
        1 for i in range(1, len(ranges)) if ranges[i] < ranges[i-1] * 0.9
    )
    vol_contractions = sum(
        1 for i in range(1, len(avg_vols)) if avg_vols[i] < avg_vols[i-1] * 0.95
    )

    if contractions >= min_contractions and vol_contractions >= min_contractions:
        pivot_high = h_seg.max()
        latest_close = c_seg[-1]
        near_pivot = (pivot_high - latest_close) / pivot_high < 0.05
        vol_dry = len(avg_vols) > 0 and avg_vols[-1] < np.mean(avg_vols) * 0.7

        if near_pivot and vol_dry:
            conf = min(0.55 + contractions * 0.1, 0.90)
            results.append({
                "pattern": "VCP",
                "direction": 100,
                "confidence": round(conf, 2),
                "start_idx": n - segment,
                "end_idx": n - 1,
                "description": (
                    f"{contractions} range contractions + {vol_contractions} vol contractions; "
                    f"pivot high {pivot_high:.2f}, close {latest_close:.2f}"
                )
            })
    return results


# ── Bull Flag ────────────────────────────────────────────────

def _detect_bull_flag(highs, lows, closes, vols, n, pole_min_gain=0.08):
    """
    Bull Flag: a sharp pole (>=8% gain in <=10 bars) followed by a tight,
    slightly-down-sloping flag consolidation on declining volume, then a
    breakout above the flag's upper trendline.
    """
    results = []
    if n < 15:
        return results

    # Find pole: scan last 25 bars for a 10-bar window with >=8% gain
    pole_end = None
    pole_start = None
    for end in range(n - 1, max(n - 25, 10), -1):
        start = max(end - 10, 0)
        gain = (closes[end] - closes[start]) / closes[start]
        if gain >= pole_min_gain:
            pole_start = start
            pole_end = end
            break

    if pole_end is None or n - pole_end < 5:
        return results

    # Flag body: bars after pole top
    flag_closes = closes[pole_end:]
    flag_highs  = highs[pole_end:]
    flag_vols   = vols[pole_end:]

    flag_range = flag_highs.max() - flag_closes.min()
    pole_range = closes[pole_end] - closes[pole_start]

    # Flag height should be < 50% of pole
    if flag_range > 0.5 * pole_range:
        return results

    # Volume should be declining in flag
    half = len(flag_vols) // 2
    if half == 0:
        return results
    vol_decline = flag_vols[:half].mean() > flag_vols[half:].mean()

    # Breakout: latest close above flag high
    breakout = closes[-1] >= flag_highs.max()

    if vol_decline and breakout:
        conf = min(0.60 + (pole_range / closes[pole_start]) * 0.5, 0.92)
        results.append({
            "pattern": "Bull Flag",
            "direction": 100,
            "confidence": round(conf, 2),
            "start_idx": pole_start,
            "end_idx": n - 1,
            "description": (
                f"Pole +{(closes[pole_end]-closes[pole_start])/closes[pole_start]*100:.1f}% "
                f"({pole_start}->{pole_end}); flag breakout at {closes[-1]:.2f}"
            )
        })
    return results


# ─────────────────────────────────────────────────────────────
# SECTION 3: Helpers
# ─────────────────────────────────────────────────────────────

def _find_swing_highs(highs, window=5):
    """Return indices of local maxima with given window."""
    peaks = []
    n = len(highs)
    for i in range(window, n - window):
        if highs[i] == max(highs[i - window: i + window + 1]):
            peaks.append(i)
    return peaks


def _find_swing_lows(lows, window=5):
    """Return indices of local minima with given window."""
    troughs = []
    n = len(lows)
    for i in range(window, n - window):
        if lows[i] == min(lows[i - window: i + window + 1]):
            troughs.append(i)
    return troughs


# ─────────────────────────────────────────────────────────────
# SECTION 4: Bias helper for Kronos T_val adjustment
# ─────────────────────────────────────────────────────────────

def candle_pattern_bias(candle_results: dict, chart_results: list) -> float:
    """
    Returns a bias float in [-1.0, +1.0] summarising all detected patterns.
    Intended to be multiplied by a small constant (e.g. 0.05) and added to
    Kronos T_val before ensemble aggregation.

    Scoring:
      High-conviction bullish  (Morning Star, Three White Soldiers, VCP, Bull Flag) -> +0.6
      Medium bullish           (Hammer, Engulfing, Piercing, Double Bottom)          -> +0.4
      Low bullish              (Inverted Hammer, Bullish Harami, Tweezer Bottom)     -> +0.2
      High-conviction bearish  (Evening Star, Three Black Crows, Double Top)         -> -0.6
      Medium bearish           (Shooting Star, Bearish Engulfing)                    -> -0.4
      Low bearish              (Bearish Harami, Tweezer Top)                         -> -0.2
      Neutral                  (Doji)                                                 -> 0.0
    """
    HIGH_BULL  = {"Morning Star", "Three White Soldiers"}
    MED_BULL   = {"Hammer", "Bullish Engulfing", "Piercing Line"}
    LOW_BULL   = {"Inverted Hammer", "Bullish Harami", "Tweezer Bottom"}
    HIGH_BEAR  = {"Evening Star", "Three Black Crows"}
    MED_BEAR   = {"Shooting Star", "Bearish Engulfing"}
    LOW_BEAR   = {"Bearish Harami", "Tweezer Top"}

    total = 0.0
    for name, val in candle_results.items():
        if name in HIGH_BULL and val > 0:    total += 0.6
        elif name in MED_BULL and val > 0:   total += 0.4
        elif name in LOW_BULL and val > 0:   total += 0.2
        elif name in HIGH_BEAR and val < 0:  total -= 0.6
        elif name in MED_BEAR and val < 0:   total -= 0.4
        elif name in LOW_BEAR and val < 0:   total -= 0.2
        elif name == "Engulfing":
            if "Bullish Engulfing" not in candle_results and "Bearish Engulfing" not in candle_results:
                total += 0.4 if val > 0 else -0.4

    for cp in chart_results:
        pname = cp.get("pattern", "")
        conf  = cp.get("confidence", 0.5)
        if pname in ("VCP", "Bull Flag", "Double Bottom"):
            total += conf * 0.6
        elif pname == "Double Top":
            total -= conf * 0.6

    # Clamp to [-1, +1]
    return max(-1.0, min(1.0, total))
