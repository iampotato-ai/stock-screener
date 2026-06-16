---
name: recent-changes
description: Summary of recent changes to the MomentumScan project
metadata:
  type: project
---

# Recent Changes to MomentumScan - NSE India Stock Screener

## Current Branch: feature/workspace-ui
The current work is focused on implementing **Phase 4 - Backtesting Engine and Analytics Dashboard** features.

## Files Modified
1. **app.py** - Backend Python/Flask application
2. **static/js/app.js** - Frontend JavaScript logic
3. **templates/index.html** - Main HTML template

## Key Features Added

### Backend (app.py) - EP Backtesting System
1. **Database Enhancement**:
   - Added index: `CREATE INDEX IF NOT EXISTS idx_ep_features_symbol_date ON ep_features (symbol, feature_date DESC)`

2. **EP Refresh Status Endpoint**:
   - Changed from `get_ep_refresh_status()` to `api_refresh_ep_status()` 
   - Returns JSON with `running` boolean indicating if EP refresh is locked

3. **Historical Backfill Preparation** (Phase 4):
   - New global status tracker: `ep_backtest_prep_status`
   - Background thread function: `run_historical_backfill()`
   - Processes symbols from daily_bars, ipo_listings, and ep_watchlist tables
   - Fetches 10-year historical data for each symbol
   - Recomputes and populates `daily_bars` and `ep_features` tables
   - Implements rate limiting with `time.sleep(0.5)` between symbols

4. **Backtesting API Endpoints**:
   - `/api/ep/backtest/prepare` (POST) - Starts historical data backfill preparation
   - `/api/ep/backtest/prep_status` (GET) - Returns preparation progress status
   - `/api/ep/backtest` (POST) - Runs EP strategy backtest with configurable parameters
   - `/api/ep/themes` (GET) - Returns today's EP themes clustered by sector
   - `/api/ep/sector-rotation` (GET) - Returns sector rotation data for active EP watchlist

### Backtest Parameters Supported:
- EP Type: all, Growth EP, Turnaround EP, Story EP, Volume EP
- Date Range: Customizable start/end dates
- Minimum EP Score: Default 0.55
- Entry Rules: DAY1_OPEN, DAY1_CLOSE
- Stop Loss Rules: DAY1_LOW, STRUCTURE_LOW, ATR_2X
- Exit Rules: SWING_LOW_TRAIL, 20D_MA, FIXED_PCT
- Position Size: Percentage of capital (default 5%)
- Initial Capital: Default ₹1,000,000

### Backend EP Analytics:
- `/api/ep/themes` - Identifies today's top EP themes by clustering Story/Volume EPs by sector
- `/api/ep/sector-rotation` - Shows RRG quadrant positioning for sectors with active EPs

### Frontend (static/js/app.js) - EP Dashboard Enhancements
1. **EP Sub-tab Navigation**:
   - Added "Themes & Rotation" tab
   - Added "Backtest Engine" tab

2. **Themes & Rotation Panel**:
   - Left side: Theme clustering visualization (Story/Volume EPs grouped by sector)
   - Right side: Sector rotation table showing:
     - Sector name
     - RRG Quadrant (Leading/Improving/Weakening/Lagging)
     - JDK RS value
     - Momentum value
     - RRG Score
     - Active EP Watchlist count

3. **Backtest Engine Panel**:
   - Configuration form for backtest parameters
   - Historical data preparation status bar with progress tracking
   - Results dashboard showing:
     - Performance metrics (Total trades, Win rate, Profit factor, Expectancy, Avg win/loss, Max drawdown)
     - Interactive equity curve chart (using Chart.js)
     - Recent trades table (limited to 200 entries)

4. **EP Panel Logic**:
   - Added visibility toggles for new sub-panels
   - Added tab loading functions: `loadEPThemesAndRotation()` and `initEPBacktestDashboard()`
   - Implemented backtest preparation polling with status updates
   - Added equity chart rendering with smooth gradients and tooltips

### Frontend (templates/index.html) - UI Updates
1. **EP Inner Navigation**:
   - Added buttons for "Themes & Rotation" and "Backtest Engine" sub-tabs

2. **Themes & Rotation Panel**:
   - Two-column layout:
     - Left: Theme clustering cards showing sector, stock count, average EP score, and ticker buttons
     - Right: Sector rotation table with color-coded quadrants (green=Leading, blue=Improving, orange=Weakening, red=Lagging)

3. **Backtest Engine Panel**:
   - Configuration section with inputs for all backtest parameters
   - Preparation status bar (hidden by default, shows during backfill)
   - Results dashboard with:
     - Stats grid (8 key performance indicators)
     - Equity curve chart canvas
   - Responsive design using CSS Grid

## Technical Implementation Details

### Database Tables Utilized/Enhanced:
- `daily_bars` - Stores OHLCV data with technical indicators
- `ep_features` - Episodic Pivot features and scores
- `ep_watchlist` - Active EP watchlist for tracking
- `ipo_listings` - IPO data for symbol universe
- `rrg_history` - Sector rotation graph data
- `fundamentals` - Quarterly financial data for catalyst scoring

### Key Algorithms Implemented:
1. **Historical Backfill**:
   - Processes all unique symbols from key tables
   - Fetches 10 years of daily data via Yahoo Finance
   - Calculates ATR, moving averages, volume indicators
   - Identifies EP breakout candidates (rel_vol_20 >= 3.0 AND gap >= 2.0 AND close_loc >= 0.5)
   - Computes full EP score and stores in ep_features table

2. **Backtesting Engine**:
   - Walks forward from EP detection date
   - Simulates entry on next trading bar open/close
   - Applies stop loss and profit target rules
   - Tracks trailing stops for swing low exit strategy
   - Calculates P&L and R-multiples
   - Portfolio simulation with position sizing and max concurrent positions
   - Generates equity curve and performance metrics

3. **Theme Detection**:
   - Groups today's Story/Volume EPs by sector (from ipo_listings)
   - Calculates average EP score per sector
   - Returns top themes sorted by stock count

4. **Sector Rotation Overlay**:
   - Gets latest RRG data for all sectors
   - Cross-references with active EP watchlist
   - Shows sectors with EP concentration in different RRG quadrants

## User Experience Improvements
- Enhanced EP analysis with thematic clustering
- Sector rotation context for EP opportunities  
- Professional-grade backtesting engine with visual equity curves
- Configurable strategy parameters for rigorous testing
- Real-time preparation progress feedback
- Interactive charts with modern styling and tooltips
- Responsive layouts for different screen sizes

## Dependencies Added
- Chart.js library (via CDN in template) for equity curve visualization
- No additional Python dependencies (uses existing pandas, numpy, sqlite3)

## Current Status
The implementation appears to be complete and ready for testing. Changes include:
- Backend API endpoints for data preparation and backtesting
- Frontend UI components for configuration and results visualization
- State management for long-running background processes
- Error handling and user feedback mechanisms
- Responsive design patterns consistent with existing UI

This Phase 4 implementation significantly enhances the MomentumScan platform by adding professional backtesting capabilities and analytical depth to the Episodic Pivot screening system.