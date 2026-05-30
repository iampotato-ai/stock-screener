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
