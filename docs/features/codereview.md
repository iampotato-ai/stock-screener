# Code Review — Feature 2: Kronos Watchlist Batch Forecasting

**Commit:** [`436c777`](https://github.com/iampotato-ai/stock-screener/commit/436c777780bdcb83f36ec7b34eea267b454ac99f)  
**Files Changed:** `app.py` (+354 / -118), `static/js/app.js` (+283 / -34), `templates/index.html` (+7 / -1)  
**Reviewed on:** 2026-05-30

---

## ✅ What's Working Well

- The batch sorting flow is clean — the spinner, disabling the button, the `finally` block for cleanup, and the optimistic UI update all look correct.
- Cache hit tracking per ticker (`cache_hit` field) is a nice touch for debugging.
- You preserve stocks not returned by the API at the tail of the sorted list, which prevents any watchlist entries from disappearing on partial results.
- The `showWatchlistKronosColumns` toggle integrates neatly with the existing `renderWatchlist()` approach.

---

## 🐛 Issues Found

### 1. Race Condition — `isKronosBatchSorting` Guard Bypassed by Re-render

In the click handler for `btn-kronos-batch-sort`, you set `isKronosBatchSorting = true` and call `renderWatchlist()` before the `await fetch(...)`. If `renderWatchlist()` re-attaches event listeners or recreates the button element (which can happen with `innerHTML` re-renders), the `isKronosBatchSorting` early-exit guard will be stale and a second click could trigger a duplicate request.

**Fix:** Check whether `renderWatchlist()` replaces the button's DOM node. If so, store a reference to the button _before_ the render and reuse it, or skip the intermediate `renderWatchlist()` call.

---

### 2. Missing Error Feedback in the UI

```js
} catch (err) {
    console.error("Kronos batch sorting error:", err);
    alert("Error during Kronos AI sorting: " + err.message);
}
```

Using a raw `alert()` is inconsistent with the rest of the UI, which uses styled error states (e.g. `showErrorState()`). Consider using a toast notification or an inline error badge on the button instead — especially since this runs in a trading-focused workspace.

---

### 3. `saveWatchlistSections` Called Without Guaranteed Availability

```js
if (typeof saveWatchlistSections === 'function') {
    saveWatchlistSections();
}
```

This `typeof` guard is defensive, but it suggests `saveWatchlistSections` may not always be available at call time (possibly defined in another file). If it silently skips, the reordered `section.stocks` array will be lost on the next re-render.

**Fix:** Confirm this function is always loaded before `initWatchlist()` runs, or move it into a guaranteed-available utility module.

---

### 4. `pred_len=5` is Hardcoded

```js
const response = await fetch('/api/watchlist/kronos-ranking?pred_len=5');
```

The prediction length is hardcoded to `5` with no way for the user to configure it. If the feature spec supports different forecast horizons (e.g., 5/10/20 days), this should read from a user preference or at minimum be a named constant at the top of the file.

**Fix:**
```js
const KRONOS_PRED_LEN = 5; // move to top of file or user settings
const response = await fetch(`/api/watchlist/kronos-ranking?pred_len=${KRONOS_PRED_LEN}`);
```

---

### 5. `watchlistKronosRankings` is Never Cleared Between Runs

```js
watchlistKronosRankings[r.ticker] = { ... };
```

This object is updated by merging — stale rankings from a previous run for tickers that have since been removed from the watchlist will persist in memory indefinitely.

**Fix:** Reset the cache at the start of the fetch:
```js
watchlistKronosRankings = {};
```

---

### 6. `btnKronosColumnToggle` Color Not Reset on Error

The button is highlighted gold at the start of the click handler:
```js
if (btnKronosColumnToggle) btnKronosColumnToggle.style.color = '#f59e0b';
```
But if an error occurs mid-flow, the toggle stays highlighted with no visual indication that the sort failed.

**Fix:** In the `catch` block, reset the button color and `showWatchlistKronosColumns` if appropriate:
```js
showWatchlistKronosColumns = false;
if (btnKronosColumnToggle) btnKronosColumnToggle.style.color = 'var(--color-text-secondary)';
```

---

## 💡 Minor Suggestions

- The `originalSortBtnHtml` save-and-restore pattern for the spinner is clean, but the inline `style` for the spinner (`border`, `animation`) should move to a CSS class to keep the markup clean.
- Consider adding a timestamp or **"Last sorted: X min ago"** label next to the Kronos button so users know how fresh the rankings are.

---

## Priority Summary

| # | Issue | Severity |
|---|-------|----------|
| 1 | Race condition — guard bypassed by re-render | 🔴 High |
| 5 | Stale Kronos rankings cache between runs | 🔴 High |
| 3 | `saveWatchlistSections` silently skipped | 🟡 Medium |
| 6 | Column toggle color not reset on error | 🟡 Medium |
| 2 | `alert()` used for error feedback | 🟡 Medium |
| 4 | `pred_len` hardcoded | 🟢 Low |

---

---

# Code Review — FEAT-004: Sector Rotation Timeline (RRG)

**Branch:** `feature/workspace-ui`  
**Scope:** `app.py` (RRG backend), `app.js` (RRG canvas renderer)  
**Reviewed on:** 2026-05-30

> Overall the implementation is solid — the animated trail canvas, playback controls, and dynamic scaling work well together. Suggestions below are grouped by priority.

---

## 🔴 High Priority

### 1. Backfill Uses Interpolated / Simulated Data, Not Real History

**File:** `app.py` → `rrg_backfill()`

The `/api/rrg/backfill` endpoint generates fake historical weekly data using linear interpolation + a `sin()` wave. This produces misleading trails the first time users view the rotation timeline.

```python
# Current — fabricated sine-wave fluctuation
val += math.sin(offset * math.pi / 2.0) * 0.25
```

**Suggested Fix:**  
Replace with real rolling history by calling `fetch_historical_prices` for each ticker in `SECTOR_INDEX_MAP` and computing true 4-week rolling returns per week. Alternatively, schedule `snapshot_rrg_week` via `APScheduler` every Friday at market close to accumulate real weekly data going forward.

```python
# Example: schedule with APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
scheduler = BackgroundScheduler()
scheduler.add_job(trigger_weekly_rrg_snap, 'cron', day_of_week='fri', hour=16, minute=5)
scheduler.start()
```

---

### 2. `snapshot_rrg_week` Uses Raw Delta for RS-Momentum

**File:** `app.py` → `snapshot_rrg_week()`

The current momentum calculation is a simple week-over-week delta, not a smoothed JdK RS-Momentum as used in the original Bloomberg RRG methodology. This causes noisy, jumpy momentum values.

```python
# Current
rs_momentum = jdk_rs - prev_rs  # raw delta — highly sensitive to weekly noise
```

**Suggested Fix:**  
Maintain a short rolling buffer (3 weeks) of `jdk_rs` per sector in the DB and compute momentum as the rate-of-change over that window:

```python
# Fetch last 3 weeks of jdk_rs
cursor.execute(
    'SELECT jdk_rs FROM rrg_history WHERE sector = ? ORDER BY snapped_at DESC LIMIT 3',
    (sector,)
)
rows = cursor.fetchall()
if len(rows) >= 2:
    rs_momentum = jdk_rs - rows[1][0]   # 1-week ROC
else:
    rs_momentum = 0.0
```

---

## 🟡 Medium Priority

### 3. Fragile SQL Date Arithmetic in `get_rrg_history_timeline`

**File:** `app.py` → `get_rrg_history_timeline()`

The query uses string concatenation to build a `datetime('now', ? || ' days')` filter. While it works in SQLite, it's brittle and bypasses the intent of parameterized queries.

```python
# Current — string concat inside SQL
cursor.execute(query, (str(-weeks * 7),))
```

**Suggested Fix:**  
Compute the cutoff date in Python and pass it as a clean ISO string parameter:

```python
cutoff = (datetime.utcnow() - timedelta(weeks=weeks)).isoformat()
cursor.execute(
    "SELECT week, sector, jdk_rs, jdk_rs_momentum, score, quadrant "
    "FROM rrg_history WHERE snapped_at >= ? ORDER BY week ASC, sector ASC",
    (cutoff,)
)
```

---

### 4. No Response-Level Cache on `/api/rrg-history`

**File:** `app.py` → `get_rrg_history()`

The endpoint calls `fetch_historical_prices` for every asset (~18 sector index tickers) in parallel on every request. While `_historical_prices_cache` (15-min TTL) covers repeat fetches, cold-start requests still fan out to Yahoo Finance simultaneously.

**Suggested Fix:**  
Add a coarse response-level cache keyed on `(view, tickers_hash)` with a 10-minute TTL:

```python
_rrg_response_cache = {}
_RRG_RESPONSE_TTL = 10 * 60  # 10 minutes

@app.route('/api/rrg-history', methods=['GET'])
def get_rrg_history():
    cache_key = f"{view}:{hash(tickers_str)}"
    cached = _rrg_response_cache.get(cache_key)
    if cached and (time.time() - cached['ts']) < _RRG_RESPONSE_TTL:
        return jsonify(cached['data'])
    # ... compute results ...
    _rrg_response_cache[cache_key] = {'ts': time.time(), 'data': result}
    return jsonify(result)
```

---

### 5. Playback Slider Not Debounced (Canvas Repaint Jank)

**File:** `app.js` → RRG slider `input` handler

Rapid scrubbing of the week slider triggers a full canvas repaint on every `input` event. With 12+ weeks × 15+ sectors, this can cause visible jank.

**Suggested Fix:**  
Gate repaints to one per animation frame:

```javascript
let _rrgRafPending = false;

sliderEl.addEventListener('input', () => {
    currentWeekIndex = parseInt(sliderEl.value);
    if (!_rrgRafPending) {
        _rrgRafPending = true;
        requestAnimationFrame(() => {
            drawRRGFrame(currentWeekIndex);
            _rrgRafPending = false;
        });
    }
});
```

---

### 6. Cluster Tooltip Doesn't Surface Sector Ranking

**File:** `app.js` → RRG hover tooltip logic

When multiple sectors converge in the same quadrant (visible in the W21 screenshot — the center cluster), the tooltip shows raw coordinates that are hard to parse.

**Suggested Fix:**  
On hover over a cluster (proximity < 20px), show a ranked mini-list ordered by `score` descending:

```javascript
// Example tooltip content for a cluster
const sorted = nearbyPoints.sort((a, b) => b.score - a.score);
tooltipHtml = sorted.map(p =>
    `<div>${p.sector} <span class="score">${p.score}</span> · ${p.quadrant}</div>`
).join('');
```

---

## 🔵 Low Priority / Code Quality

### 7. `Stocks` RRG View Has No Visible Dot Labels

**File:** `app.js` → RRG stocks canvas renderer

In the Stocks view, dots have no visible labels — only hover tooltips. With 20+ dots this makes cluster identification difficult at a glance.

**Suggested Fix:**  
Render a short label (≤ 5 chars) next to each dot when the total dot count is ≤ 25:

```javascript
if (assets.length <= 25) {
    ctx.fillStyle = '#a0f0c0';
    ctx.font = '10px Inter';
    ctx.fillText(asset.label.substring(0, 5), dotX + 6, dotY - 4);
}
```

---

### 8. `wc_intensity` and Growth CAGRs Are Simulated in Production

**File:** `app.py` → `compute_extra_fields()`

The function uses `hash(ticker) % 100` to generate deterministic but fake working capital and CAGR values. These look real to users but are not backed by actual financial data.

```python
h = hash(ticker) % 100  # deterministic but fake
stock["wc_intensity"] = round(25.0 + (h % 20), 2)  # ← simulated
```

**Suggested Fix:**  
The `growth_data_source: "simulated"` flag is already emitted in the API response. Surface a visible disclaimer badge (e.g., `~` prefix or an info icon) next to all simulated fields in the Fundamental tab.

---

### 9. `_rrg_snapped_today` Guard Resets on App Restart

**File:** `app.py` → `snapshot_rrg_week()`

The in-memory guard `_rrg_snapped_today` resets to `None` on every app restart. If the app restarts mid-day, it will re-snap immediately. This is low-risk because the `ON CONFLICT ... DO UPDATE` handles idempotency in SQL, but worth a comment:

```python
# NOTE: _rrg_snapped_today is in-memory only. App restarts will trigger
# a re-snap, but the DB INSERT uses ON CONFLICT DO UPDATE so data is safe.
_rrg_snapped_today = None
```

---

## Summary Table

| # | Area | Severity | Effort |
|---|------|----------|--------|
| 1 | Backfill uses fake interpolated data | 🔴 High | Medium |
| 2 | RS-Momentum is unsmoothed raw delta | 🔴 High | Low |
| 3 | Fragile SQL date arithmetic | 🟡 Medium | Low |
| 4 | No response cache on `/api/rrg-history` | 🟡 Medium | Low |
| 5 | Slider repaint not debounced | 🟡 Medium | Low |
| 6 | Cluster tooltip lacks sector ranking | 🟡 Medium | Low |
| 7 | No dot labels in Stocks RRG view | 🔵 Low | Low |
| 8 | Simulated growth data has no UI flag | 🔵 Low | Low |
| 9 | `_rrg_snapped_today` resets on restart | 🔵 Low | Trivial |

---

---

# Post-Fix Review — FEAT-004: Sector Rotation Timeline (RRG)

**Commit:** [`a94a7a2`](https://github.com/iampotato-ai/stock-screener/commit/a94a7a259246557c5ee005a2f7a859c9a6001ef1)  
**Files Changed:** `app.py` (+103 / -50), `static/js/app.js` (+35 / -5)  
**Reviewed on:** 2026-05-30

> All 9 original suggestions have been addressed. The implementation is solid overall. The following issues were found during review of the fix commit and should be resolved before merging.

---

## ✅ What's Well Done

- **Real-data backfill** — `rrg_backfill()` correctly fetches actual `^NSEI` benchmark history and maps it to weekly boundary dates. The JDK-RS formula `((100 + sector_R) / (100 + bench_R) * 100)` is mathematically sound and handles negative returns safely.
- **Robust momentum** — `snapshot_rrg_week()` now queries `WHERE week != ?` to get the previous week's `jdk_rs` before computing `rs_momentum = jdk_rs - prev_rs`. Correct approach.
- **Response caching** — `_rrg_response_cache` with 10-minute TTL is correctly implemented. Cache key `f"{view}:{tickers_str}"` is a good choice.
- **`SECTOR_INDEX_MAP`** — Well-curated. The indices used (`NIFTY_FIN_SERVICE.NS`, `^CNXIT`, `^CNXMETAL`, etc.) are appropriate proxies for NSE sector indices.

---

## ⚠️ Issues & Suggestions

### 1. 🔴 Backfill Deletes All History Without a Transaction

**File:** `app.py` → `rrg_backfill()`

```python
c.execute('DELETE FROM rrg_history')
```

This is risky in production — if `scan_stocks()` fails mid-way, all historical RRG data is lost with no rollback. Wrap the entire operation in an explicit transaction:

```python
conn.execute('BEGIN')
try:
    c.execute('DELETE FROM rrg_history')
    # ... all inserts ...
    conn.commit()
except:
    conn.rollback()
    raise
```

---

### 2. 🔴 `ThreadPoolExecutor` in Backfill Has No Error Boundary

**File:** `app.py` → `rrg_backfill()`

```python
for fut in futures:
    sector_histories[futures[fut]] = fut.result()
```

`fut.result()` re-raises exceptions from the thread. If any sector ticker fails (e.g. `^CNXMETAL` returns empty), it aborts the entire backfill silently. Wrap with a per-future try/except:

```python
for fut in futures:
    ticker = futures[fut]
    try:
        sector_histories[ticker] = fut.result()
    except Exception as e:
        print(f"[RRG Backfill] Failed for {ticker}: {e}")
        sector_histories[ticker] = []
```

---

### 3. 🟡 `manual_rrg_snapshot` Calls Heavy `scan_stocks()` — No Cooldown Guard

**File:** `app.py` → `manual_rrg_snapshot()`

```python
_rrg_snapped_today = None  # resets guard
res = scan_stocks()        # triggers full TradingView scan
```

If triggered accidentally (e.g. double-click in the UI), two expensive full scans can fire in parallel. Add a short per-endpoint cooldown (e.g. 60 seconds) or a lock:

```python
_last_snapshot_time = 0
_SNAPSHOT_COOLDOWN = 60  # seconds

@app.route('/api/rrg/snapshot', methods=['POST'])
def manual_rrg_snapshot():
    global _last_snapshot_time
    if time.time() - _last_snapshot_time < _SNAPSHOT_COOLDOWN:
        return jsonify(error="Snapshot cooldown active. Try again in a moment."), 429
    _last_snapshot_time = time.time()
    # ...
```

---

### 4. 🟡 `weeks_dates` Only Keeps Last Boundary Per Week — Needs a Comment

**File:** `app.py` → `rrg_backfill()`

```python
for idx, entry in enumerate(bench_history):
    weeks_dates[week_str] = (entry["date"], idx)  # overwrites on every iteration
```

Since the loop is chronological, this correctly retains the **last trading day of each week (Friday)**. This is the right behaviour but is non-obvious. Add a comment:

```python
# Keeps the last trading day of each ISO week (i.e. Friday close)
weeks_dates[week_str] = (entry["date"], idx)
```

---

### 5. 🟡 No Guard for Insufficient Benchmark History in Backfill

**File:** `app.py` → `rrg_backfill()`

```python
target_weeks = sorted_weeks[-14:]  # last 14 weeks → 13 momentum intervals
```

If `bench_history` has fewer than 2 distinct weeks (e.g. first run on a fresh DB), `target_weeks` produces fewer than 2 items and the momentum loop is silently skipped — no error is returned. Add a guard:

```python
if len(sorted_weeks) < 2:
    conn.close()
    return jsonify(error="Insufficient benchmark history for backfill (need ≥ 2 weeks)"), 400
```

---

### 6. 🔵 `app.js` Debounce Delay Not Verified

**File:** `static/js/app.js` → RRG slider repaint

The commit message mentions "debounced repaints" (+35 lines in `app.js`). Ensure the debounce/RAF delay is ≥ 150ms or uses `requestAnimationFrame` correctly — anything shorter on a 20-sector canvas will still feel janky on slower machines.

---

### 7. 🔵 `growth_data_source = "simulated"` Has No Frontend Badge

**File:** `app.py` → `compute_extra_fields()`

```python
stock["growth_data_source"] = "simulated"
```

This flag is already emitted in the API response, which is good for transparency. However, if the frontend doesn't yet surface a `simulated` badge or `~` prefix next to CAGR/WC fields in the Fundamental tab, users may interpret these as live data.

---

## Summary Table

| # | Area | Severity | Action |
|---|------|----------|--------|
| 1 | Backfill deletes history without transaction safety | 🔴 High | Wrap in `BEGIN/ROLLBACK` |
| 2 | ThreadPool exceptions abort entire backfill | 🔴 High | Per-future try/except |
| 3 | Snapshot endpoint has no cooldown guard | 🟡 Medium | Add 60s cooldown / lock |
| 4 | `weeks_dates` overwrite logic undocumented | 🟡 Medium | Add inline comment |
| 5 | No guard for < 2 weeks of benchmark history | 🟡 Medium | Return 400 early |
| 6 | Debounce delay in `app.js` unverified | 🔵 Low | Confirm ≥ 150ms or RAF |
| 7 | Simulated growth fields have no UI badge | 🔵 Low | Surface `~` prefix or icon |

---

# Code Review — Pull Request #1: Multi-Model Ensemble Forecasting (Phase 1)

**Scope:** `app.py` (EnsembleCast backend)  
**Reviewed on:** 2026-05-31

---

## 🔴 High Priority

### 1. Database Connection Leak on Error
In `/api/ensemble_forecast`, both cache lookup and cache write blocks open database connections (`conn = get_db_connection()`), but call `conn.close()` only at the end of their respective `try` blocks. If any exception is raised, `conn.close()` is bypassed, leaking SQLite connections.
**Fix:** Wrap DB calls in a `try...finally` block to guarantee `conn.close()` is executed:
```python
conn = None
try:
    conn = get_db_connection()
    # db operations...
finally:
    if conn:
        conn.close()
```

### 2. Insufficient History / Invalid Ticker Returns 500
If a ticker has insufficient history (e.g., < 60 days or invalid symbol), `_fetch_price_history` correctly throws a `ValueError`. This causes all model runners to fail, resulting in less than 2 active models. The endpoint then returns a `500 Internal Server Error` with `ensemble_failed`. This should degrade to a `400 Bad Request` with an informative error payload.
**Fix:** Catch `ValueError` or inspect model errors. If any failure is due to `insufficient_history`, return `400 Bad Request`.

---

## 🟡 Medium Priority

### 3. Prophet Predictor Calendar Date Misalignment
`prophet_predict` generates future dates using `pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=horizon)`. While this skips weekends, it does not account for **NSE market holidays** (e.g., Diwali, Christmas). Kronos uses the holiday-aware `generate_next_trading_days` function. This causes Prophet's close predictions to align with different dates than Kronos.
**Fix:** Use the same holiday-aware date generator:
```python
last_date_str = df['ds'].iloc[-1].strftime("%Y-%m-%d")
future_dates = generate_next_trading_days(last_date_str, horizon)
future_df = pd.DataFrame({'ds': pd.to_datetime(future_dates)})
```

### 4. Logger Spam from cmdstanpy and statsmodels
Prophet (`cmdstanpy`) prints info chain processing logs to stderr on every prediction, and `statsmodels` prints convergence warnings. This spams the server console during scanning or drawer loads.
**Fix:** Explicitly set logger level and filter warnings:
```python
import logging
logging.getLogger('cmdstanpy').setLevel(logging.WARNING)

from statsmodels.tools.sm_exceptions import ConvergenceWarning
import warnings
warnings.simplefilter('ignore', ConvergenceWarning)
warnings.simplefilter('ignore', UserWarning)
```

---

## Summary Table

| # | Area | Severity | Action |
|---|------|----------|--------|
| 1 | DB connection leak on cache lookup/write failure | 🔴 High | Wrap connections in `finally` blocks |
| 2 | Insufficient history errors return 500 instead of 400 | 🔴 High | Map `ValueError` of history to 400 Bad Request |
| 3 | Prophet future dates omit NSE holidays | 🟡 Medium | Align Prophet to `generate_next_trading_days` |
| 4 | cmdstanpy and statsmodels stderr log spam | 🟡 Medium | Set log level and filter ConvergenceWarnings |

---

---

# Pattern Detection Integration: TA-Lib + stock-pattern Defect Fixes

**Branch:** `feature/workspace-ui`  
**Files Reviewed:** `pattern_detection.py`, `app.py`, `tests/test_pattern_detection.py`  
**Reviewed on:** 2026-06-03  
**Context:** TA-Lib is not installed in this environment. The codebase gracefully falls back to `_detect_candlestick_fallback()` — a pure-Python engine. All unit tests pass under this fallback mode. The issues below were identified via static code review of the fallback logic, `app.py` integration points, and the test suite.

---

## 🔴 Critical Bugs

### Bug 1 — Engulfing Trend Variable Reused From Hammer Block

**File:** `pattern_detection.py` → `_detect_candlestick_fallback()`

`is_downtrend` and `is_uptrend` are computed once for the Hammer/Shooting Star block (around lines 80–81), then silently reused in the Bullish and Bearish Engulfing checks further down. If the Hammer block already evaluated and set `is_downtrend = True`, the Bearish Engulfing condition will also use the same variable — meaning a bearish candle that engulfs a bullish one in a downtrend can pass the wrong trend guard and be emitted as a bullish signal.

**Current (broken):**
```python
# Set once, for Hammer
is_downtrend = c1 < c2 or c0 < c1

# ...later in the Engulfing block, this same variable is reused implicitly
if is_downtrend and body0 > 0 and body1 < 0 and o0 < c1 and c0 > o1:
    results["Engulfing"] = 100  # Bullish Engulfing — uses Hammer's is_downtrend!
```

**Fix — re-evaluate trend context inline inside each engulfing block:**
```python
# Bullish Engulfing — needs a prior downtrend context
is_downtrend_ctx = (c1 < c2)
if is_downtrend_ctx and body0 > 0 and body1 < 0 and o0 < c1 and c0 > o1:
    results["Engulfing"] = 100

# Bearish Engulfing — needs a prior uptrend context
is_uptrend_ctx = (c1 > c2)
if is_uptrend_ctx and body0 < 0 and body1 > 0 and o0 > c1 and c0 < o1:
    results["Engulfing"] = -100
```

---

### Bug 2 — Hammer Downtrend Condition Too Loose (OR instead of AND)

**File:** `pattern_detection.py` → `_detect_candlestick_fallback()`

`is_downtrend = c1 < c2 or c0 < c1` — the `or` makes the condition true whenever *any single* prior bar is lower, which includes flat and ranging markets. A stock that is sideways but happened to close slightly lower yesterday will trigger Hammer detection incorrectly, generating false bullish signals in non-trending conditions.

**Current (over-fires):**
```python
is_downtrend = c1 < c2 or c0 < c1  # True even in sideways markets
```

**Fix — require both prior bars to be declining (AND):**
```python
is_downtrend = c1 < c2 and c0 <= c1  # Both bars must confirm the downtrend
```

---

### Bug 3 — Morning Star / Evening Star Gap Condition References Wrong Anchor

**File:** `pattern_detection.py` → `_detect_candlestick_fallback()`

The Morning Star gap check `is_gap_down = max(o1, c1) < c2` compares the star candle's body top against `c2` — the *close* of the prior big bearish candle. The correct reference point is the *body of the prior bearish candle* — i.e. `min(o2, c2)` (the bottom of its body). As written, the condition is almost never satisfied on NSE stocks (which rarely gap more than the full prior close) and fires incorrectly when it does satisfy. The Evening Star has the same mirror issue.

**Current (wrong reference):**
```python
is_gap_down = max(o1, c1) < c2        # Morning Star — compares against prior CLOSE, not prior body bottom
is_gap_up   = min(o1, c1) > c2        # Evening Star — compares against prior CLOSE, not prior body top
```

**Fix — compare against the prior candle's body extremes:**
```python
# Morning Star: star body must be below the bottom of the prior bearish candle's body
is_gap_down = max(o1, c1) < min(o2, c2)

# Evening Star: star body must be above the top of the prior bullish candle's body
is_gap_up   = min(o1, c1) > max(o2, c2)
```

---

## 🟡 Logic Issues

### Issue 4 — Zero-Range Candle Guard Triggers Spurious Doji

**File:** `pattern_detection.py` → `_detect_candlestick_fallback()`

When `range0 == 0` (e.g. a trading halt or data gap), you set `range0 = 1e-5` to avoid division by zero. But `body0` will also be ~0 in that case, so `body0 <= 0.1 * 1e-5` evaluates to `True`, labelling every zero-move candle as a Doji. This inflates Doji counts on illiquid NSE stocks that frequently halt mid-session.

**Fix — early exit for zero-range candles before any pattern check:**
```python
# At the start of _detect_candlestick_fallback, after building range0:
if range0 <= 1e-4:
    return results   # No meaningful candle — skip all pattern detection
```

---

### Issue 5 — Stage 2 Camp Uses First `.index()` for Minimum Low

**File:** `app.py` → `classify_technical_pattern()`

```python
leg_start_idx = slice_start + lows[slice_start:slice_end].index(min_low_in_slice)
```

Python's `list.index()` returns the **first** (earliest) occurrence of the value. If the minimum low appears more than once across the slice (common in consolidating NSE stocks), `leg_start_idx` is anchored to an older, irrelevant low — inflating `stage1_gain` by measuring from an earlier base instead of the most recent impulse start.

**Fix — use the last (most recent) occurrence:**
```python
sub = lows[slice_start:slice_end]
leg_start_idx = slice_start + len(sub) - 1 - sub[::-1].index(min_low_in_slice)
```

---

### Issue 6 — Cup & Handle Left-Peak Index Same `.index()` Problem

**File:** `app.py` → `classify_technical_pattern()`

```python
local_idx = highs[slice_start:-25].index(cup_left_high)
```

Same first-occurrence issue as Issue 5. If the left-cup high appears multiple times, the earliest occurrence is selected — which places the cup-left anchor too far back in history, making the measured cup depth and handle width unreliable.

**Fix — use numpy argmax for the correct (last/most prominent) peak:**
```python
sub = highs[slice_start:-25]
local_idx = int(np.argmax(sub))   # returns index of the maximum value; handles ties predictably
```

---

### Issue 7 — `cache_valid = True` Set Before JSON Parse (Silent Stale Cache Bug)

**File:** `app.py` → `analyze_single_stock()`

In the DB cache-read block, `cache_valid = True` is set **before** `json.loads(cand_json)` is called. If `cand_json` is `NULL` (a row that was inserted before the `candlestick_json` column was added via `ALTER TABLE`), `json.loads(None)` raises a `TypeError`. The outer `except Exception: pass` catches it — but `cache_valid` is already `True`, so the code never re-fetches live pattern data. That ticker is permanently returned with `candlestick_patterns = {}` until the DB row is manually deleted.

**Current (broken ordering):**
```python
try:
    gen_time = datetime.fromisoformat(gen_at_str)
    if (datetime.now() - gen_time).total_seconds() < 24 * 3600:
        cache_valid = True                         # ← set BEFORE the parse
        stock["candlestick_patterns"] = json.loads(cand_json)  # ← can raise TypeError if NULL
except Exception:
    pass   # cache_valid is already True — stale data locked in permanently
```

**Fix — move `cache_valid = True` to after the successful parse:**
```python
try:
    gen_time = datetime.fromisoformat(gen_at_str)
    if (datetime.now() - gen_time).total_seconds() < 24 * 3600:
        stock["pattern_name"]          = p_name
        stock["pattern_grade"]         = p_grade
        stock["pattern_desc"]          = p_desc
        stock["candlestick_patterns"]  = json.loads(cand_json) if cand_json else {}
        cache_valid = True             # ← set AFTER successful parse
except Exception:
    pass   # parse failure → cache_valid stays False → live re-fetch triggered
```

---

## 🟢 Improvements

### Improvement 8 — TA-Lib Doji Hardcodes Bullish `100` Regardless of Context

**File:** `pattern_detection.py` → `detect_candlestick_patterns()` (TA-Lib path)

```python
if doji[-1] != 0:
    results["Doji"] = 100   # ← always bullish, ignores TA-Lib's actual returned sign
```

TA-Lib's `CDLDOJI` returns `-100` when the doji appears in a bearish context (e.g., as a gravestone doji at the top of an uptrend) and `+100` in a bullish context. Hardcoding `100` masks bearish doji signals entirely, which matters when feeding into the Kronos bias calculation.

**Fix:**
```python
if doji[-1] != 0:
    results["Doji"] = int(doji[-1])   # preserve TA-Lib's directional sign
```

---

### Improvement 9 — Candlestick Priority List Should Be Signal-Strength Ordered

**File:** `app.py` → `classify_technical_pattern()` (candlestick fallback block)

The fallback iterates a hardcoded list `['Morning Star', 'Evening Star', 'Hammer', 'Shooting Star', 'Engulfing', 'Doji']` and returns on the first match. If two patterns fire simultaneously (e.g., a candle that is both a Hammer and technically a Doji), the first item in the list wins regardless of signal strength. Higher-confidence multi-candle patterns (Morning/Evening Star) should win over single-candle ones, and among same-rank patterns the one with the higher absolute value should win.

**Fix — sort by absolute signal value descending before iterating:**
```python
# Instead of iterating the hardcoded priority list:
for p in sorted(candlesticks, key=lambda k: abs(candlesticks[k]), reverse=True):
    if candlesticks[p] != 0:
        # use this pattern as the primary signal
        break
```

---

### Improvement 10 — Missing Test Coverage in `tests/test_pattern_detection.py`

Two gaps in the test suite that would have caught Bug #1 earlier:

**Gap A — `test_detect_doji()` has no negative assertions:**
A Doji candle (tiny body, large wicks) can also superficially resemble a Hammer shape. The test only asserts `'Doji' in result`; it does not verify that Hammer and Shooting Star do NOT co-fire.

```python
def test_detect_doji():
    # ... existing assertions ...
    assert result.get("Doji") != 0, "Doji should be detected"
    # ADD these negative assertions:
    assert result.get("Hammer", 0) == 0,         "Hammer must NOT co-fire on a Doji candle"
    assert result.get("Shooting Star", 0) == 0,  "Shooting Star must NOT co-fire on a Doji candle"
```

**Gap B — No test for Bearish Engulfing (`result["Engulfing"] == -100`):**
Only Bullish Engulfing is tested. Bug #1 (shared trend variable) directly affects bearish engulfing detection and would have been caught immediately with this test.

```python
def test_detect_bearish_engulfing():
    """Bearish Engulfing: prior uptrend, current red candle fully engulfs prior green candle."""
    data = {
        "open":  [95.0, 98.0, 102.0, 97.0, 100.0, 103.0, 96.0],   # uptrend context
        "high":  [99.0, 102.0, 105.0, 101.0, 104.0, 108.0, 107.0],
        "low":   [94.0, 97.0, 101.0, 96.0, 99.0, 102.0, 94.0],
        "close": [98.0, 101.0, 104.0, 100.0, 103.0, 107.0, 95.0],  # last candle: big red engulfer
    }
    result = detect_candlestick_patterns(data)
    assert result.get("Engulfing") == -100, \
        f"Expected Bearish Engulfing (-100), got {result.get('Engulfing')}"
```

---

## Consolidated Fix Priority

| # | Severity | File | Impact on Signal Quality |
|---|----------|------|--------------------------|
| 1 | 🔴 Critical | `pattern_detection.py` | Wrong engulfing direction due to shared trend variable — directly corrupts bullish/bearish labels |
| 2 | 🔴 Critical | `pattern_detection.py` | False Hammers in flat/ranging NSE markets — over-fires on sideways consolidation |
| 3 | 🔴 Critical | `pattern_detection.py` | Morning/Evening Star almost never fires correctly on NSE intraday gaps |
| 7 | 🟡 High | `app.py` | NULL `cand_json` rows permanently bypass live re-fetch — silent stale data |
| 4 | 🟡 Medium | `pattern_detection.py` | Trading halt candles falsely labelled Doji |
| 5 | 🟡 Medium | `app.py` | Stage 2 Camp `stage1_gain` inflated by wrong leg anchor |
| 6 | 🟡 Medium | `app.py` | Cup & Handle left-peak anchored to earliest (wrong) occurrence |
| 8 | 🟢 Low | `pattern_detection.py` | TA-Lib Doji always emits bullish `100`, hides bearish context |
| 9 | 🟢 Low | `app.py` | Fixed-list pattern priority should be signal-strength ordered |
| 10 | 🟢 Low | `tests/test_pattern_detection.py` | Missing negative assertions + bearish engulfing test case |

> **Fix order recommended:** Bugs 1 → 3 first (they corrupt the signal fed to Kronos), then Issue 7 (silent cache stale), then Issues 4–6, then Improvements 8–10.
