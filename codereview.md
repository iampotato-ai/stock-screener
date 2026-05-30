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
