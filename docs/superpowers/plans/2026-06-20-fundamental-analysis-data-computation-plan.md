# Fundamental Analysis Tabs Enhancement Data Computation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement backend computation of fundamental analysis metrics for swing trading by: 1) attaching existing fundamentals database data to stock objects, and 2) adding calculations for key valuation, quality, and growth metrics in the compute_extra_fields function.

**Architecture:** Enhance the existing fundamentals data processing in scan_stocks() to attach revenue_growth, profit_growth, consecutive_quarters_growth, and surprise_type to stock objects. Enhance compute_extra_fields() to calculate FCF/EBITDA ratio and add the new fundamental analysis metrics (PEG ratio, EV/Revenue, Debt/EBITDA, FCF conversion %) to stock objects. Call existing validation to ensure no syntax errors.

**Tech Stack:** Python, Flask, TradingView API data, SQLite fundamentals database

## Global Constraints

- Must maintain backward compatibility with existing functionality
- Should not add additional API calls - use data already fetched from TradingView and database
- Must follow existing code patterns and conventions in the codebase
- Should handle missing/null data gracefully with appropriate defaults
- Must integrate seamlessly with existing frontend JavaScript code that expects these metrics

---

### Task 1: Attach fundamentals database data to stock objects

**Files:**
- Modify: `C:\Users\91996\Documents\My Projects\stock-screener/app/api/v1/legacy_routes.py:1722` (after fundamentals data is queried and processed)

**Interfaces:**
- Consumes: revenue_growth, profit_growth, consecutive_quarters_growth, surprise_type variables from fundamentals query
- Produces: stock object with added fundamental data fields for frontend consumption

- [ ] **Step 1: Attach fundamentals data to stock object**

```python
            if fund:
                has_result = 1
                revenue_growth = fund[0] if fund[0] is not None else 0.0
                profit_growth = fund[1] if fund[1] is not None else 0.0
                consec_growth = fund[2] if fund[2] is not None else 0
                surprise_type = fund[3] or "UNKNOWN"
                # ATTACH FUNDAMENTALS DATA TO STOCK OBJECT
                stock["revenue_growth"] = revenue_growth
                stock["profit_growth"] = profit_growth
                stock["consecutive_quarters_growth"] = consec_growth
                stock["surprise_type"] = surprise_type
            else:
                has_result = 0
                revenue_growth = 0.0
                profit_growth = 0.0
                consec_growth = 0
                surprise_type = "UNKNOWN"
                # ATTACH DEFAULTS WHEN NO FUNDAMENTALS DATA
                stock["revenue_growth"] = 0.0
                stock["profit_growth"] = 0.0
                stock["consecutive_quarters_growth"] = 0
                stock["surprise_type"] = "UNKNOWN"
```

- [ ] **Step 2: Verify syntax is valid**

Run: `python -m py_compile app/api/v1/legacy_routes.py`
Expected: No syntax errors

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/legacy_routes.py
git commit -m "feat: attach fundamentals database data to stock objects"
```

---

### Task 2: Add FCF/EBITDA calculation to compute_extra_fields

**Files:**
- Modify: `C:\Users\91996\Documents\My Projects\stock-screener/app/api/v1/legacy_routes.py:2474-2479` (in compute_extra_fields function, after CFO/EBITDA calculation)

**Interfaces:**
- Consumes: stock object with fcf_raw, mkt_cap, ps_ratio, ebitda_margin
- Produces: stock object with added fcf_ebitda metric (FCF/EBITDA ratio)

- [ ] **Step 1: Add FCF/EBITDA calculation alongside existing CFO/EBITDA**

```python
    # 1. CFO/EBITDA
    stock["cfo_ebitda"] = None
    if fcf_raw is not None and mkt_cap > 0 and ps_ratio is not None and ps_ratio > 0 and ebitda_margin is not None and ebitda_margin > 0:
        cfo_est = fcf_raw * 1.12  # Estimate CFO = FCF + estimated CapEx
        revenue = mkt_cap / ps_ratio
        ebitda_est = revenue * (ebitda_margin / 100.0)
        if ebitda_est > 0:
            stock["cfo_ebitda"] = round((cfo_est / ebitda_est) * 100.0, 2)
    
    # 1B. FCF/EBITDA (Free Cash Flow to EBITDA ratio)
    stock["fcf_ebitda"] = None
    if fcf_raw is not None and mkt_cap > 0 and ps_ratio is not None and ps_ratio > 0 and ebitda_margin is not None and ebitda_margin > 0:
        revenue = mkt_cap / ps_ratio
        ebitda_est = revenue * (ebitda_margin / 100.0)
        if ebitda_est > 0:
            stock["fcf_ebitda"] = round((fcf_raw / ebitda_est) * 100.0, 2)
```

- [ ] **Step 2: Verify syntax is valid**

Run: `python -m py_compile app/api/v1/legacy_routes.py`
Expected: No syntax errors

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/legacy_routes.py
git commit -m "feat: add FCF/EBITDA calculation to compute_extra_fields"
```

---

### Task 3: Add fundamental analysis metrics calculations to compute_extra_fields

**Files:**
- Modify: `C:\Users\91996\Documents\My Projects\stock-screener/app/api/v1/legacy_routes.py:2573` (at end of compute_extra_fields function, before Inside Bar calculation)

**Interfaces:**
- Consumes: stock object with pe_ratio, profit_growth, enterprise_value_fq, ps_ratio, market_cap_basic, debt_to_equity, ebitda_margin, fcf_ebitda
- Produces: stock object with added valuation, quality, and growth metrics

- [ ] **Step 1: Add fundamental analysis metrics calculations**

