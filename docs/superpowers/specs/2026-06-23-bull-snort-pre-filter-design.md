# Bull Snort Pre‑filter Design Specification

## 1. Objective
Add a lightweight pre‑filter to the Bull Snort screen endpoint that silently skips any symbol whose price‑history DataFrame contains fewer than **230 rows**. The existing `len(history) < 230` guard inside `compute_bull_snort` remains unchanged, preserving the statistical baseline.

## 2. Scope
- Affects only the bulk‑screen API (`/api/bull_snort/screen`).
- Single‑symbol endpoint (`/api/bull_snort/single`) continues to return `null` for insufficient data.
- No change to the public API contract: callers still receive a JSON list with HTTP 200.
- Optional diagnostic cache (`BULL_SNORT_SKIPPED`) for internal debugging; not exposed to clients.

## 3. Architecture & Data Flow
```
[client] → GET/POST /api/bull_snort/screen
    └─► bull_snort_screen() (api/v1/bull_snort.py)
           │
           ├─► Parse parameters, assemble symbol list
           │
           └─► screen_bull_snort(symbols, …) (services/bull_snort_service.py)
                  │
                  ├─► for each symbol:
                  │     ├─► _has_sufficient_history(symbol)
                  │     │     └─► fetch_historical_prices(..., range_str="2y")
                  │     │           → DataFrame
                  │     │           → len(df) >= 230 ?
                  │     ├─► if False: continue (silent skip)
                  │     └─► if True: compute_bull_snort(symbol, …)
                  │           → may still return None (original guard)
                  │
                  └─► Collect non‑None results → return list
```

## 4. Implementation Details (pseudo‑code)
```python
# app/services/bull_snort_service.py
MIN_ROWS_REQUIRED = 230

def _has_sufficient_history(symbol: str) -> bool:
    """Return True iff the symbol has at least MIN_ROWS_REQUIRED rows of history."""
    hist = fetch_historical_prices(symbol, range_str="2y")
    return bool(hist) and len(hist) >= MIN_ROWS_REQUIRED

def screen_bull_snort(
    symbols: List[str],
    vol_avg_period: int = DEFAULT_VOL_AVG_PERIOD,
    vol_surge_min: float = DEFAULT_VOL_SURGE_MIN,
    close_position_min: float = DEFAULT_CLOSE_POSITION_MIN,
    min_gap_history: float = DEFAULT_MIN_GAP_HISTORY,
    max_current_gap: float = DEFAULT_MAX_CURRENT_GAP,
) -> List[Dict[str, Any]]:
    """Run compute_bull_snort for each symbol, silently skipping those with
    insufficient historical rows.
    """
    results = []
    skipped = []
    for sym in symbols:
        if not _has_sufficient_history(sym):
            skipped.append(sym)
            continue  # silent skip
        res = compute_bull_snort(
            sym,
            vol_avg_period=vol_avg_period,
            vol_surge_min=vol_surge_min,
            close_position_min=close_position_min,
            min_gap_history=min_gap_history,
            max_current_gap=max_current_gap,
        )
        if res:
            results.append(res)

    if skipped:
        # optional diagnostic cache – does not affect API contract
        current_app.config.setdefault('BULL_SNORT_SKIPPED', set()).update(skipped)

    return results
```
*The existing `compute_bull_snort` still contains the `len(history) < 230` guard and returns `None` when a symbol fails any phase.*

## 5. Testing Strategy
- **Unit test** `test_pre_filter_skips_short_history` – mock `fetch_historical_prices` to return a DataFrame with < 230 rows; verify `screen_bull_snort` returns an empty list (or only other symbols). Verify the symbol is not passed to `compute_bull_snort`.
- **Unit test** `test_pre_filter_allows_long_history` – mock a DataFrame with ≥ 230 rows; ensure `compute_bull_snort` is called and its result appears in the output.
- **Integration test** `test_bull_snort_screen_pre_filter` – patch `_has_sufficient_history` to return `False` for a specific symbol; confirm the JSON response omits that symbol and HTTP status remains 200.
- **Optional diagnostic cache test** – after a call with skipped symbols, assert that `current_app.config['BULL_SNORT_SKIPPED']` contains the expected IDs.
- Run full test suite (`pytest`) to ensure existing tests remain green.
- Coverage target: **≥ 85 %** for the new helper and updated `screen_bull_snort`.

## 6. Documentation Updates
- Add a **Pre‑filter** subsection to `docs/features/BULL_SNORT_FILTER.md` describing the silent‑skip behavior.
- Include a changelog entry: *Add silent pre‑filter for insufficient‑data symbols in Bull Snort screen.*

## 7. Acceptance Checklist
- [ ] API `/bull_snort/screen` returns HTTP 200 with a list that excludes symbols having < 230 rows.
- [ ] No error or warning is emitted to the client for those symbols.
- [ ] Single‑symbol endpoint behavior unchanged.
- [ ] New unit and integration tests pass; overall coverage ≥ 85 % for the updated module.
- [ ] Documentation reflects the new pre‑filter.
- [ ] All existing tests continue to pass.

---
## 8. Latest Implementation Plan
The pre‑filter is part of a broader set of enhancements to the Bull Snort feature. The current roadmap includes:

1. **SQLite price cache** – Add a `historical_prices` table (`ticker`, `range_str`, `price_json`, `cached_at`) with a primary key on `(ticker, range_str)` and an index on `cached_at`.
2. **Cache helper functions** – Implement `get_cached_history(ticker, range_str="6mo")` and `set_cached_history(ticker, range_str, price_data)` in `app/utils/technical.py`, importing `json`, `datetime`, and `get_db_connection`.
3. **Fetch integration** – Extend `fetch_historical_prices` to check the in‑memory LRU cache, then the SQLite cache, and finally Yahoo Finance. Store successful remote fetches in both caches.
4. **Nightly purge job** – Add `purge_historical_price_cache` in `app/tasks/scheduler.py` to delete rows older than 7 days (or 30 days) and schedule it (e.g., daily at 02:00 AM) via APScheduler.
5. **UI table header** – Insert `<th>Date</th>` (and adjust colspan if needed) into the Bull Snort table header in `templates/index.html`.
6. **Row rendering** – Update the Bull Snort rendering loop in `static/js/app.js` to output a date cell, display a “New” badge when the breakout date equals today, and apply a highlight CSS class to those rows.
7. **Result count label** – Enhance the UI count label (e.g., `#bull-snort-result-count`) to display both total results and the number of “new today” signals.
8. **Testing** – Add unit tests for the SQLite cache helpers, integration tests for the fetch logic, and a Playwright UI test verifying badge/highlight behavior and updated count label.
9. **Verification** – Run the full test suite (`pytest && python -m pytest -q e2e/tests/*.py`) to ensure all existing tests pass and coverage thresholds are met.
10. **Commit workflow** – Apply each logical change in a separate commit on the `feature/workspace-ui` branch, keeping the design spec staged and committed alongside the code changes.

---
*Design approved pending user review.*