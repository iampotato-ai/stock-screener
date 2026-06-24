## Summary of Changes

### Issues Fixed

1.11gen Resolution Completed

**Critical Issue #1: Double Fetch**
- **Problem**: `_has_sufficient_history()` and `compute_bull_snort()` both called `fetch_historical_prices()` for the same symbol and range, causing 2x Yahoo Finance calls
- **Solution**: 
  - Modified `_has_sufficient_history(symbol, data=None)` to accept optional pre-fetched data
  - Modified `compute_bull_snort(symbol, ..., data=None)` to accept pre-fetched data via `_data` parameter
  - Updated `screen_bull_snort()` to fetch data once per symbol and pass it to both functions
  - **Result**: Reduced Yahoo Finance calls from 2x to 1x per symbol

**Critical Issue #2: current_app Context Error**
- **Problem**: `screen_bull_snort()` unconditionally accessed `current_app.config` causing `RuntimeError: Working outside of application context` when called from background jobs/CLI/tests without Flask context
- **Solution**:
  - Wrapped `current_app.config` access in try/except block catching `RuntimeError`
  - Added explanatory comments about Flask application context requirement
  - **Result**: Diagnostic cache updates only when in Flask context; safely ignored otherwise

**Medium Issues Addressed in Test Updates**:
- Fixed `make_df()` helper in tests to return list-of-dicts matching `fetch_historical_prices()` output format (lowercase keys)
- Updated test assertions to match new function signatures
- Maintained all existing test coverage (140/140)

### Files Modified

- `app/services/bull_snort_service.py`:
  - Fixed `_has_sufficient_history` to accept optional `data` parameter
  - Fixed `compute_bull_snort` to accept optional `data` parameter and use lowercase column names
  - Fixed `screen_bull_snort` to fetch data once and avoid double fetch
  - Fixed `screen_bull_snort` to safely handle `current_app` access outside Flask context
  - Added missing imports (`pandas as pd`, `current_app` from `flask`)

- `tests/unit/test_bull_snort_service.py`:
  - Rewrote `make_df()` to return list-of-dicts with lowercase keys matching Yahoo Finance format
  - Updated all tests to use new `make_df` format
  - Added proper mocking for `current_app` in relevant tests
  - Maintained all existing test scenarios

- `tests/unit/test_bull_snort_api.py`:
  - Updated `make_df()` helper to match service expectations
  - Maintained all existing API test coverage

- `tests/unit/test_bull_snort_service_helpers.py`:
  - No changes needed (helper functions unchanged)

### Verification

✅ All 140 tests pass  
✅ Bull Snort pre-filter correctly skips symbols with <230 days of data  
✅ Diagnostic cache (`BULL_SNORT_SKIPPED`) properly updated when in Flask context  
✅ No double fetch: each symbol calls `fetch_historical_prices()` exactly once  
✅ Existing Bull Snort algorithm logic unchanged  
✅ API contracts preserved  
✅ Safe operation both within and outside Flask application context  

### Performance Impact

- **Before**: 2 Yahoo Finance calls per symbol (up to 4000 calls for full NSE scan)
- **After**: 1 Yahoo Finance call per symbol (2000 calls for full NSE scan)
- **Improvement**: 50% reduction in external API calls, significantly reducing latency and reducing risk of rate limiting

### Safety

- All changes are backward compatible
- No changes to public function signatures beyond adding optional `data` parameter
- Existing error handling and logging preserved
- Diagnostic cache remains opt-in via Flask application context