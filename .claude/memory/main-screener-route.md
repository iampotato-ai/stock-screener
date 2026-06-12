---
name: main-screener-route
description: Details about the main screener API endpoint (/api/scan)
metadata:
  type: reference
---

# Main Screener Route - /api/scan

## Overview
The `/api/scan` endpoint is the core of the MomentumScan application, responsible for fetching, filtering, and enriching stock data from TradingView and other sources.

## TradingView API Payload
```json
{
  "filter": [
    {"left": "exchange", "operation": "equal", "right": "NSE"},
    {"left": "market_cap_basic", "operation": "greater", "right": 10000000000}
  ],
  "options": {"lang": "en"},
  "symbols": {"query": {"types": []}, "tickers": []},
  "columns": COLUMNS,
  "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
  "range": [0, 5000]
}
```

### Key Filters:
- Exchange: NSE only
- Minimum market cap: ₹10,000,000,000 (10,000 Cr / ~$120M USD)
- Returns: All matching columns (see COLUMNS array)
- Sort: By market cap descending
- Range: First 5000 stocks (enough to capture all large-cap NSE stocks)

## Processing Pipeline

### 1. Initial Filtering
After fetching from TradingView, stocks are filtered based on:
- Data integrity (correct number of columns)
- Non-null values in required calculation fields:
  - close, SMA10, SMA21, SMA50, ATR
  - price_52_week_low, average_volume, market_cap_basic

### 2. Momentum Filters (Applied Sequentially)
Stocks must pass ALL of these conditions:
1. **SMA(10) > SMA(21)** - Short-term trend above medium-term
2. **SMA(21) > SMA(50)** - Medium-term trend above long-term
3. **ATR(14) > 3% of close** - Sufficient volatility (>3% average true range)
4. **Price ≥ 1.5 × 52-week low** - Recovered from oversold levels
5. **Turnover > ₹100 Crores** (close × 30-day average volume > 100,000,000 INR)

### 3. Data Enrichment
For passing stocks, calculate/add:
- **Technical Indicators**:
  - `atr_pct` = (ATR / close) × 100
  - `pct_above_low` = ((close - 52w_low) / 52w_low) × 100
  - `turnover_m` = (close × avg_vol) / 10,000,000 (in Crores)
  - `mkt_cap_cr` = market_cap_basic / 10,000,000 (in Crores)
  - `relative_volume` = volume / 10-day average volume
  - Performance metrics: perf_w, perf_m, perf_3m (weekly, monthly, 3-month)

- **Clean Ticker Extraction**:
  - Remove "NSE:" or "BSE:" prefixes
  - Extract simple name from TradingView "name" field

- **Fundamental Ratios**:
  - PE ratio, EV/EBITDA, PB ratio, Dividend yield
  - PS ratio, Enterprise value, Free cash flow yield
  - ROE, ROCE, ROA, Debt-to-equity
  - Net income and FCF in Crores
  - Derived ratios: CFO/PAT approximation, Interest coverage

- **Earnings Date Processing**:
  - Check earnings_release_date and earnings_release_next_date
  - Set upcoming_earnings field if either date is in future

- **Extra Fields Calculation** (`compute_extra_fields`):
  - CFO/EBITDA approximation
  - Working capital intensity (simulated or real)
  - Growth metrics: Sales CAGR, Revenue growth (3Y, YoY, QoQ)
  - EBITDA and EPS CAGR
  - Book value growth
  - Order-book and Segment growth (sector-specific)

### 4. Catalyst Data Preparation
- Fetch NSE block/bulk deals data
- Create deal_symbols set for intraday scoring
- Used later in `compute_intraday_score` for catalyst points

### 5. Technical Scoring (Parallel Processing)
For each stock:
- `compute_intraday_score(stock, deal_symbols)` - Intraday Momentum Score (0-10)
- `compute_swing_score(stock)` - Swing Trading Score (0-10)
- `compute_mtf_confirmation(stock)` - Multi-timeframe confirmation

### 6. Historical Analysis
- Query `scan_history` table for each stock's scan history
- Calculate:
  - `first_seen` - First date stock appeared in scans
  - `times_seen_20d` - Appearances in last 20 days
  - `days_in_scan` - Consecutive days currently in scan
  - `re_entry` - Whether stock re-entered after being absent

### 7. Pattern Intelligence & Setup Classification
- `populate_screener_intelligence(filtered_stocks)` - Parallel pattern detection
  - Candlestick patterns (Hammer, Engulfing, Morning Star, etc.)
  - Chart patterns (VCP, Cup & Handle, High Tight Flag, etc.)
  - Persists results to `pattern_cache` and `pattern_signals` tables
- `classify_setup(stock)` - Determine setup label:
  - Breakout Ready, Pullback to MA, Inside Bar Coil, etc.
  - Sets setupLabel, setupTags, setupConfidence fields
- `compute_vol_dryup(stock)` - Volume dryup detection

### 8. Real-Time Volume Alerts
Evaluate intraday volume conditions:
- `is_blue_bar` = Up day AND volume > max down-day volume (last 10 down days)
- `is_green_bar` = Up day AND volume > 50-day volume SMA AND NOT blue bar
- `is_orange_bar` = Volume ≤ 20% of 50-day volume SMA

### 9. Weekly RRG Snapshot
If universe_stocks available:
- Calculate sector scores using `calculate_backend_sector_scores`
- Update RRG history via `snapshot_rrg_week`

## Response Format
Returns JSON with:
```json
{
  "total_scanned": <number of stocks from TradingView>,
  "total_matched": <number of stocks passing all filters>,
  "stocks": [<array of enriched stock objects>],
  "deal_symbols": [<array of symbols with block/bulk deals>],
  "universe": [<array of lightweight universe objects for sector scoring>]
}
```

Each stock object contains:
- All original TradingView columns
- All calculated/enriched fields described above
- Technical scores (intraday_score, swingscore, mtfScore)
- Pattern information (pattern_name, pattern_grade, pattern_desc)
- Setup information (setupLabel, setupTags, setupConfidence)
- Volume alert flags (is_blue_bar, is_green_bar, is_orange_bar)
- Historical metrics (first_seen, times_seen_20d, days_in_scan, re_entry)
- AI forecast data (if available from cache)

## Error Handling & Fallbacks
- If TradingView API fails, attempts to load from `scan_result.txt` cache
- Various try/catch blocks prevent single stock failures from crashing entire scan
- Detailed error logging to console for debugging
- Graceful degradation when optional data sources are unavailable

## Performance Considerations
- Parallel processing for pattern analysis (`populate_screener_intelligence`)
- Caching mechanisms for historical data and AI predictions
- Timeout limits on external API calls (TradingView: 15s, Yahoo Finance: 6s)
- Database connection reuse and proper cleanup
- In-memory caches for frequently accessed data (RRG response, historical prices)