```python
            # Inside Bar calculation
            h_val = float(stock["high"]) if stock.get("high") is not None else None
            l_val = float(stock["low"]) if stock.get("low") is not None else None
            h1_val = float(stock["high[1]"]) if stock.get("high[1]") is not None else None
            l1_val = float(stock["low[1]"]) if stock.get("low[1]") is not None else None
            if h_val is not None and l_val is not None and h1_val is not None and l1_val is not None:
                is_inside_price = bool(h_val < h1_val and l_val > l1_val)
                
                # Check volume compression: current volume < average volume
                vol_val = float(stock.get("volume") or 0)
                avg_vol_val = float(stock.get("average_volume") or stock.get("average_volume_10d_calc") or 0)
                
                # If avg_vol is 0 or missing, we just rely on price (fallback)
                has_vol_compression = (avg_vol_val == 0) or (vol_val < avg_vol_val)
                
                stock["is_inside_bar"] = bool(is_inside_price and has_vol_compression)
            else:
                stock["is_inside_bar"] = False

            # FUNDAMENTAL ANALYSIS METRICS FOR SWING TRADING
            # Valuation Metrics
            # PEG Ratio = P/E ratio divided by earnings growth rate
            pe_ratio = stock.get("pe_ratio")
            profit_growth = stock.get("profit_growth")  # Using profit growth as earnings growth proxy
            if pe_ratio is not None and profit_growth is not None and profit_growth != 0:
                # Convert profit_growth from percentage to decimal for PEG calculation
                # PEG = P/E / (earnings_growth_as_decimal)
                # So: PEG = pe_ratio / (profit_growth/100) = pe_ratio * 100 / profit_growth
                stock["peg_ratio"] = round(pe_ratio * 100.0 / profit_growth, 2)
            else:
                stock["peg_ratio"] = None  # Handle division by zero or missing data
            
            # EV/Revenue = Enterprise Value / Revenue
            # Revenue = market_cap_basic / ps_ratio
            # EV/Revenue = enterprise_value_fq / (market_cap_basic / ps_ratio) = (enterprise_value_fq * ps_ratio) / market_cap_basic
            enterprise_value_fq = stock.get("enterprise_value_fq")
            ps_ratio = stock.get("ps_ratio")
            market_cap_basic = stock.get("market_cap_basic")
            if enterprise_value_fq is not None and ps_ratio is not None and market_cap_basic is not None and market_cap_basic > 0:
                stock["ev_revenue"] = round((enterprise_value_fq * ps_ratio) / market_cap_basic, 2)
            else:
                stock["ev_revenue"] = None
                
            # Debt/EBITDA approximation using available data
            # Debt/EBITDA = (Total Debt) / EBITDA
            # Approximate Total Debt = debt_to_equity * market_cap_basic (assuming market cap ≈ equity)
            # EBITDA = Revenue * (EBITDA Margin/100) = (market_cap_basic / ps_ratio) * (ebitda_margin/100)
            # Debt/EBITDA = (debt_to_equity * market_cap_basic) / [(market_cap_basic / ps_ratio) * (ebitda_margin/100)]
            #           = (debt_to_equity * ps_ratio * 100) / ebitda_margin
            debt_to_equity = stock.get("debt_to_equity")
            ps_ratio = stock.get("ps_ratio")
            ebitda_margin = stock.get("ebitda_margin")
            if debt_to_equity is not None and ps_ratio is not None and ebitda_margin is not None and ebitda_margin != 0:
                stock["debt_ebitda"] = round((debt_to_equity * ps_ratio * 100.0) / ebitda_margin, 2)
            else:
                stock["debt_ebitda"] = None
                
            # Quality Metrics (already have some from fundamentals and compute_extra_fields)
            # Consecutive EPS Growth Quarters - already attached from fundamentals data
            # FCF Conversion % = FCF/EBITDA ratio (we calculated this as fcf_ebitda above)
            # Note: fcf_ebitda is already a percentage (multiplied by 100 in calculation)
            # So we can use it directly or rename for clarity
            fcf_ebitda = stock.get("fcf_ebitda")
            if fcf_ebitda is not None:
                stock["fcf_conversion_pct"] = fcf_ebitda  # Already calculated as percentage
            else:
                stock["fcf_conversion_pct"] = None
                
            # ROE as quality proxy (Return on Equity - higher is generally better quality)
            # Already available as stock["roe"] from fundamental derived fields
            # No additional calculation needed

            # Growth Metrics
            # Revenue Growth YoY - already attached from fundamentals data
            # Order Book Growth - already calculated in compute_extra_fields as order_growth
            # Segment Growth Contribution - already calculated in compute_extra_fields as segment_growth
            # No additional calculations needed for these
```

- [ ] **Step 2: Verify syntax is valid**

Run: `python -m py_compile app/api/v1/legacy_routes.py`
Expected: No syntax errors

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/legacy_routes.py
git commit -m "feat: add fundamental analysis metrics calculations to compute_extra_fields"
```

---

### Task 4: Verify no existing functionality is broken

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

- [ ] **Step 3: Verify enhanced stock objects contain new metrics**

Check that stocksData objects contain our new fundamental analysis metrics:
- revenue_growth
- profit_growth  
- consecutive_quarters_growth
- surprise_type
- peg_ratio
- ev_revenue
- debt_ebitda
- fcf_conversion_pct
- (Plus existing metrics should still be present)

Expected: New metrics present with appropriate values (not all None/undefined)

- [ ] **Step 4: Test edge cases and error handling**

Verify graceful handling of missing data:
- Stocks with no fundamentals data should have default values (0.0, "UNKNOWN", None)
- Stocks with missing component data for calculations should have None for derived metrics
- No crashes or exceptions should occur

- [ ] **Step 5: Commit final verification**

```bash
git add app/api/v1/legacy_routes.py
git commit -m "feat: verify fundamental analysis metrics implementation works correctly"
```
