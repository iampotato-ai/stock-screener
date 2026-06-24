# Bull Snort Pre‑filter Implementation Plan

## Objective
Add a lightweight pre‑filter to `/api/bull_snort/screen` that silently skips symbols with fewer than 230 rows of price history, while preserving the existing guard inside `compute_bull_snort`.

## Scope
- Modify `app/services/bull_snort_service.py`:
  - Add constant `MIN_ROWS_REQUIRED = 230` (already present).
  - Add helper function `_has_sufficient_history(symbol: str) -> bool`.
  - Modify `screen_bull_snort` to skip symbols where the helper returns `False`.
  - Optionally maintain a diagnostic cache `current_app.config['BULL_SNORT_SKIPPED']`.
- No changes to `compute_bull_snort` (retains its own `len(history) < 230` guard).
- No changes to the API contract: endpoints still return HTTP 200 with `{ "data": [...] }`.
- Add unit tests for the new helper and the modified screen function.
- Add integration test for the `/bull_snort/screen` endpoint.
- Update documentation (`docs/features/BULL_SNORT_FILTER.md`) with a “Pre‑filter” subsection.
- Add a changelog entry.

## Detailed Steps

### 1. Restore the full Bull Snort service implementation
The current `app/services/bull_snort_service.py` is missing the function bodies (only constants and docstring remain). We will restore the implementation from the previous commit (HEAD~1) as the base for our changes.

**File:** `app/services/bull_snort_service.py`
- Replace the file contents with the version from `HEAD~1` (which includes the full implementation of `compute_bull_snort`, `screen_bull_snort`, `_score_base_accumulation`, `_compute_final_score`, and helper functions).
- After restoring, verify that the file compiles and passes existing tests.

### 2. Add the pre‑filter helper
**File:** `app/services/bull_snort_service.py`
- Below the existing constants, add:
  ```python
  MIN_ROWS_REQUIRED = 230  # already present; keep if not duplicated

  def _has_sufficient_history(symbol: str) -> bool:
      """Return True iff the symbol has at least MIN_ROWS_REQUIRED rows of history."""
      hist = fetch_historical_prices(symbol, range_str="2y")
      return bool(hist) and len(hist) >= MIN_ROWS_REQUIRED
  ```
- Import `current_app` from `flask` if we plan to use the diagnostic cache (see step 4).

### 3. Modify `screen_bull_snort` to incorporate the pre‑filter
**File:** `app/services/bull_snort_service.py`
- Locate the `screen_bull_snort` function.
- At the start of the loop over `symbols`, add:
  ```python
      results = []
      skipped = []  # for optional diagnostic cache
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
  ```
- After the loop, if `skipped` is not empty, update the diagnostic cache:
  ```python
      if skipped:
          # optional diagnostic cache – does not affect API contract
          current_app.config.setdefault('BULL_SNORT_SKIPPED', set()).update(skipped)
  ```
- Ensure we import `current_app` from `flask` at the top of the file.

### 4. Diagnostic cache (optional but recommended)
- The spec mentions an optional diagnostic cache `BULL_SNORT_SKIPPED` stored in `current_app.config`. We will implement it as a set to avoid duplicates.
- This cache is purely for internal debugging and is not exposed via the API.

### 5. Update unit tests
**File:** `tests/unit/test_bull_snort_service.py`
- Add a test for `_has_sufficient_history`:
  - Mock `fetch_historical_prices` to return a list of length < 230 → assert returns `False`.
  - Mock to return a list of length ≥ 230 → assert returns `True`.
  - Mock to return an empty list → assert returns `False`.
- Add a test for `screen_bull_snort` pre‑filter behavior:
  - Mock `fetch_historical_prices` to return short data for symbol "A" and long data for symbol "B".
  - Mock `compute_bull_snort` to return a dummy result for any symbol (to verify it is not called for "A").
  - Call `screen_bull_snort(["A", "B"])` and assert that the result list contains only the result from "B".
  - Assert that `compute_bull_snort` was called exactly once (for "B").
- Add a test for the diagnostic cache:
  - After calling `screen_bull_snort` with a mix of short and long symbols, assert that `current_app.config['BULL_SNORT_SKIPPED']` contains the expected skipped symbols.

### 6. Update API integration test
**File:** `tests/unit/test_bull_snort_api.py`
- Add a test for `/bull_snort/screen` endpoint that verifies the pre‑filter works:
  - Mock `_has_sufficient_history` (or `fetch_historical_prices`) to return `False` for a specific symbol (e.g., "SKIP") and `True` for another (e.g., "PASS").
  - Mock `screen_bull_snort` to return the expected filtered list (or let it call through to the mocked service).
  - Assert that the JSON response omits the skipped symbol and that the HTTP status is 200.
- Alternatively, we can rely on the unit test of the service and keep the API test focused on the contract; but adding an explicit test for the endpoint is good practice.

### 7. Update documentation
**File:** `docs/features/BULL_SNORT_FILTER.md`
- Add a new section after the existing content, titled “Pre‑filter”:
  ```markdown
  ### Pre‑filter
  The `/bull_snort/screen` endpoint now includes a pre‑filter that silently skips any symbol whose price‑history DataFrame contains fewer than 230 rows (approximately two years of daily data). This avoids unnecessary computation for symbols with insufficient data while preserving the existing guard inside `compute_bull_snort`. The pre‑filter does not alter the API contract: the endpoint still returns HTTP 200 with a JSON list under the `"data"` key.

  An optional diagnostic cache `BULL_SNORT_SKIPPED` (a set of tickers) is maintained in the Flask application context for internal debugging.
  ```
- Add a changelog entry (if a changelog file exists; otherwise, we can add a note in the commit message).

### 8. Verify existing tests still pass
- Run the full test suite (`pytest`) to ensure that the changes do not break any existing functionality.
- Ensure coverage for the new and modified code meets the target (≥ 85 % for the updated module).

## Risks and Mitigations
- **Double fetch of historical data**: The pre‑filter calls `fetch_historical_prices`, and `compute_bull_snort` calls it again for symbols that pass the pre‑filter. This could double the Yahoo Finance requests.
  - **Mitigation**: Accept this inefficiency as per the spec (the existing guard in `compute_bull_snort` is kept for statistical consistency). In the future, consider introducing a caching layer (e.g., the SQLite cache mentioned in the broader roadmap) to avoid redundant network calls.
- **Cache staleness**: The diagnostic cache lives only for the lifetime of the application process; it is not persisted.
  - **Mitigation**: This is acceptable as it is strictly for debugging.
- **Breaking changes**: We are not changing the public API, so existing clients should continue to work unchanged.
- **Testing complexity**: Mocking `fetch_historical_prices` correctly is essential. We will follow the existing test patterns in the test suite.

## Definition of Done
- [ ] The file `app/services/bull_snort_service.py` has been restored to its full implementation and updated with the pre‑filter logic.
- [ ] Unit tests for the new helper and modified screen function pass.
- [ ] Integration test for the `/bull_snort/screen` endpoint passes.
- [ ] All existing tests continue to pass.
- [ ] Documentation reflects the new pre‑filter behavior.
- [ ] A changelog entry has been added.
- [ ] Manual verification: calling `/bull_snort/screen` with a mix of known‑good and known‑short‑history symbols returns the expected filtered list with HTTP 200.

## Next Steps
1. Restore the full service implementation from `HEAD~1`.
2. Implement the pre‑filter helper and modify `screen_bull_snort`.
3. Write and run unit tests.
4. Update documentation.
5. Run the full test suite and verify coverage.
6. Submit for review.

---
*Prepared using Spec‑Driven Development methodology.*