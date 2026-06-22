# EP Screener Module — Review & Improvement Plan

## Overview

The EP (Episodic Pivot) Screener is a multi-tab workspace for identifying and tracking stocks undergoing fundamental repricing events. It spans five sub-tabs — **Today**, **Watchlist**, **Sugar Babies**, **Themes & Rotation**, and **Backtest** — backed by `/api/ep/*` endpoints and `ipo_service.py` on the backend. This document catalogues every identified issue, missing feature, and improvement opportunity across the full stack.

---

## Architecture Summary

| Layer | Files |
|---|---|
| Frontend UI | `templates/index.html` (lines ~1260–1860), `static/js/app.js` (lines ~11230–11930) |
| API endpoints | `app/api/v1/ep_watchlist.py`, `app/api/v1/ipo.py` |
| Business logic | `app/services/ipo_service.py` |
| Data access | `app/database.py`, `app/models.py` |

The EP screener shares `ipo_service.py` with the IPO Momentum workspace, which is an architectural concern addressed below.

---

## 1. Critical Issues

### 1.1 EP and IPO Logic Live in the Same Service File

`ipo_service.py` handles both IPO momentum metrics and EP screener operations. These are conceptually distinct domains — IPOs are new listings being tracked over time, while EPs are established stocks undergoing repricing events. Mixing them creates:

- A single file growing disproportionately large (already 22KB)
- Naming confusion (`IPOService` vs EP-related methods)
- Difficulty writing isolated unit tests for EP-specific logic

**Fix:** Extract EP-related methods into a dedicated `app/services/ep_service.py`. The `IPOService` class retains only `get_ipo_listings`, `get_ipo_detail`, `refresh_ipo_metrics`, and `_refresh_ipo_metrics_internal`.

### 1.2 `epDetailListenersBound` Flag — One-Time Binding Bug

In `openEPDetailModal()` (app.js ~line 11595), action button event listeners (Add to Watchlist, Mark Triggered, Remove, Add Sugar Baby) are bound inside a `if (!window.epDetailListenersBound)` guard. This means:

- Listeners are bound only on the **first** modal open
- On subsequent opens, `symbol` captured in the closure is **stale** — it still refers to the ticker from the first open
- Any watchlist/sugar action taken on a second or third EP stock will silently act on the wrong ticker

**Fix:** Remove the `epDetailListenersBound` guard. Instead, remove and re-add listeners on every modal open using `btn.replaceWith(btn.cloneNode(true))` or by storing and removing named handler functions.

### 1.3 `days_since_listing` Recalculation in `get_ipo_listings`

The service recalculates `days_since_listing` dynamically in Python for every row on every request to prevent staleness. However, the `ipo_metrics_cache` table is still filtered with `WHERE days_since_listing <= ?` using the **cached** (potentially stale) DB value. A stock right on the boundary could be excluded from results even though it qualifies dynamically.

**Fix:** Replace the `WHERE days_since_listing <= ?` filter with a date arithmetic filter: `WHERE julianday('now') - julianday(listing_date) <= ?`. This makes both filtering and display consistent.

---

## 2. Backend Issues

### 2.1 `COUNT(DISTINCT company_name)` for Deduplication is Fragile

In `get_ipo_listings`, when `exchange_param == 'all'`, the count uses `DISTINCT company_name` to avoid double-counting NSE+BSE dual-listed stocks. Company name strings are not guaranteed to be identical across exchanges (e.g., abbreviations, punctuation differences), so this deduplication is unreliable.

**Fix:** Add a `canonical_id` or use `DISTINCT ticker` where the ticker is normalised across exchanges, or add a `is_primary_listing` boolean column to `ipo_metrics_cache`.

### 2.2 No Pagination on EP `/api/ep/today`

The EP listings endpoint appears to return all results without server-side pagination. On days with many EP signals, this creates large payloads and slow renders.

**Fix:** Add `limit` and `offset` query params to `/api/ep/today` matching the pattern already in `get_ipo_listings`. Update `fetchEPListings()` in the frontend to support infinite scroll or page controls.

### 2.3 `_refresh_ipo_metrics_internal` Has No Error Recovery Per Row

The `_update_single(row)` function processes each IPO row individually. If a fetch or calculation fails for one row (e.g., network timeout for a specific ticker), the exception propagates and cancels the entire refresh batch.

**Fix:** Wrap `_update_single(row)` in a `try/except` with logging, continuing to the next row on failure. This makes the refresh resilient to individual ticker failures.

### 2.4 Raw SQL in Service Methods

Several methods in `ipo_service.py` use raw `conn.cursor().execute(...)` instead of the SQLAlchemy models in `app/models.py`. The `IpoMetricsCache` and `IpoListing` models exist but are not used for queries.

**Fix:** Migrate `get_ipo_listings` and `get_ipo_detail` to use SQLAlchemy ORM queries. This enables proper query composition, type safety, and consistent test mocking.

