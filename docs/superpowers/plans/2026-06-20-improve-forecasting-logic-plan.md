# Improve Forecasting Logic – Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task‑by‑task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebalance the AI forecast bias distribution to ~20 % per label while keeping CPU‑only performance unchanged.

**Architecture:** Introduce a modest volatility signal (ATR %), re‑weight existing metrics, and replace static bias thresholds with a percentile‑based mapping stored in an in‑memory circular buffer.

**Tech Stack:** Python 3.8+, Flask, NumPy, Pandas, `collections.deque` (standard library).

## Global Constraints
- No GPU usage; all calculations must remain CPU‑only and O(N) per ticker.
- No external dependencies beyond what the project already imports.
- Preserve the existing `forecast_metrics` JSON schema; add an optional `percentile` field.
- Feature flag `ENABLE_PERCENTILE_BIAS` default `True`.

---

### Task 1: Add Configuration Constants
**Files:**
- Modify: `app/utils/forecast_math.py`

**Interfaces:**
- Consumes: none.
- Produces: `METRIC_WEIGHTS` dict, `PERCENTILE_BUFFER_SIZE` int, `ENABLE_PERCENTILE_BIAS` bool.

- [ ] **Step 1:** Insert constants near the top of the file after imports.
```python
# Configuration for forecast scoring
METRIC_WEIGHTS = {
    "s1": 0.20,
    "s2": 0.20,
    "s3": 0.25,
    "s4": 0.25,
    "s5": 0.10,
    "s6": 0.10,
}
PERCENTILE_BUFFER_SIZE = 500
ENABLE_PERCENTILE_BIAS = True  # can be toggled via app config if needed
```
- [ ] **Step 2:** Run `pytest tests/test_forecast_math.py::test_compute_atr_pct -q` to ensure import still works.
- [ ] **Step 3:** Commit changes.
```bash
git add app/utils/forecast_math.py
git commit -m "feat: add forecast scoring config constants"
```

### Task 2: Compute ATR Volatility Signal `s6`
**Files:**
- Modify: `app/utils/forecast_math.py`

**Interfaces:**
- Consumes: `history` list, `compute_atr_pct` function.
- Produces: `s6` value used in weighted sum.

- [ ] **Step 1:** Within `compute_forecast_metrics`, after existing metric calculations, add:
```python
# 6️⃣ ATR volatility signal (14‑day ATR %)
atr_pct = compute_atr_pct(history, window=14)
# Normalise ATR to a 0‑5% range (higher volatility => higher score)
# _norm clamps to [0,1]; we map 0‑5% to 0‑1.
# Re‑use existing _norm helper:
# _norm(value, lo, hi) → (value‑lo)/(hi‑lo) clipped to [0,1]
s6 = _norm(atr_pct, 0, 5)
```
- [ ] **Step 2:** Verify that `atr_pct` is calculated without error on a sample history (use a short REPL or test snippet).
- [ ] **Step 3:** Commit.
```bash
git add app/utils/forecast_math.py
git commit -m "feat: add ATR volatility as s6 for forecast scoring"
```

### Task 3: Apply New Weight Vector and Normalise Sum
**Files:**
- Modify: `app/utils/forecast_math.py`

**Interfaces:**
- Consumes: `METRIC_WEIGHTS` dict, metric values `s1`‑`s6`.
- Produces: `weighted_score` (float in [-1,1]).

- [ ] **Step 1:** Replace the hard‑coded weighted sum with a dynamic calculation:
```python
# Gather metric values into a dict for clarity
metric_vals = {
    "s1": s1,
    "s2": s2,
    "s3": s3,
    "s4": s4,
    "s5": s5,
    "s6": s6,
}
# Compute raw weighted sum
raw_score = sum(METRIC_WEIGHTS[k] * metric_vals[k] for k in METRIC_WEIGHTS)
# Normalise by total weight (should be 1.10)
weighted_score = raw_score / sum(METRIC_WEIGHTS.values())
# Clip to [-1, 1]
weighted_score = float(np.clip(weighted_score, -1.0, 1.0))
```
- [ ] **Step 2:** Run existing unit tests (`pytest tests/test_forecast_math.py -q`) to confirm no regression.
- [ ] **Step 3:** Commit.
```bash
git add app/utils/forecast_math.py
git commit -m "refactor: compute weighted_score using configurable METRIC_WEIGHTS"
```

