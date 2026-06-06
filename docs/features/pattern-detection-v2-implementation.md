# Pattern Detection v2 — Full Implementation Plan

> **Scope:** Extend the existing `pattern_detection.py` (TA-Lib + fallback, 6 candle patterns) to a full
> pattern intelligence layer: 15 TA-Lib candlestick patterns, 4 chart-level structure patterns (Double
> Top/Bottom, VCP, Bull Flag), a persistent `pattern_signals` DB table, a new REST endpoint, JS chip
> rendering in the workspace drawer, and a Kronos `T_val` bias adjustment.
>
> All changes are **backward-compatible** — the `TALIB_AVAILABLE` guard already present in
> `pattern_detection.py` is reused throughout.

---

## 0. Current State Audit

| File | What exists today |
|---|---|
| `pattern_detection.py` | TA-Lib guard, `detect_candlestick_patterns()` with 6 patterns (Hammer, Engulfing, Morning Star, Evening Star, Doji, Shooting Star), `_detect_candlestick_fallback()` |
| `app.py` → `init_db()` | `pattern_cache` table (ticker, generated_at, pattern_name, pattern_grade, pattern_desc, candlestick_json) |
| `app.py` → `classify_setup()` | Reads `stock.get("pattern_name")` and `stock.get("pattern_grade")` to override `setupLabel` |
| `forecast_math.py` | `compute_forecast_metrics()` — exposes `T_val` used by Kronos ensemble |

**Gap:** Only 6 of ~15 swing-relevant candle patterns are detected; no chart-structure patterns; no
dedicated API endpoint; candle results stored as raw JSON blob without per-signal rows; no Kronos
feedback loop.

---

## Phase 1 — Expand `pattern_detection.py`

Replace the current file content entirely. The new version is a strict superset — all existing
function signatures are preserved.

```python
# pattern_detection.py  (v2 — full replacement)
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
        return _detect_talib(opens, highs, lows, closes)
    return _detect_candlestick_fallback(opens, highs, lows, closes)


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
    Pure-Python fallback — unchanged from v1 plus 3 new patterns.
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
            c0 >= (c2 + 0.5*body2) and max(o1, c1) < min(o2, c2)):
        results["Morning Star"] = 100

    # 7. Evening Star (3-candle)
    if (c2 > o2 and abs(c1-o1) <= 0.25*body2 and c0 < o0 and
            c0 <= (c2 - 0.5*body2) and min(o1, c1) > max(o2, c2)):
        results["Evening Star"] = -100

    # 8. Piercing Line (NEW)
    # Prior day bearish; today opens below prior low, closes above midpoint of prior body
    if n >= 2:
        prior_mid = (o1 + c1) / 2
        if c1 < o1 and o0 < l1 and c0 > prior_mid and c0 < o1:
            results["Piercing Line"] = 100

    # 9. Three White Soldiers (NEW) — simplified: 3 consecutive bullish closes, each > prev close
    if n >= 3:
        if (c0 > c1 > c2 and
                c0 > o0 and c1 > o1 and c2 > o2 and
                abs(c0-o0) > 0.5*(h0-l0) and abs(c1-o1) > 0.5*(h1-l1)):
            results["Three White Soldiers"] = 100

    # 10. Bullish Harami (NEW)
    if c1 < o1 and c0 > o0 and o0 > c1 and c0 < o1 and body0 < 0.5 * body1:
        results["Bullish Harami"] = 100

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
        vol_dry = avg_vols and avg_vols[-1] < np.mean(avg_vols) * 0.7

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
    for name in candle_results:
        if name in HIGH_BULL:   total += 0.6
        elif name in MED_BULL:  total += 0.4
        elif name in LOW_BULL:  total += 0.2
        elif name in HIGH_BEAR: total -= 0.6
        elif name in MED_BEAR:  total -= 0.4
        elif name in LOW_BEAR:  total -= 0.2

    for cp in chart_results:
        pname = cp.get("pattern", "")
        conf  = cp.get("confidence", 0.5)
        if pname in ("VCP", "Bull Flag", "Double Bottom"):
            total += conf * 0.6
        elif pname == "Double Top":
            total -= conf * 0.6

    # Clamp to [-1, +1]
    return max(-1.0, min(1.0, total))
```