### 2.5 Allowed Sort Columns Whitelist is Hardcoded

`get_ipo_listings` defines `allowed_sort_cols` as a hardcoded list. If `ipo_metrics_cache` schema changes (column added/removed), this list must be manually updated or sort silently falls back to `listing_date`.

**Fix:** Either derive the allowed columns from the `IpoMetricsCache` model's `__table__.columns`, or centralise the list as a class-level constant with a clear comment.

---

## 3. Frontend Issues

### 3.1 EP Backtest Sub-Tab — `initEPBacktestDashboard` Status Unknown

`loadEPSubTab` calls `initEPBacktestDashboard()` for the `backtest` sub-tab. No definition of this function was found in `app.js`. This is either a stub that silently fails, or is defined elsewhere. Either way it needs to be verified.

**Action:** Search for `initEPBacktestDashboard` definition. If missing, implement or display a "Coming Soon" placeholder instead of a silent no-op.

### 3.2 EP Themes & Rotation Sub-Tab — `loadEPThemesAndRotation` Needs Audit

`loadEPThemesAndRotation()` populates `#ep-themes-container` but no backend endpoint or service method for themes was visible in the codebase review. The container max-height is hardcoded at `500px` with overflow scroll, which is a poor UX pattern for variable content.

**Action:** Confirm `/api/ep/themes` or equivalent exists and returns data. Replace fixed max-height with a proper flex layout.

### 3.3 EP Table Columns Have No Tooltips

The EP screener table header has columns like `Neglect`, `Catalyst`, `Repricing`, `Close Loc`, `RVOL` with no tooltip or explanation. Unlike the main screener table (which has `tooltip` properties on column definitions), these are bare `<th>` elements.

**Fix:** Add `title` attributes or a tooltip system consistent with the main screener table's column definitions pattern.

### 3.4 EP Filter Bar Uses Inline Styles Throughout

The EP filter bar in `index.html` (~lines 1270–1420) is entirely inline-styled. This makes responsive layout adjustments, theming, and maintenance difficult. The IPO workspace uses CSS classes like `.ipo-filters-bar`, `.ipo-btn-group`.

**Fix:** Extract EP filter styles into dedicated CSS classes `.ep-filters-bar`, `.ep-filter-group`, `.ep-select-btn` in `style.css`.

### 3.5 `epListingsData` Not Reset on Filter Change

`fetchEPListings()` checks `if (tbody && epListingsData.length === 0)` to show a loading state. When filters change and a new fetch is triggered, `epListingsData` still holds stale results during the fetch, so the loading state is never shown. The user sees old data until the new fetch completes.

**Fix:** Reset `epListingsData = []` at the start of each `fetchEPListings()` call, before the fetch begins.

### 3.6 Min Score Filter Hardcoded Default of 0.55

The Min Score filter (`#filter-ep-min-score`) defaults to `0.55` hardcoded in HTML. This threshold is significant — it silently filters out many candidates without users realising it's active.

**Fix:** Default to `0.0` (show all), or add a visual indicator (e.g., a yellow border or "Active" label) when a filter is set above the minimum.

---

## 4. UX & Feature Gaps

### 4.1 No Sorting on Watchlist and Sugar Babies Tables

The EP Listings table has `data-sort` attributes on all headers and a full sort implementation. The **Watchlist** (`#ep-watchlist-table`) and **Sugar Babies** (`#ep-sugar-table`) tables have no sortable columns — headers are plain `<th>` elements.

**Fix:** Add `data-sort` attributes and wire up sort handling consistent with the main EP table's implementation.

### 4.2 EP Detail Modal Has No Chart

The EP detail modal (`#ep-detail-modal`) shows EP score, confidence, fundamentals, and catalyst events — but no price chart. The trade drawer has a full TradingView chart integration. Users need to click "Open Chart" separately, breaking the workflow.

**Fix:** Embed a lightweight chart (using the existing LightweightCharts library already loaded in the app) in the EP detail modal, similar to `drawer-tv-chart-container` in the trade drawer.

### 4.3 Sugar Babies Has No Explanation or Criteria

The "Sugar Babies" tab has no descriptive header or criteria definition visible in the UI. New users have no indication of what qualifies a stock as a "Sugar Baby" or how it differs from the Watchlist.

**Fix:** Add a small info banner at the top of the Sugar Babies panel explaining the concept (e.g., high-confidence EPs held for a longer swing trade).

### 4.4 No Bulk Actions on Watchlist

Users can only act on one EP watchlist item at a time via the detail modal. There is no way to bulk-remove, bulk-trigger, or bulk-export watchlist entries.

**Fix:** Add row-level checkboxes and a bulk action toolbar (Remove Selected, Export CSV) consistent with the journal's multi-select pattern.

### 4.5 EP Score Trend Not Shown

The EP score is shown as a point-in-time value. There is no indication of whether it's rising or falling over the day/week. A score of 0.72 that was 0.90 yesterday is very different from one that was 0.55.

