
# Pattern Detection Integration: TA-Lib + stock-pattern

> **Feature Branch Recommendation:** `feature/pattern-detection`  
> **Touches:** `app.py`, new `patterns/` package, `scan_history.db` schema, scan API JSON  
> **Depends on:** existing `fetch_historical_prices()`, `classify_technical_pattern()`, `populate_screener_intelligence()`, `scan_stocks()`, `/api/setup-analysis`

---

## Overview

This plan integrates two open-source pattern libraries into the existing screener pipeline:

| Layer | Library | Purpose | When It Runs |
|---|---|---|---|
| **Candlestick** | [TA-Lib](https://github.com/TA-Lib/ta-lib-python) | ~60 classic candle patterns per bar, fast C-core | Every scan cycle, on all filtered stocks |
| **Chart patterns** | [BennyThadikaran/stock-pattern](https://github.com/BennyThadikaran/stock-pattern) | Double tops/bottoms, triangles, harmonics | Daily timeframe only, on top-50 swing stocks |

Both libraries feed into the existing `classify_setup()` / `setupLabel` system and extend the JSON already returned by `/api/scan` and `/api/setup-analysis`.

---

## Phase 1 — Install Dependencies

### 1.1 TA-Lib (C library + Python wrapper)

**On Linux (Ubuntu/Debian):**

```bash
# Install native C library first
sudo apt-get install -y libta-lib-dev

# Then the Python binding
pip install TA-Lib
```

**On Windows (local dev):**

```bash
# Download the prebuilt wheel for your Python version from:
# https://github.com/cgohlke/talib-build/releases
# e.g. TA_Lib-0.4.29-cp311-cp311-win_amd64.whl
pip install TA_Lib-0.4.29-cp311-cp311-win_amd64.whl
```

**Verify:**

```python
import talib
print(talib.__version__)   # should print e.g. 0.4.29
```

**Add to `requirements.txt`:**

```
TA-Lib>=0.4.29
```

### 1.2 stock-pattern (vendored as submodule)

```bash
# From your repo root
git submodule add https://github.com/BennyThadikaran/stock-pattern vendor/stock_pattern

# Install its dependencies
pip install -r vendor/stock_pattern/requirements.txt
```

> **Note:** You only need the detection logic, not its CLI flow. The `src/` directory inside the submodule contains the importable modules.

---

## Phase 2 — Create the `patterns/` Package

Create a new directory `patterns/` at your repo root with three files:

```
patterns/
├── __init__.py
├── ta_patterns.py
└── chart_patterns.py
```

### 2.1 `patterns/__init__.py`

```python
# patterns/__init__.py
# Makes patterns a proper Python package.
from .ta_patterns import compute_ta_pattern_snapshot, compute_ta_pattern_series
from .chart_patterns import detect_chart_patterns, ChartPattern
```

---

### 2.2 `patterns/ta_patterns.py`

This wraps TA-Lib's candlestick recognition functions into your existing OHLC dict/list format.

```python
# patterns/ta_patterns.py
"""
TA-Lib candlestick pattern wrapper.

Accepts:
  df  — pd.DataFrame with columns: open, high, low, close (floats)
        OR a list of dicts matching fetch_historical_prices() output format.

Returns:
  compute_ta_pattern_snapshot(df) -> dict  — last-bar pattern values
  compute_ta_pattern_series(df)   -> pd.DataFrame  — full series (for backtest)

TA-Lib return convention:
  0   = no pattern detected
  100 = bullish signal  (positive strength)
 -100 = bearish signal  (negative strength)
  200 = strong bullish  (e.g. Morning Star)
 -200 = strong bearish
"""

import numpy as np
import pandas as pd

try:
    import talib
    _TALIB_AVAILABLE = True
except ImportError:
    _TALIB_AVAILABLE = False
    print("[patterns/ta_patterns] WARNING: TA-Lib not installed. Candlestick patterns disabled.")

# ── Curated set relevant for NSE swing trading ──────────────────────────────
# Expand or trim this list freely; each entry is (friendly_name, talib_function).
_SWING_PATTERNS = [
    ("hammer",          lambda o, h, l, c: talib.CDLHAMMER(o, h, l, c)),
    ("inverted_hammer", lambda o, h, l, c: talib.CDLINVERTEDHAMMER(o, h, l, c)),
    ("shooting_star",   lambda o, h, l, c: talib.CDLSHOOTINGSTAR(o, h, l, c)),
    ("doji",            lambda o, h, l, c: talib.CDLDOJI(o, h, l, c)),
    ("dragonfly_doji",  lambda o, h, l, c: talib.CDLDRAGONFLYDOJI(o, h, l, c)),
    ("gravestone_doji", lambda o, h, l, c: talib.CDLGRAVESTONEDOJI(o, h, l, c)),
    ("engulfing",       lambda o, h, l, c: talib.CDLENGULFING(o, h, l, c)),
    ("piercing",        lambda o, h, l, c: talib.CDLPIERCING(o, h, l, c)),
    ("morning_star",    lambda o, h, l, c: talib.CDLMORNINGSTAR(o, h, l, c, penetration=0)),
    ("evening_star",    lambda o, h, l, c: talib.CDLEVENINGSTAR(o, h, l, c, penetration=0)),
    ("three_white_sol", lambda o, h, l, c: talib.CDL3WHITESOLDIERS(o, h, l, c)),
    ("three_black_cr",  lambda o, h, l, c: talib.CDL3BLACKCROWS(o, h, l, c)),
    ("marubozu",        lambda o, h, l, c: talib.CDLMARUBOZU(o, h, l, c)),
    ("harami",          lambda o, h, l, c: talib.CDLHARAMI(o, h, l, c)),
    ("dark_cloud",      lambda o, h, l, c: talib.CDLDARKCLOUDCOVER(o, h, l, c, penetration=0)),
]


def _to_numpy_arrays(data):
    """
    Normalise input to numpy float64 arrays (O, H, L, C).
    Accepts either:
      - pd.DataFrame with columns open/high/low/close
      - list of dicts from fetch_historical_prices()
    """
    if isinstance(data, list):
        data = pd.DataFrame(data)
    o = data["open"].astype(float).values
    h = data["high"].astype(float).values
    l = data["low"].astype(float).values
    c = data["close"].astype(float).values
    return o, h, l, c


def compute_ta_pattern_series(data) -> pd.DataFrame:
    """
    Returns a DataFrame indexed 0..N-1 with one column per pattern.
    Values are TA-Lib integers (0, ±100, ±200).
    """
    if not _TALIB_AVAILABLE:
        return pd.DataFrame()
    o, h, l, c = _to_numpy_arrays(data)
    result = {}
    for name, fn in _SWING_PATTERNS:
        try:
            result[name] = fn(o, h, l, c)
        except Exception as e:
            print(f"[ta_patterns] {name} failed: {e}")
            result[name] = np.zeros(len(c), dtype=int)
    return pd.DataFrame(result)


def compute_ta_pattern_snapshot(data) -> dict:
    """
    Returns a dict of {pattern_name: value} for the *last bar only*.
    Non-zero values indicate a pattern on the most recent candle.

    Example output:
      {"hammer": 100, "doji": 100, "engulfing": 0, ...}
    """
    if not _TALIB_AVAILABLE:
        return {}
    series = compute_ta_pattern_series(data)
    if series.empty:
        return {}
    last = series.iloc[-1]
    return {name: int(val) for name, val in last.items()}


def summarise_ta_patterns(snapshot: dict) -> dict:
    """
    Convert raw TA-Lib snapshot into human-readable summary fields.

    Returns:
      {
        "bullish_candles": ["hammer", "morning_star"],
        "bearish_candles": ["shooting_star"],
        "neutral_candles": ["doji"],
        "strongest_bullish": "morning_star",    # highest positive value
        "strongest_bearish": "shooting_star",   # most negative value
      }
    """
    bullish, bearish, neutral = [], [], []
    for name, val in snapshot.items():
        if val > 0:
            bullish.append((name, val))
        elif val < 0:
            bearish.append((name, abs(val)))
        # val == 0 → skip (no pattern)

    return {
        "bullish_candles": [n for n, _ in sorted(bullish, key=lambda x: -x[1])],
        "bearish_candles": [n for n, _ in sorted(bearish, key=lambda x: -x[1])],
        "neutral_candles": neutral,
        "strongest_bullish": bullish[0][0] if bullish else None,
        "strongest_bearish": bearish[0][0] if bearish else None,
    }
```

---

### 2.3 `patterns/chart_patterns.py`

This wraps logic extracted from `BennyThadikaran/stock-pattern`. Study the `src/` directory in the submodule; the key functions operate on pandas DataFrames of OHLC data and return detected pattern "legs" and ratios. The wrapper below shows the *interface* you target — fill in the `# TODO` blocks after inspecting the submodule source.

```python
# patterns/chart_patterns.py
"""
Chart pattern detection wrapper around BennyThadikaran/stock-pattern.

Design notes:
  - Only detect patterns on *daily* timeframe (1D).
  - Slice df.tail(160) before calling — mirrors the CLI's default look-back.
  - Returns a list of ChartPattern dataclasses, newest first.
  - Falls back gracefully (returns []) if the submodule is not present.
"""

import sys
import os
from dataclasses import dataclass, field
from typing import List, Optional
import pandas as pd

# ── Attempt to import stock-pattern from the vendored submodule ─────────────
_STOCK_PATTERN_AVAILABLE = False
try:
    _vendor_path = os.path.join(os.path.dirname(__file__), "..", "vendor", "stock_pattern", "src")
    if _vendor_path not in sys.path:
        sys.path.insert(0, os.path.abspath(_vendor_path))
    # Once the submodule is cloned, inspect vendor/stock_pattern/src/ and
    # replace the import below with the actual module name(s).
    # Example:  from pattern_detector import detect_patterns, PatternResult
    # from pattern_detector import detect_patterns   # <── FILL THIS IN
    _STOCK_PATTERN_AVAILABLE = True
except ImportError as e:
    print(f"[chart_patterns] stock-pattern submodule not available: {e}")


@dataclass
class ChartPattern:
    name: str                      # e.g. "Double Bottom", "Ascending Triangle"
    direction: str                 # "bullish" | "bearish" | "neutral"
    start_date: str                # ISO date string, e.g. "2026-04-01"
    end_date: str                  # ISO date string
    pivot_high: float              # Highest price in pattern
    pivot_low: float               # Lowest price in pattern
    quality: float                 # 0.0 – 1.0 (or raw score from library)
    breakout_level: Optional[float] = None  # Key resistance/support level
    extra: dict = field(default_factory=dict)


def detect_chart_patterns(
    data,
    *,
    lookback: int = 160
) -> List[ChartPattern]:
    """
    Run chart pattern detection on daily OHLCV data.

    Args:
      data      — pd.DataFrame OR list-of-dicts (fetch_historical_prices format)
                  Columns: date, open, high, low, close, volume
      lookback  — Number of recent candles to analyse (default: 160, ~8 months daily)

    Returns:
      List[ChartPattern], newest patterns first. Empty list if none found or
      library unavailable.
    """
    if not _STOCK_PATTERN_AVAILABLE:
        return []

    # Normalise input
    if isinstance(data, list):
        df = pd.DataFrame(data)
    else:
        df = data.copy()

    # Ensure proper types and sort ascending
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # Slice to lookback window — same behaviour as stock-pattern CLI
    df_scan = df.tail(lookback).reset_index(drop=True)

    patterns: List[ChartPattern] = []

    # ── TODO: Replace this block with actual stock-pattern API calls ────────
    # After cloning the submodule, inspect vendor/stock_pattern/src/ to find
    # the correct function signatures.  A typical usage pattern looks like:
    #
    #   results = detect_patterns(df_scan)
    #   for r in results:
    #       patterns.append(ChartPattern(
    #           name=r.name,
    #           direction="bullish" if r.bias > 0 else "bearish",
    #           start_date=df_scan["date"].iloc[r.start_idx].strftime("%Y-%m-%d"),
    #           end_date=df_scan["date"].iloc[r.end_idx].strftime("%Y-%m-%d"),
    #           pivot_high=float(df_scan["high"].iloc[r.start_idx:r.end_idx+1].max()),
    #           pivot_low=float(df_scan["low"].iloc[r.start_idx:r.end_idx+1].min()),
    #           quality=float(r.score),
    #           breakout_level=float(r.breakout) if r.breakout else None,
    #           extra={"legs": r.legs, "ratios": r.ratios}
    #       ))
    # ────────────────────────────────────────────────────────────────────────

    # Sort newest first (pattern ending latest comes first)
    patterns.sort(key=lambda p: p.end_date, reverse=True)
    return patterns


def chart_patterns_to_json(patterns: List[ChartPattern]) -> list:
    """Serialise ChartPattern list to JSON-safe dicts for the scan API."""
    return [
        {
            "name": p.name,
            "direction": p.direction,
            "start_date": p.start_date,
            "end_date": p.end_date,
            "pivot_high": p.pivot_high,
            "pivot_low": p.pivot_low,
            "quality": round(p.quality, 3),
            "breakout_level": p.breakout_level,
        }
        for p in patterns
    ]
```

---

## Phase 3 — Database Schema Migration

Add a new table to `scan_history.db`. Place this inside the existing `init_db()` function in `app.py`, after the last `CREATE TABLE IF NOT EXISTS` block:

```python
# Inside init_db() — add after the last existing CREATE TABLE block

c.execute('''
    CREATE TABLE IF NOT EXISTS pattern_signals (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker      TEXT NOT NULL,
        scan_date   TEXT NOT NULL,
        timeframe   TEXT NOT NULL DEFAULT '1D',
        signal_type TEXT NOT NULL,         -- 'candle' | 'chart'
        pattern_name TEXT NOT NULL,
        direction   TEXT,                  -- 'bullish' | 'bearish' | 'neutral'
        value       INTEGER,               -- TA-Lib raw value for candle signals
        quality     REAL,                  -- 0-1 score for chart patterns
        start_date  TEXT,                  -- chart pattern start date
        end_date    TEXT,                  -- chart pattern end date
        breakout_level REAL,
        meta_json   TEXT                   -- extra dict serialised as JSON
    )
''')
try:
    c.execute("CREATE INDEX IF NOT EXISTS idx_pattern_signals_ticker_date ON pattern_signals(ticker, scan_date)")
except Exception:
    pass
```

---

## Phase 4 — Integrate into `app.py`

### 4.1 Import the patterns package

Add at the top of `app.py`, after the existing imports:

```python
# Pattern detection — Phase 4 integration
try:
    from patterns.ta_patterns import compute_ta_pattern_snapshot, summarise_ta_patterns
    from patterns.chart_patterns import detect_chart_patterns, chart_patterns_to_json
    _PATTERNS_ENABLED = True
except ImportError as e:
    print(f"[app] Pattern detection disabled: {e}")
    _PATTERNS_ENABLED = False
```

---

### 4.2 Extend `analyze_single_stock()`

Your existing `analyze_single_stock()` already fetches 6-month daily history per ticker and stores `pattern_name`, `pattern_grade`, `pattern_desc` on the stock dict.  
Extend it to also compute TA-Lib candle patterns and chart patterns:

```python
def analyze_single_stock(stock):
    try:
        ticker = stock["clean_ticker"]
        history = fetch_historical_prices(ticker, range_str="6mo")
        if history:
            # ── Existing Screener Intelligence pattern logic ──────────────
            result = classify_technical_pattern(history)
            stock["pattern_name"]  = result["pattern"]
            stock["pattern_grade"] = result["grade"]
            stock["pattern_desc"]  = result["description"]

            # ── NEW: TA-Lib candlestick patterns ──────────────────────────
            if _PATTERNS_ENABLED:
                try:
                    ta_snap = compute_ta_pattern_snapshot(history)
                    stock["ta_candle_raw"]  = ta_snap
                    stock["ta_candle_summary"] = summarise_ta_patterns(ta_snap)
                except Exception as ta_err:
                    print(f"[ta_patterns] {ticker}: {ta_err}")
                    stock["ta_candle_raw"]     = {}
                    stock["ta_candle_summary"] = {}

            # ── NEW: Chart patterns (daily timeframe only) ────────────────
            if _PATTERNS_ENABLED:
                try:
                    chart_pats = detect_chart_patterns(history, lookback=160)
                    stock["chart_patterns"] = chart_patterns_to_json(chart_pats)
                except Exception as cp_err:
                    print(f"[chart_patterns] {ticker}: {cp_err}")
                    stock["chart_patterns"] = []
        else:
            print(f"[Yahoo Finance] Fetch failed for {ticker} (silently falling back to Trend Continuation)")
            stock["pattern_name"]      = "Trend Continuation"
            stock["pattern_grade"]     = "B"
            stock["pattern_desc"]      = "Price in standard swing configuration. Historical daily data fetch not available."
            stock["ta_candle_raw"]     = {}
            stock["ta_candle_summary"] = {}
            stock["chart_patterns"]    = []
    except Exception as e:
        print(f"[Yahoo Finance] Error analyzing setup for {ticker}: {e}")
        stock["pattern_name"]      = "Trend Continuation"
        stock["pattern_grade"]     = "B"
        stock["pattern_desc"]      = f"Analysis error: {e}"
        stock["ta_candle_raw"]     = {}
        stock["ta_candle_summary"] = {}
        stock["chart_patterns"]    = []
```

---

### 4.3 Extend `/api/setup-analysis` endpoint

The `/api/setup-analysis` endpoint already returns chart data and Kronos forecast. Add the pattern fields to its `return jsonify(...)` block:

```python
# Inside get_setup_analysis() — extend the return jsonify(...) call

# Compute pattern signals for the setup lab view
ta_snapshot   = {}
ta_summary    = {}
chart_pats_json = []

if _PATTERNS_ENABLED and history:
    try:
        ta_snapshot = compute_ta_pattern_snapshot(history)
        ta_summary  = summarise_ta_patterns(ta_snapshot)
    except Exception:
        pass
    try:
        chart_pats      = detect_chart_patterns(history, lookback=160)
        chart_pats_json = chart_patterns_to_json(chart_pats)
    except Exception:
        pass

return jsonify(
    ticker=ticker,
    pattern=result["pattern"],
    grade=result["grade"],
    description=result["description"],
    indicators=indicators,
    ai_forecast_bias=ai_forecast_bias,
    ai_confidence_score=ai_confidence_score,
    forecast_metrics=forecast_metrics,
    forecast_data=forecast_list,
    # ── NEW pattern fields ─────────────────────────────────────────────────
    ta_candle_summary=ta_summary,
    ta_candle_raw=ta_snapshot,
    chart_patterns=chart_pats_json,
    # ──────────────────────────────────────────────────────────────────────
    chart_data=[{
        "date":   d["date"],
        "open":   d["open"],
        "high":   d["high"],
        "low":    d["low"],
        "close":  d["close"],
        "volume": d["volume"]
    } for d in history[-120:]]
)
```

---

### 4.4 Persist pattern signals after `populate_screener_intelligence()`

In `scan_stocks()`, after the call to `populate_screener_intelligence(filtered_stocks)`, add a persistence block:

```python
# Inside scan_stocks() — after populate_screener_intelligence(filtered_stocks)

if _PATTERNS_ENABLED:
    try:
        import json as _json_mod
        today_str = datetime.now().strftime('%Y-%m-%d')
        _conn_pat = sqlite3.connect('scan_history.db')
        _cur_pat  = _conn_pat.cursor()

        for stock in filtered_stocks:
            ticker = stock.get("clean_ticker", "")
            if not ticker:
                continue

            # Persist TA-Lib candle pattern hits (only non-zero values)
            for pname, pval in stock.get("ta_candle_raw", {}).items():
                if pval != 0:
                    direction = "bullish" if pval > 0 else "bearish"
                    try:
                        _cur_pat.execute(
                            """INSERT OR IGNORE INTO pattern_signals
                               (ticker, scan_date, timeframe, signal_type, pattern_name,
                                direction, value, quality, meta_json)
                               VALUES (?, ?, '1D', 'candle', ?, ?, ?, NULL, NULL)""",
                            (ticker, today_str, pname, direction, pval)
                        )
                    except Exception:
                        pass

            # Persist chart patterns
            for cp in stock.get("chart_patterns", []):
                try:
                    _cur_pat.execute(
                        """INSERT OR IGNORE INTO pattern_signals
                           (ticker, scan_date, timeframe, signal_type, pattern_name,
                            direction, value, quality, start_date, end_date,
                            breakout_level, meta_json)
                           VALUES (?, ?, '1D', 'chart', ?, ?, NULL, ?, ?, ?, ?, NULL)""",
                        (ticker, today_str, cp["name"], cp["direction"],
                         cp["quality"], cp["start_date"], cp["end_date"],
                         cp.get("breakout_level"))
                    )
                except Exception:
                    pass

        _conn_pat.commit()
        _conn_pat.close()
    except Exception as persist_err:
        print(f"[pattern_signals] Persist error: {persist_err}")
```

---

## Phase 5 — New API Endpoint: Pattern History

Add a lightweight read endpoint so the workspace UI can query which patterns a stock has recently fired:

```python
@app.route('/api/pattern-signals', methods=['GET'])
def get_pattern_signals():
    """
    GET /api/pattern-signals?ticker=RELIANCE&days=30&type=candle

    Query parameters:
      ticker  — required
      days    — look-back in calendar days (default 30)
      type    — 'candle' | 'chart' | 'all' (default 'all')
    """
    from flask import request
    ticker = request.args.get('ticker', '').strip().upper()
    if not ticker:
        return jsonify({"error": "ticker required"}), 400

    days = min(int(request.args.get('days', 30)), 90)
    signal_type = request.args.get('type', 'all').lower()

    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    conn = get_db_connection()
    query = """
        SELECT scan_date, signal_type, pattern_name, direction,
               value, quality, start_date, end_date, breakout_level
        FROM pattern_signals
        WHERE ticker = ? AND scan_date >= ?
    """
    params = [ticker, cutoff]

    if signal_type in ('candle', 'chart'):
        query += " AND signal_type = ?"
        params.append(signal_type)

    query += " ORDER BY scan_date DESC LIMIT 200"

    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()

    return jsonify({
        "ticker": ticker,
        "days": days,
        "signals": rows
    })
```

---

## Phase 6 — Frontend Integration (Workspace JS)

The workspace already renders `setupLabel`, `swingband`, and the Kronos panel. Add pattern chips to the symbol detail drawer with minimal changes.

### 6.1 Pattern chip renderer (add to your workspace JS)

```javascript
// Add to your workspace/setup-lab JS — renders pattern signal chips

function renderPatternChips(stock) {
  const chips = [];

  // TA-Lib candle summary
  const summary = stock.ta_candle_summary || {};
  if (summary.strongest_bullish) {
    chips.push({
      label: formatPatternName(summary.strongest_bullish),
      cls: 'chip-bullish'
    });
  }
  if (summary.strongest_bearish) {
    chips.push({
      label: formatPatternName(summary.strongest_bearish),
      cls: 'chip-bearish'
    });
  }

  // Chart patterns
  (stock.chart_patterns || []).slice(0, 2).forEach(cp => {
    chips.push({
      label: cp.name,
      cls: cp.direction === 'bullish' ? 'chip-chart-bullish'
           : cp.direction === 'bearish' ? 'chip-chart-bearish'
           : 'chip-chart-neutral',
      title: `Quality: ${(cp.quality * 100).toFixed(0)}% | ${cp.start_date} → ${cp.end_date}`
    });
  });

  if (chips.length === 0) return '';

  return `
    <div class="pattern-chips">
      ${chips.map(c =>
        `<span class="chip ${c.cls}" title="${c.title || ''}">${c.label}</span>`
      ).join('')}
    </div>
  `;
}

function formatPatternName(snake) {
  return snake.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}
```

### 6.2 CSS additions (add to your workspace stylesheet)

```css
/* Pattern detection chips */
.pattern-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.chip {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 12px;
  white-space: nowrap;
  cursor: default;
}

.chip-bullish         { background: rgba(74, 222, 128, 0.15); color: #4ade80; border: 1px solid rgba(74, 222, 128, 0.3); }
.chip-bearish         { background: rgba(248, 113, 113, 0.15); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.3); }
.chip-chart-bullish   { background: rgba(96, 165, 250, 0.15); color: #60a5fa; border: 1px solid rgba(96, 165, 250, 0.3); }
.chip-chart-bearish   { background: rgba(251, 146, 60, 0.15); color: #fb923c; border: 1px solid rgba(251, 146, 60, 0.3); }
.chip-chart-neutral   { background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.2); }
```

---

## Phase 7 — Feeding Patterns into Kronos / Ensemble

Once Phases 1–6 are stable, you can use TA-Lib candle pattern flags as additional input features to your ensemble:

```python
# Example: Encode candle pattern presence as a scalar feature
# for use in compute_dynamic_weights() or as a Kronos temperature modifier

def candle_pattern_bias(ta_snapshot: dict) -> float:
    """
    Returns a scalar in [-1, +1] summarising the net candle bias on the last bar.
    Positive = net bullish candle signals. Negative = net bearish.
    Use this to nudge ensemble weights or Kronos temperature.
    """
    total = sum(ta_snapshot.values())
    # TA-Lib values are multiples of 100; normalise to [-1, 1]
    return max(-1.0, min(1.0, total / (len(ta_snapshot) * 100 + 1e-9)))
```

Integration point in `get_setup_analysis()` — after computing `ta_snapshot`:

```python
# In get_setup_analysis(), after computing ta_snapshot and before Kronos inference
if ta_snapshot and _PATTERNS_ENABLED:
    pattern_bias = candle_pattern_bias(ta_snapshot)
    # Adjust Kronos temperature slightly: bullish candles → lower T (more confident)
    # This is additive with the ATR-based T_val already computed below
    T_candle_adj = -0.05 * pattern_bias   # range: -0.05 to +0.05
else:
    T_candle_adj = 0.0

# Then in the Kronos predict call:
# T_val = max(0.5, min(0.8, 0.5 + atr_pct * 0.03 + T_candle_adj))
```

---

## Implementation Checklist

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 1 | Install TA-Lib C library and Python wrapper | `requirements.txt`, env | ☐ |
| 2 | Add stock-pattern as git submodule | `vendor/stock_pattern/` | ☐ |
| 3 | Create `patterns/__init__.py` | `patterns/` | ☐ |
| 4 | Create `patterns/ta_patterns.py` | `patterns/` | ☐ |
| 5 | Inspect `vendor/stock_pattern/src/` and fill TODO in `chart_patterns.py` | `patterns/chart_patterns.py` | ☐ |
| 6 | Add `pattern_signals` table to `init_db()` | `app.py` | ☐ |
| 7 | Add pattern imports to top of `app.py` | `app.py` | ☐ |
| 8 | Extend `analyze_single_stock()` | `app.py` | ☐ |
| 9 | Extend `/api/setup-analysis` return | `app.py` | ☐ |
| 10 | Add pattern persistence in `scan_stocks()` | `app.py` | ☐ |
| 11 | Add `/api/pattern-signals` endpoint | `app.py` | ☐ |
| 12 | Add chip renderer + CSS to workspace JS | `static/` | ☐ |
| 13 | Optionally wire `candle_pattern_bias` into Kronos T | `app.py` | ☐ |

---

## Key Design Decisions

- **TA-Lib runs on all top-50 stocks** inside `analyze_single_stock()` which already uses `ThreadPoolExecutor(max_workers=8)` — no added latency.
- **chart_patterns runs on daily data only** — same `history` fetch already happening, zero extra network calls.
- **Graceful fallback on import failure** — if TA-Lib or stock-pattern is not installed, `_PATTERNS_ENABLED = False` and all new fields default to empty dicts/lists. No existing functionality breaks.
- **No new Yahoo Finance fetches** — both layers reuse the `_historical_prices_cache` already populated by `analyze_single_stock()`.
- **Existing `classify_technical_pattern()` is untouched** — it runs first, the new pattern fields are additive.