---

## Phase 2 — DB Migration: `pattern_signals` Table

Add this block inside `init_db()` in `app.py`, **after** the existing `pattern_cache` table creation:

```python
# ---------- pattern_signals (Phase 2 addition) ----------
c.execute('''
    CREATE TABLE IF NOT EXISTS pattern_signals (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker      TEXT NOT NULL,
        timeframe   TEXT NOT NULL DEFAULT 'D',
        signal_type TEXT NOT NULL,           -- 'candle' | 'chart'
        pattern     TEXT NOT NULL,
        direction   INTEGER NOT NULL,        -- 100 bullish, -100 bearish
        confidence  REAL,                    -- 0.0-1.0 (chart patterns only)
        description TEXT,
        detected_at TEXT NOT NULL,
        bar_date    TEXT                     -- date of the last bar in the signal
    )
''')
# Index for fast per-ticker lookups
c.execute('''
    CREATE INDEX IF NOT EXISTS idx_pattern_signals_ticker
    ON pattern_signals (ticker, detected_at DESC)
''')
try:
    c.execute("ALTER TABLE pattern_signals ADD COLUMN bar_date TEXT")
except Exception:
    pass  # already exists
```

---

## Phase 3 — Persistence Helper

Add this function to `app.py` (place it near `compute_extra_fields`):

```python
import pattern_detection  # already imported at top of app.py

def persist_pattern_signals(ticker: str, candle_results: dict,
                             chart_results: list, bar_date: str = None):
    """
    Write detected patterns for a ticker into pattern_signals table.
    Clears today's rows for the ticker first to avoid duplicates.
    """
    now   = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    today = datetime.utcnow().strftime("%Y-%m-%d")

    conn = sqlite3.connect('scan_history.db')
    c = conn.cursor()

    # Remove today's signals for this ticker to avoid duplication on re-scans
    c.execute(
        "DELETE FROM pattern_signals WHERE ticker = ? AND detected_at LIKE ?",
        (ticker, f"{today}%")
    )

    # Insert candle signals
    for pat_name, direction in candle_results.items():
        c.execute('''
            INSERT INTO pattern_signals
                (ticker, timeframe, signal_type, pattern, direction,
                 confidence, description, detected_at, bar_date)
            VALUES (?, 'D', 'candle', ?, ?, NULL, NULL, ?, ?)
        ''', (ticker, pat_name, direction, now, bar_date or today))

    # Insert chart signals
    for cp in chart_results:
        c.execute('''
            INSERT INTO pattern_signals
                (ticker, timeframe, signal_type, pattern, direction,
                 confidence, description, detected_at, bar_date)
            VALUES (?, 'D', 'chart', ?, ?, ?, ?, ?, ?)
        ''', (
            ticker,
            cp.get("pattern"),
            cp.get("direction"),
            cp.get("confidence"),
            cp.get("description"),
            now,
            bar_date or today
        ))

    conn.commit()
    conn.close()
```

---

## Phase 4 — Wire into `analyze_single_stock`

Locate the section in `app.py` where `pattern_detection` is called and extend it:

```python
# ── BEFORE (existing call) ──────────────────────────────────
candlestick_results = pattern_detection.detect_candlestick_patterns(history)

# ── AFTER (v2 replacement block) ────────────────────────────
candlestick_results = pattern_detection.detect_candlestick_patterns(history)
chart_results       = pattern_detection.detect_chart_patterns(history, lookback=60)

# Persist signals (never let DB write crash the scan)
bar_date = history[-1].get("date") if history else None
try:
    persist_pattern_signals(ticker, candlestick_results, chart_results, bar_date)
except Exception:
    pass

# Compute Kronos bias adjustment (used in Phase 6)
pattern_bias = pattern_detection.candle_pattern_bias(candlestick_results, chart_results)
stock["pattern_bias"] = pattern_bias

# Merge best chart pattern into stock dict for classify_setup()
if chart_results:
    best = max(chart_results, key=lambda x: x.get("confidence", 0))
    if not stock.get("pattern_name") or stock.get("pattern_name") == "Trend Continuation":
        stock["pattern_name"]  = best["pattern"]
        stock["pattern_grade"] = "A+" if best["confidence"] >= 0.85 else "A"
        stock["pattern_desc"]  = best["description"]
```