**Fix:** Store score snapshots in the EP watchlist table and show a small delta badge (e.g., `▲ +0.05`) next to the current score.

### 4.6 No Mobile / Responsive Layout for EP Workspace

The EP workspace uses a fixed-width table with 14 columns. On screens narrower than ~1100px, the table overflows horizontally with no horizontal scroll affordance or column hiding strategy.

**Fix:** Add a horizontal scroll container on the table wrapper for small screens, and consider collapsing less critical columns (e.g., `Avg Turnover`) on screens below 768px using CSS `display: none` at a breakpoint.

---

## 5. Data & Scoring Issues

### 5.1 `neglect_score`, `catalyst_score`, `repricing_score` — Computation Not Visible

The three component scores displayed in the EP table are fetched from the API but their computation logic was not found in `ipo_service.py` or `app/database.py` in this review. If they are computed in a legacy route or raw SQL, they should be migrated to `ep_service.py` with documented scoring criteria.

**Action:** Locate the scoring computation. Document the scoring formula for each component in a docstring and add unit tests for edge cases (zero volume, missing fundamentals).

### 5.2 `ep_score` Confidence Levels Have No Documented Thresholds

The confidence field shows `HIGH`, `MEDIUM`, `LOW` but the thresholds that map `ep_score` to these levels are not visible in the reviewed code. These thresholds may be hardcoded in a legacy route.

**Fix:** Define thresholds as named constants in `app/utils/constants.py`:
```python
EP_CONFIDENCE_HIGH   = 0.75
EP_CONFIDENCE_MEDIUM = 0.55
EP_CONFIDENCE_LOW    = 0.0
```

### 5.3 Fundamentals in EP Detail Modal Show Historical Quarters But No Trend Indicator

The fundamentals table in `#ep-detail-fundamentals-body` lists quarterly data but shows raw numbers without any QoQ trend arrow or colour coding. A revenue figure means little without context of direction.

**Fix:** Add a trend column computed server-side (or client-side from the array of values) showing `▲`, `▼`, or `—` with green/red colouring.

---

## 6. Code Quality Issues

### 6.1 `renderEPListingsTable` Builds HTML via String Concatenation

The EP table renderer constructs rows via template literal string concatenation — the same pattern the main screener originally used. This is harder to maintain and debug than a DOM-based or component approach.

**Fix:** Not urgent, but worth refactoring alongside any major EP table changes. Consider extracting a `renderEPRow(ep)` function for readability.

### 6.2 Multiple `fetch('/api/ep/...')` Calls Not Centralised

API calls to `/api/ep/today`, `/api/ep/:symbol/detail`, `/api/ep/watchlist`, `/api/ep/sugar-babies`, etc. are scattered across `fetchEPListings`, `openEPDetailModal`, `fetchEPWatchlist`, and `fetchEPSugarBabies` without a centralised API client or error handling pattern. Each has its own error handling (or lacks it entirely).

**Fix:** Create a small `EP_API` object (similar to how some apps centralise fetch calls) with methods like `EP_API.getToday(params)`, `EP_API.getDetail(symbol)`, `EP_API.addToWatchlist(data)` — all sharing a common error handler.

### 6.3 No Loading/Error States for Themes and Sugar Babies

`fetchEPSugarBabies` and `loadEPThemesAndRotation` don't have consistent loading skeleton states like `fetchEPListings` does (which at least sets `colspan` loading text). If the fetch is slow, the panel appears empty with no feedback.

**Fix:** Add the same loading placeholder pattern used in `fetchEPListings` to all sub-tab fetch functions.

---

## Priority Summary

| Priority | Issue | Effort |
|---|---|---|
| 🔴 Critical | `epDetailListenersBound` stale closure bug | Low |
| 🔴 Critical | EP + IPO service separation | Medium |
| 🔴 Critical | `days_since_listing` filter vs display inconsistency | Low |
| 🟡 High | Pagination on `/api/ep/today` | Medium |
| 🟡 High | `epListingsData` not reset on filter change | Low |
| 🟡 High | No chart in EP detail modal | High |
| 🟡 High | Neglect/Catalyst/Repricing score computation undocumented | Medium |
| 🟡 High | Confidence thresholds not centralised | Low |
| 🟠 Medium | Sortable Watchlist and Sugar Babies tables | Medium |
| 🟠 Medium | EP filter bar inline styles → CSS classes | Medium |
| 🟠 Medium | Bulk actions on EP watchlist | High |
| 🟠 Medium | Fundamentals trend indicator in detail modal | Low |
| 🟠 Medium | Min Score default misleading | Low |
| 🟢 Low | Responsive/mobile layout for EP workspace | Medium |
| 🟢 Low | Sugar Babies explanation banner | Low |
| 🟢 Low | EP score delta trend badge | Medium |
| 🟢 Low | Column tooltips on EP table headers | Low |
