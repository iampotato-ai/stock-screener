---
name: project-summary
description: Comprehensive summary of the MomentumScan - NSE India Stock Screener project
metadata:
  type: project
---

# MomentumScan - NSE India Stock Screener - Project Summary

## Overview
MomentumScan is a premium, high-performance Swing & Intraday Momentum stock screener for the National Stock Exchange of India (NSE). It combines real-time data analytics, AI-powered forecasting, and advanced technical analysis to deliver institutional-grade trading insights through a responsive web interface.

## Core Technology Stack
- **Backend**: Python 3.8+ with Flask framework
- **Frontend**: Single-page JavaScript application with TradingView Lightweight Charts
- **Database**: SQLite (`scan_history.db`) for persistent storage
- **Data Sources**: TradingView API, NSE APIs, Yahoo Finance, Google News

## Key Functional Domains

### 1. Market Intelligence Engine
- **Regime Score (0-100)**: Composite market sentiment from breadth indicators
- **Sector Rotation Timeline (RRG)**: Visual 12-week sector momentum tracking
- **Intraday Momentum Score (IMS)**: Real-time gap, RVOL, VWAP analysis (0-10)
- **Swing Score (0-10)**: Trend-based swing trading setup scoring
- **Multi-Timeframe Confirmation**: Weekly/monthly alignment verification

### 2. AI-Powered Prediction System
- **EnsembleCast Multi-Model Forecasting**:
  - Kronos-small (deep learning time-series model)
  - Meta Prophet (trend/seasonality decomposition)
  - ARIMA (statistical baseline)
  - Dynamic MAPE-weighted blending with EMA smoothing
  - Agreement matrix and conviction levels (HIGH/LOW)
- **Kronos AI Integration**: Local model loading with GPU/CPU support
- **Dynamic Weight Adjustment**: Rolling backtest-based model weighting

### 3. Advanced Technical Analysis
- **Pattern Recognition**:
  - Candlestick patterns (Hammer, Engulfing, Morning/Evening Star, etc.)
  - Chart patterns (VCP, Cup & Handle, High Tight Flag, Long Base)
  - Persistent storage in `pattern_cache` and `pattern_signals` tables
- **Setup Classification**:
  - Breakout Ready, Pullback to MA, Inside Bar Coil, Sector Leader, Momentum Continuation
  - Confidence scoring and tag-based filtering
- **Volume Analysis**:
  - Institutional Accumulation (Blue Bar)
  - Above Average Volume (Green Bar)
  - Supply Exhaustion/Dryup (Orange Bar)
- **Volatility Contraction Patterns**:
  - Stage 2 Camp Setup Detection ('The Camp')
  - Volatility dryup and supply exhaustion signals

### 4. Episodic Pivot (EP) System - Phase 2 & 3
- **EP Scoring Framework**:
  - Neglect Score (3m/6m performance, 60-day range, volume rank)
  - Catalyst Score (earnings beats, order wins, theme catalysts)
  - Repricing Score (gap, volume, close location, day strength)
  - Composite EP Score (0-1.0 scale)
- **EP Classification**:
  - Growth EP, Turnaround EP, Story EP, Volume EP, Delayed EP, Short EP
  - Confidence Levels: HIGH/MEDIUM/LOW
- **EP Watchlist Tracking**:
  - Active/Triggered/Expired status management
  - Automated alert generation for high-conviction setups
  - Sugar Babies tracking (high-score recurring EPs)

### 5. IPO & Specialized Modules
- **IPO Momentum Hub**:
  - Real-time tracking of recent NSE/BSE listings
  - Dynamic phase classification: HOT (≤10 days, >15% gain), STABLE, FADING, BROKEN
  - Sector filters, exchange toggle, volume alert overlays
- **Fundamental Data Integration**:
  - Quarterly results from NSE and Yahoo Finance
  - YoY/QoQ growth calculations
  - Earnings surprise categorization
  - Consecutive quarters growth tracking
- **Corporate Events Monitoring**:
  - NSE announcements, block/bulk deals
  - Dividend/split/bonus/AGM tracking
  - Sentiment analysis and catalyst scoring

### 6. Backtesting & Analytics Engine - Phase 4 (Recent Implementation)
- **Historical Data Preparation**:
  - Background backfill of 10-year OHLCV data
  - Technical indicator recomputation (ATR, moving averages, volume averages)
  - EP feature regeneration for historical analysis
- **Strategy Backtesting**:
  - Configurable EP type filters (all, Growth, Turnaround, Story, Volume)
  - Customizable date ranges and position sizing
  - Multiple entry/exit/stop loss rule combinations
  - Portfolio simulation with equity curve tracking
  - Performance metrics (win rate, profit factor, expectancy, max drawdown)