---

## Phase 5 — New REST Endpoint `/api/pattern-signals`

Add this route to `app.py`:

```python
@app.route('/api/pattern-signals')
def get_pattern_signals():
    """
    GET /api/pattern-signals?ticker=RELIANCE&days=7&type=candle

    Query params:
      ticker  (required) — NSE ticker
      days    (optional, default 7) — lookback in days
      type    (optional) — 'candle' | 'chart' | omit for both
    """
    ticker = request.args.get('ticker', '').upper().strip()
    if not ticker:
        return jsonify({"error": "ticker is required"}), 400

    days     = int(request.args.get('days', 7))
    sig_type = request.args.get('type', None)
    since    = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = sqlite3.connect('scan_history.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query  = "SELECT * FROM pattern_signals WHERE ticker = ? AND detected_at >= ?"
    params = [ticker, since]

    if sig_type in ('candle', 'chart'):
        query  += " AND signal_type = ?"
        params.append(sig_type)

    query += " ORDER BY detected_at DESC LIMIT 100"
    rows   = c.execute(query, params).fetchall()
    conn.close()

    return jsonify({
        "ticker":  ticker,
        "days":    days,
        "count":   len(rows),
        "signals": [dict(r) for r in rows]
    })
```

---

## Phase 6 — Kronos `T_val` Bias Adjustment

In `forecast_math.py`, add `extra_context=None` as a kwarg to `compute_forecast_metrics` and apply
the nudge after `T_val` is assembled:

```python
# Inside compute_forecast_metrics(... , extra_context=None):
pattern_bias = (extra_context or {}).get("pattern_bias", 0.0)
T_val = T_val + pattern_bias * 0.05   # max ±0.05 nudge — conservative until backtested
```

In `app.py`, pass `pattern_bias` at the call site:

```python
forecast_result = compute_forecast_metrics(
    ticker=ticker,
    history=history,
    # ... existing kwargs ...
    extra_context={"pattern_bias": stock.get("pattern_bias", 0.0)}
)
```

---

## Phase 7 — JS Chip Rendering (Workspace Drawer)

### JavaScript

```javascript
// pattern chip renderer
function renderPatternChips(patternSignals) {
  if (!patternSignals || patternSignals.length === 0) return '';

  const dirLabel = (d) => d === 100 ? 'bull' : d === -100 ? 'bear' : 'neutral';
  const dirIcon  = (d) => d === 100 ? '▲' : d === -100 ? '▼' : '◆';

  // Deduplicate by pattern name (keep most recent)
  const seen = new Map();
  patternSignals.forEach(s => { if (!seen.has(s.pattern)) seen.set(s.pattern, s); });

  const chips = [...seen.values()].map(s => `
    <span class="pattern-chip pattern-chip--${dirLabel(s.direction)}"
          title="${s.description || s.pattern}">
      ${dirIcon(s.direction)} ${s.pattern}
      ${s.confidence != null
        ? `<span class="pattern-chip__conf">${Math.round(s.confidence * 100)}%</span>`
        : ''}
    </span>
  `).join('');

  return `<div class="pattern-chips-row">${chips}</div>`;
}

async function loadPatternSignals(ticker, containerEl) {
  try {
    const res  = await fetch(`/api/pattern-signals?ticker=${ticker}&days=3`);
    const data = await res.json();
    containerEl.innerHTML = data.signals && data.signals.length > 0
      ? renderPatternChips(data.signals)
      : '<span class="no-patterns">No patterns detected</span>';
  } catch (e) {
    containerEl.innerHTML = '';
  }
}

// Wire to your drawer open event — adjust selector to match your actual handler:
// document.addEventListener('draweropen', (e) => {
//   const chipBox = document.querySelector('#pattern-chips-container');
//   if (chipBox) loadPatternSignals(e.detail.ticker, chipBox);
// });
```

### CSS