### Task 4: Add Percentile Buffer and Percentile‑Based Bias Mapping
**Files:**
- Modify: `app/utils/forecast_math.py`

**Interfaces:**
- Consumes: `PERCENTILE_BUFFER_SIZE`, `ENABLE_PERCENTILE_BIAS`.
- Produces: Updated bias label and new `percentile` field in `forecast_metrics`.

- [ ] **Step 1:** Import `deque` at top of file:
```python
from collections import deque
```
- [ ] **Step 2:** Define a module‑level buffer (singleton) after imports:
```python
# Circular buffer of recent weighted scores for percentile mapping
_SCORE_BUFFER = deque(maxlen=PERCENTILE_BUFFER_SIZE)
```
- [ ] **Step 3:** After computing `weighted_score`, append it to the buffer before bias mapping:
```python
_SCORE_BUFFER.append(weighted_score)
```
- [ ] **Step 4:** Replace static `if` cascade with percentile lookup when the flag is enabled:
```python
if ENABLE_PERCENTILE_BIAS and len(_SCORE_BUFFER) >= 5:
    # Compute percentiles only once per call (fast for small buffer)
    pct = (np.sum(np.array(_SCORE_BUFFER) < weighted_score) / len(_SCORE_BUFFER)) * 100
    # Map to 5 buckets (each 20 %)
    if pct >= 80:
        ai_forecast_bias = "Strong Breakout"
    elif pct >= 60:
        ai_forecast_bias = "Bullish Continuation"
    elif pct >= 40:
        ai_forecast_bias = "Sideways Consolidation"
    elif pct >= 20:
        ai_forecast_bias = "Bearish Pressure"
    else:
        ai_forecast_bias = "Strong Downtrend"
    # Store percentile for UI debugging
    forecast_metrics["percentile"] = round(pct, 1)
else:
    # Fallback to original static thresholds (kept for backward compatibility)
    if weighted_score > 0.40:
        ai_forecast_bias = "Strong Breakout"
    elif weighted_score > 0.15:
        ai_forecast_bias = "Bullish Continuation"
    elif weighted_score > -0.15:
        ai_forecast_bias = "Sideways Consolidation"
    elif weighted_score > -0.40:
        ai_forecast_bias = "Bearish Pressure"
    else:
        ai_forecast_bias = "Strong Downtrend"
```
- [ ] **Step 5:** Ensure `forecast_metrics` dictionary includes the new key when applicable.
- [ ] **Step 6:** Run all tests; add a quick sanity check that the buffer does not raise errors on first few calls.
- [ ] **Step 7:** Commit.
```bash
git add app/utils/forecast_math.py
git commit -m "feat: percentile‑based bias mapping with circular score buffer"
```

### Task 5: Extend Unit Tests for New Logic
**Files:**
- Modify: `tests/test_forecast_math.py`

**Interfaces:**
- Consumes: `compute_forecast_metrics`, `METRIC_WEIGHTS`.
- Produces: New test cases verifying `s6` calculation, percentile distribution, and weight sum.

