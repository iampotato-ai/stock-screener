# Growth Momentum Signals Fix - Source Real Data from Fundamentals Table

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the growth momentum signals in the stock screener to source real data from the fundamentals table instead of incorrect assignments or leaving them as None when ENABLE_SIMULATED_DATA=false.

**Architecture:** Modify the SQL query in scan_stocks() to explicitly reference needed fundamentals fields and correct the growth metric assignments in compute_extra_fields() to use real QoQ data from the fundamentals table.

**Tech Stack:** Python, Flask, SQLite, SQL

---

## Global Constraints

- Must maintain backward compatibility with existing functionality
- Should not add additional API calls - use data already fetched from TradingView and database
- Must follow existing code patterns and conventions in the codebase
- Should handle missing/null data gracefully with appropriate defaults
- Must integrate seamlessly with existing frontend JavaScript code that expects these metrics
- Only modify existing code, do not add new files or dependencies

---

## Task 1: Fix revenue_growth_qoq assignment and enhance SQL clarity

**Files:**
- Modify: `C:\Users\91996\Documents\My Projects\stock-screener/app/api/v1/legacy_routes.py:1585` (SQL query in scan_stocks)
- Modify: `C:\Users\91996\Documents\My Projects\stock-screener/app/api/v1/legacy_routes.py:2460` (incorrect revenue_growth_qoq assignment)

**Interfaces:**
- Consumes: stock object from scan_stocks() function
- Produces: stock object with corrected revenue_growth_qoq field

- [ ] **Step 1: Enhance SQL query to explicitly select needed fundamentals fields**

```python
            c.execute('''
                SELECT 
                    revenue_yoy_pct,
                    revenue_qoq_pct,
                    net_profit_yoy_pct,
                    net_profit_qoq_pct,
                    eps_yoy_pct,
                    eps_qoq_pct,
                    ebitda,
                    consecutive_quarters_growth,
                    surprise_type
                FROM fundamentals
                WHERE symbol = ? AND exchange = ?
                ORDER BY result_date DESC, id DESC
                LIMIT 1
            ''', (s['ticker'], s['exchange']))
```

- [ ] **Step 2: Fix the incorrect revenue_growth_qoq assignment**

```python
            # FIXED: Use actual revenue QoQ data instead of profit_growth
            stock["revenue_growth_qoq"] = fund[1] if fund[1] is not None else 0.0
```

- [ ] **Step 3: Verify syntax is valid**

Run: `python -m py_compile app/api/v1/legacy_routes.py`
Expected: No syntax errors

- [ ] **Step 4: Commit**

```bash
git add app/api/v1/legacy_routes.py
git commit -m "feat: fix revenue_growth_qoq assignment and enhance SQL query for fundamentals data"
```

---

## Task 2: Source additional real growth metrics from fundamentals

**Files:**
- Modify: `C:\Users\91996\Documents\My Projects\stock-screener/app/api/v1/legacy_routes.py:1585` (SQL query - add more fields if needed)
- Modify: `C:\Users\91996\Documents\My Projects\stock-screener/app/api/v1/legacy_routes.py:2459-2462` (growth metrics assignments in compute_extra_fields)

**Interfaces:**
- Consumes: stock object with additional fundamentals data
- Produces: stock object with additional real growth metrics

- [ ] **Step 1: Source profit_growth_qoq from fundamentals**

```python
            # Source profit quarter-over-quarter growth from fundamentals
            stock["profit_growth_qoq"] = fund[3] if fund[3] is not None else 0.0
```

- [ ] **Step 2: Source eps_growth_qoq from fundamentals**

```python
            # Source EPS quarter-over-quarter growth from fundamentals
            stock["eps_growth_qoq"] = fund[5] if fund[5] is not None else 0.0
```

- [ ] **Step 3: Assign revenue_growth_yoy correctly (already mostly correct)**

```python
            # This is already correct - revenue_growth_yoy comes from revenue_yoy_pct via the revenue_growth variable
            stock["revenue_growth_yoy"] = revenue_growth  # Already set correctly in fundamentals section
```

- [ ] **Step 4: Verify syntax is valid**

Run: `python -m py_compile app/api/v1/legacy_routes.py`
Expected: No syntax errors

- [ ] **Step 5: Commit**

```bash
git add app/api/v1/legacy_routes.py
git commit -m "feat: source additional real growth metrics from fundamentals table"
```

---

## Task 3: Handle metrics that cannot be sourced from available data

**Files:**
- Modify: `C:\Users\91996\Documents\My Projects\stock-screener/app/api/v1/legacy_routes.py:2453-2455, 2461-2462, 2470-2471` (metrics that should remain None)

**Interfaces:**
- Consumes: stock object
- Produces: stock object with appropriate None values for unsourceable metrics

- [ ] **Step 1: Leave revenue_growth_3y as None (insufficient historical data)**

```python
            # Cannot calculate 3-year CAGR without historical data - leave as None
            stock["revenue_growth_3y"] = None
```

- [ ] **Step 2: Leave ebitda_cagr as None (insufficient historical data for CAGR)**

```python
            # Cannot calculate CAGR without sufficient historical data points - leave as None
            stock["ebitda_cagr"] = None
```

- [ ] **Step 3: Leave eps_cagr as None (insufficient historical data for CAGR)**

```python
            # Cannot calculate CAGR without sufficient historical data points - leave as None
            stock["eps_cagr"] = None
```

- [ ] **Step 4: Leave order_growth as None (no direct equivalent in fundamentals)**

```python
            # No direct equivalent in fundamentals table - leave as None (could be simulated if needed)
            stock["order_growth"] = None
```

- [ ] **Step 5: Leave segment_growth as None (no direct equivalent in fundamentals)**

```python
            # No direct equivalent in fundamentals table - leave as None (could be simulated if needed)
            stock["segment_growth"] = None
```

- [ ] **Step 6: Verify syntax is valid**

Run: `python -m py_compile app/api/v1/legacy_routes.py`
Expected: No syntax errors

- [ ] **Step 7: Commit**

```bash
git add app/api/v1/legacy_routes.py
git commit -m "feat: handle unsourceable growth metrics with appropriate None values"
```

---

## Task 4: Verify no existing functionality is broken

**Files:**
- Test: Application startup and basic scanning functionality

**Interfaces:**
- Consumes: None
- Produces: Confirmed backward compatibility

- [ ] **Step 1: Run application and verify no errors on startup**

Run: `python -m flask --app app --debug run --host=0.0.0.0 --port=5000` (or equivalent)
Expected: Application starts without errors related to our changes

- [ ] **Step 2: Verify a scan completes successfully**

Trigger a scan through the UI or API and verify it completes without errors
Expected: Scan completes and returns stock data

- [ ] **Step 3: Verify enhanced stock objects contain correct growth metrics**

Check that stocksData objects contain our fixed growth metrics:
- revenue_growth_qoq (should now reflect actual revenue QoQ, not profit growth)
- revenue_growth_yoy (should remain correct)
- profit_growth_qoq (newly added)
- eps_growth_qoq (newly added)
- Other metrics appropriately set

Expected: New metrics present with appropriate values (not incorrectly assigned)

- [ ] **Step 4: Test edge cases and error handling**

Verify graceful handling of missing data:
- Stocks with no fundamentals data should have default values (0.0 for growth metrics)
- Stocks with missing component data should have None for derived metrics where appropriate
- No crashes or exceptions should occur

- [ ] **Step 5: Commit final verification**

```bash
git add app/api/v1/legacy_routes.py
git commit -m "feat: verify growth momentum signals fix works correctly"
```

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-21-growth-momentum-signals-fix.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**