```css
.pattern-chips-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0;
}

.pattern-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 99px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  cursor: default;
  user-select: none;
}

.pattern-chip--bull    { background: rgba(67,122,34,0.15);  color: #437a22; border: 1px solid rgba(67,122,34,0.35); }
.pattern-chip--bear    { background: rgba(161,44,123,0.12); color: #a12c7b; border: 1px solid rgba(161,44,123,0.30); }
.pattern-chip--neutral { background: rgba(122,121,116,0.10); color: #7a7974; border: 1px solid rgba(122,121,116,0.25); }

.pattern-chip__conf {
  opacity: 0.7;
  font-weight: 400;
  font-size: 10px;
}

.no-patterns {
  font-size: 12px;
  color: var(--color-text-faint, #bab9b4);
}
```

### HTML (inside drawer)

```html
<!-- After setupLabel row in the stock detail drawer -->
<div class="drawer-row">
  <span class="drawer-label">Patterns</span>
  <div id="pattern-chips-container"></div>
</div>
```

---

## Checklist

### Phase 1 — `pattern_detection.py`
- [ ] Replace file with v2 content above (15 TA-Lib candle patterns + 4 chart patterns)
- [ ] Verify `_detect_talib` handles exceptions and falls through to fallback
- [ ] Smoke test: `python -c "import pattern_detection; print('OK')"`

### Phase 2 — DB Migration
- [ ] Add `pattern_signals` table + index inside `init_db()`
- [ ] Start app once to auto-migrate; verify: `sqlite3 scan_history.db ".tables"`

### Phase 3 — Persistence
- [ ] Add `persist_pattern_signals()` to `app.py`

### Phase 4 — `analyze_single_stock` wiring
- [ ] Replace single candle call with v2 block (candle + chart + bias + merge)

### Phase 5 — REST endpoint
- [ ] Add `/api/pattern-signals` route
- [ ] Test: `curl "http://localhost:5000/api/pattern-signals?ticker=RELIANCE&days=7"`

### Phase 6 — Kronos bias
- [ ] Add `extra_context=None` kwarg to `compute_forecast_metrics`
- [ ] Apply `T_val += pattern_bias * 0.05`
- [ ] Pass `pattern_bias` from call site in `app.py`

### Phase 7 — Frontend chips
- [ ] Add JS functions to workspace JS file
- [ ] Add CSS chips styles to main stylesheet
- [ ] Add `#pattern-chips-container` div inside drawer HTML
- [ ] Wire `loadPatternSignals` to drawer open event

---

## Testing Commands

```bash
# 1. Confirm TA-Lib is available
python -c "import talib; print(talib.__version__)"

# 2. Smoke test all new functions
python - <<'EOF'
import json, pattern_detection
history = [
    {"open":100,"high":105,"low":98, "close":104,"volume":100000},
    {"open":104,"high":108,"low":103,"close":106,"volume":120000},
    {"open":106,"high":110,"low":105,"close":108,"volume":90000},
    {"open":108,"high":112,"low":107,"close":111,"volume":80000},
    {"open":111,"high":113,"low":109,"close":110,"volume":60000},
    {"open":110,"high":111,"low":105,"close":106,"volume":50000},
    {"open":106,"high":107,"low":102,"close":103,"volume":45000},
]
candles = pattern_detection.detect_candlestick_patterns(history)
charts  = pattern_detection.detect_chart_patterns(history)
bias    = pattern_detection.candle_pattern_bias(candles, charts)
print("Candles:", json.dumps(candles, indent=2))
print("Charts: ", json.dumps(charts,  indent=2))
print("Bias:   ", bias)
EOF

# 3. Verify DB schema after first app start
sqlite3 scan_history.db ".schema pattern_signals"

# 4. Test REST endpoint
curl -s "http://localhost:5000/api/pattern-signals?ticker=RELIANCE&days=7" | python -m json.tool
```

---

## Notes

- **`detect_candlestick_patterns()` public signature is unchanged** — no existing callers break.
- Chart patterns silently return `[]` when `len(history) < 20`.
- `persist_pattern_signals()` is wrapped in `try/except` at the call site — a DB write failure
  never crashes a scan.
- The Kronos `T_val` nudge is capped at `±0.05` (conservative) until signal quality is validated
  over a full backtest window.
- VCP and Bull Flag are pure-Python (no vendor dependency). Once you add
  `BennyThadikaran/stock-pattern` as a git submodule, replace `_detect_vcp` and `_detect_bull_flag`
  bodies with library calls while keeping the same return schema.