- **Analytics Dashboards**:
  - EP Theme Clustering: Sector-based grouping of Story/Volume EPs
  - Sector Rotation Overlay: RRG positioning with EP watchlist concentration
  - Interactive equity charts with modern styling and tooltips

## Database Schema Highlights

### Core Tables:
- `watchlist_sections/items`: User-defined watchlists with section organization
- `trade_journal`: Trade logging with P&L, win rate, average R-tracking
- `kronos_forecasts`: AI model predictions with ensemble blending
- `pattern_cache/pattern_signals`: Technical pattern detection results
- `rrg_history`: Sector rotation graph data (weekly snapshots)
- `ep_features/ep_watchlist`: Episodic Pivot scoring and tracking
- `fundamentals`: Quarterly financials (revenue, profit, EPS, margins)
- `daily_bars`: Historical OHLCV with technical indicators (ATR, SMAs)
- `ipo_listings/ipo_metrics_cache`: IPO tracking and metrics
- `corporate_events`: News, announcements, block/bulk deals
- `sugar_babies`: High-conviction recurring EP stocks

## API Endpoints Reference

### Market Data:
- `GET /api/scan` - Main stock screener (TradingView → filtering → enrichment)
- `GET /api/nse-holidays` - NSE trading holiday calendar

### Technical Analysis:
- `GET /api/pattern-signals` - Detected candlestick/chart patterns
- `GET /api/setup-analysis` - Detailed technical setup for individual ticker
- `GET /api/rrg-history` - Sector rotation graph timeline data
- `POST /api/rrg/snapshot` - Manual RRG snapshot trigger

### AI Forecasting:
- `GET /api/kronos-forecast` - Individual Kronos model predictions
- `POST /api/ensemble_forecast` - Multi-model ensemble forecasts
- `GET /api/kronos-backtest` - Kronos model historical backtesting
- `GET /api/ensemble-backtest` - Multi-model ensemble backtesting

### EP System:
- `GET /api/ep/refresh/status` - EP refresh process status
- `GET /api/ep/themes` - Today's EP theme clustering by sector
- `GET /api/ep/sector-rotation` - Sector rotation with EP watchlist data
- `POST /api/ep/backtest/prepare` - Start historical data backfill
- `GET /api/ep/backtest/prep_status` - Backfill preparation progress
- `POST /api/ep/backtest` - Run EP strategy backtest

### Watchlist & Journal:
- `GET/POST/DELETE /api/watchlist/sections` - Watchlist section management
- `GET/POST/DELETE /api/watchlist/items` - Watchlist item management
- `GET/POST/DELETE /api/trade-journal` - Trade journal CRUD operations

## Usage & Deployment

### Prerequisites:
- Python 3.8+
- pip package manager
- Recommended: Telegram bot credentials for alerts (optional)

### Installation:
```bash
pip install flask requests pandas numpy torch transformers huggingface_hub einops sentencepiece prophet statsmodels yfinance openpyxl
# For CPU-optimized PyTorch on Windows:
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### Execution:
```bash
python app.py  # or: py app.py on Windows
```

### Access:
- Web Interface: http://127.0.0.1:5000
- API Documentation: Available through endpoint inspection

## Recent Development Focus (feature/workspace-ui branch)

The current development branch implements **Phase 4 - Backtesting Engine and Analytics Dashboard**, adding:

1. **Professional Backtesting Capabilities**:
   - Historical data preparation (10-year OHLCV backfill)
   - Configurable EP strategy backtesting with multiple rule combinations
   - Portfolio simulation with performance analytics
   - Interactive equity curve visualization

2. **Enhanced EP Analytics**:
   - Sector-based EP theme clustering (Story/Volume EPs)
   - Sector rotation overlay with EP watchlist concentration
   - Interactive dashboards with modern UI components

3. **User Experience Improvements**:
   - New EP sub-tabs: "Themes & Rotation" and "Backtest Engine"
   - Real-time preparation progress feedback
   - Responsive design with CSS Grid and Flexbox
   - Modern visual styling consistent with existing interface

This implementation transforms MomentumScan from a screening and alerting platform into a complete trading system development environment, allowing users to:
- Discover EP opportunities through technical screening
- Analyze historical performance of EP strategies
- Optimize strategy parameters through backtesting
- Visualizeportfolio growth and risk metrics
- Identify thematic opportunities and sector rotation patterns

The system maintains backward compatibility while extending functionality for sophisticated quantitative analysis and strategy development.