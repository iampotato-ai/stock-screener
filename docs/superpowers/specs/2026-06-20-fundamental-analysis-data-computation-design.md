# Fundamental Analysis Tabs Enhancement - Data Computation Design

## Overview
This document describes the approach for computing the fundamental analysis metrics needed for the Fundamental Analysis Tabs Enhancement. The enhancement adds expandable detail sections (Valuation Deep Dive, Quality Trends Analysis, Growth Momentum Signals) to the stock detail drawer that appear contextually based on which fundamental tab is active.

## Goal
Compute key fundamental metrics for swing trading analysis and make them available in the stocksData object for frontend consumption, without requiring additional API calls.

## Selected Approach
Create a new dedicated function `compute_fundamental_metrics(stock)` that calculates fundamental analysis metrics and call it from the existing `scan_stocks()` function after `compute_extra_fields()`.

## Architecture

### Components
1. **compute_fundamental_metrics(stock)** - New function that calculates valuation, quality, and growth metrics
2. **Integration point** - Called from `scan_stocks()` in `app/api/v1/legacy_routes.py` 
3. **Data flow** - TradingView data → Base stock → compute_extra_fields() → compute_fundamental_metrics() → Enhanced stock → frontend stocksData
4. **Frontend integration** - Existing JavaScript functions access metrics via stock object properties

### Data Sources
- **Primary**: Fields already available from TradingView API (via COLUMNS) 
- **Secondary**: Fields computed by `compute_extra_fields()` 
- **Tertiary**: Metrics calculated from combinations of available data
- **Quaternary**: Data from fundamentals database table (when available)

## Metrics Selection
Selected metrics provide balanced coverage across valuation, quality, and growth dimensions most relevant to swing trading:

### Valuation Metrics
- **PEG Ratio** - P/E ratio divided by earnings growth; identifies undervalued growth stocks
- **EV/Revenue** - Enterprise value to revenue; useful for comparing companies with different margins  
- **Debt/EBITDA** - Financial leverage ratio; lower indicates more flexibility for growth investments

### Quality Metrics
- **Consecutive EPS Growth Quarters** - Shows consistency of earnings execution
- **ROIC Trend** - Direction of return on invested capital over recent quarters
- **FCF Conversion %** - Free cash flow as percentage of EBITDA; >80% indicates high earnings quality

### Growth Metrics
- **QoQ Growth Acceleration** - Change in quarter-over-quarter growth rate; shows momentum
- **YoY Growth Consistency** - Stability of year-over-year growth (lower = more consistent)
- **Order Book/Backlog Growth** - Forward revenue visibility indicator

## Implementation Details

### Function Location
- File: `app/api/v1/legacy_routes.py`
- Location: Added after `compute_extra_fields()` function

### Integration Point
In `scan_stocks()` function, after line 5506:
```python
# Compute extra fundamental and growth metrics
compute_extra_fields(stock)

# NEW: Compute fundamental analysis metrics for swing trading
compute_fundamental_metrics(stock)
```

### Error Handling
- Graceful defaults (0 or None) when source data is missing or invalid
- Protect against division by zero
- Handle null/undefined values from TradingView data

### Performance Considerations
- Minimal computational overhead - simple arithmetic operations
- No additional database queries or API calls
- Runs per-stock during scan processing, consistent with existing `compute_extra_fields()`

## Benefits
- **Follows existing patterns** - Similar to `compute_extra_fields()` already in codebase
- **Separation of concerns** - Fundamental analysis logic isolated from other computations
- **No additional API calls** - Uses data already fetched from TradingView
- **Easy to test and maintain** - Self-contained function with clear inputs/outputs
- **Swing-trader focused** - Metrics selected for relevance to swing trading decisions
- **Seamless frontend integration** - Existing JavaScript code can access new properties directly

## Data Availability & Computation
Based on code analysis, the following data sources are available:

### Directly Available from TradingView (via COLUMNS):
- market_cap_basic, price_earnings_ttm, enterprise_value_ebitda_ttm, price_book_fq
- dividends_yield, price_sales_ratio, enterprise_value_fq, gross_margin_ttm
- ebitda_margin_ttm, debt_to_equity_fq, net_income_ttm, free_cash_flow_ttm/fy
- return_on_equity_fq, return_on_assets_fq, return_on_capital_employed_fq

### Computed by compute_extra_fields():
- sales_cagr, revenue_growth_3y/yoy/qoq, ebitda_cagr, eps_cagr, bv_growth
- order_growth (for certain sectors), segment_growth (simulated or real)
- wc_intensity, cfo_ebitda, growth_data_source

### Available from Fundamentals Database:
- revenue_yoy_pct, net_profit_yoy_pct, consecutive_quarters_growth, surprise_type
- (These are queried but currently not attached to stock object - opportunity for enhancement)

### Computable from Available Data:
- PEG ratio = pe_ratio / eps_growth (need to get/compute eps_growth)
- EV/Revenue = enterprise_value / revenue
- Debt/EBITDA = debt_to_equity * (market_cap / ebitda) or similar derivation
- Various trends and ratios calculable from time-series data

## Spec Self-Review

### Placeholder Scan
- [ ] No placeholders/TODOs found
- [ ] All sections completed with specific details

### Internal Consistency
- [ ] Architecture matches approach description
- [ ] Component responsibilities are clear and non-overlapping
- [ ] Data flow logically follows existing code patterns

### Scope Check
- [ ] Focused on single responsibility: computing fundamental metrics for enhancement
- [ ] Does not attempt to solve unrelated problems (UI, API changes beyond scope)
- [ ] Appropriate for single implementation plan

### Ambiguity Check
- [ ] Approach clearly defined (new function + integration point)
- [ ] Metrics explicitly listed 
- [ ] Integration location specified (after compute_extra_fields in scan_stocks)
- [ ] Error handling strategy defined

## Next Steps
After user approval of this design document, proceed to implementation planning using the writing-plans skill to create detailed implementation tasks.