- [ ] **Step 1:** Add a test for ATR‑based `s6` normalization.
```python
def test_compute_s6_atr_normalization():
    # History with high volatility (ATR ~4%) should yield s6 near 0.8
    volatile_hist = [{"high": 105, "low": 95, "close": 100} for _ in range(15)]
    atr = compute_atr_pct(volatile_hist, window=14)
    s6 = _norm(atr, 0, 5)
    assert 0.7 <= s6 <= 0.9
```
- [ ] **Step 2:** Add a test that simulates a series of scores to ensure the percentile bucket distributes roughly evenly.
```python
def test_percentile_bias_balanced_distribution():
    # Seed the buffer with a range of synthetic scores
    from app.utils.forecast_math import _SCORE_BUFFER, PERCENTILE_BUFFER_SIZE
    _SCORE_BUFFER.clear()
    for i in range(PERCENTILE_BUFFER_SIZE):
        # Create a sinusoidal pattern to cover the full range [-1, 1]
        score = np.sin(i / 50.0)
        _SCORE_BUFFER.append(score)
    # Pick a score near the 70th percentile
    test_score = 0.5
    # Manually compute percentile
    pct = (np.sum(np.array(_SCORE_BUFFER) < test_score) / len(_SCORE_BUFFER)) * 100
    # Run the function to get bias
    dummy_forecast = [{"close": 100, "high": 101, "low": 99}] * 5
    bias, conf, metrics = compute_forecast_metrics(dummy_forecast, 100, dummy_forecast)
    # Bias should be in the 60‑80 % bucket (Bullish Continuation)
    assert bias == "Bullish Continuation"
    # Percentile field should be present and close to manual pct
    assert "percentile" in metrics
    assert abs(metrics["percentile"] - round(pct, 1)) < 1.0
```
- [ ] **Step 3:** Run the full test suite to verify no failures.
```bash
pytest tests/test_forecast_math.py -q
```
- [ ] **Step 4:** Commit test additions.
```bash
git add tests/test_forecast_math.py
git commit -m "test: add s6 ATR test and percentile‑bias distribution test"
```

### Task 6: Add Performance Benchmark (optional but required by spec)
**Files:**
- Modify: `scripts/run_performance_tests.py`

**Interfaces:**
- Consumes: the forecast pipeline for a single ticker.
- Produces: printed timing before and after changes.

- [ ] **Step 1:** Insert a new benchmark function at the bottom of the script:
```python
def benchmark_forecast_latency(ticker="RELIANCE.NS", history_len=30, runs=20):
    from app.utils.forecast_math import compute_forecast_metrics
    # Build dummy history and forecast
    hist = [{"high": 100 + i, "low": 95 + i, "close": 97 + i} for i in range(history_len)]
    forecast = [{"close": 100 + i, "high": 101 + i, "low": 99 + i} for i in range(5)]
    start = time.time()
    for _ in range(runs):
        compute_forecast_metrics(forecast, hist[-1]["close"], hist)
    elapsed = time.time() - start
    print(f"Average forecast latency: {elapsed/run*1000:.2f} ms per call")
```
- [ ] **Step 2:** Run the benchmark before and after code changes (e.g., `git checkout <previous‑commit>` then run, then after). Verify the increase is < 5 %.
- [ ] **Step 3:** Commit benchmark addition.
```bash
git add scripts/run_performance_tests.py
git commit -m "perf: add benchmark for forecast latency"
```

### Task 7: Documentation Update (optional but nice)
**Files:**
- Modify: `README.md` or a dedicated section in `docs/superpowers/specs/2026-06-20-improve-forecasting-logic-design.md`.

**Interfaces:**
- Consumes: none.
- Produces: note about the new percentile‑based bias.

- [ ] **Step 1:** Append a short paragraph to the design spec stating that the forecast panel now uses percentile‑based bias and displays a `percentile` tooltip.
- [ ] **Step 2:** Commit.
```bash
git add docs/superpowers/specs/2026-06-20-improve-forecasting-logic-design.md
git commit -m "doc: note percentile bias mapping in design spec"
```

---

**Plan complete.**

**Execution options:**
1. **Sub‑agent‑driven (recommended):** Dispatch a fresh sub‑agent per task, review after each commit, and let the sub‑agents handle test runs.
2. **Inline execution:** Run all tasks sequentially in this session using the `executing-plans` skill.

Which approach would you like to take?