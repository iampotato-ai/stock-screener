---
name: project-overview
description: Overview of the MomentumScan - NSE India Stock Screener project
metadata:
  type: project
---

# MomentumScan - NSE India Stock Screener

A premium, high-performance Swing & Intraday Momentum stock screener for the National Stock Exchange of India (NSE). Powered by a lightweight Flask backend and an interactive single-page JS frontend, MomentumScan aggregates live data from TradingView, NSE announcements, bulk/block deals, corporate events, and Google News, integrating advanced deep learning predictions to deliver an institutional-grade trading dashboard.

## Core Architecture

### Backend (Flask)
- **Main File**: `app.py` - Contains all backend logic and API endpoints
- **Database**: `scan_history.db` - SQLite database for persistent storage
- **Key Tables**:
  - `watchlist_sections` & `watchlist_items` - User watchlists
  - `trade_journal` - Trading performance tracking
  - `kronos_forecasts` - AI model predictions
  - `pattern_cache` & `pattern_signals` - Technical pattern detection
  - `rrg_history` - Sector rotation graph data
  - `ep_features` & `ep_watchlist` - Episodic Pivot scoring system
  - `fundamentals` - Quarterly financial data
  - `daily_bars` - Historical OHLCV data
  - `ipo_listings` & `ipo_metrics_cache` - IPO tracking
  - `corporate_events` - News and announcements
  - `sugar_babies` - High-conviction stocks

### Frontend
- Single-page JavaScript application
- TradingView Lightweight Charts for interactive candlestick charting
- Responsive design with keyboard navigation support
- Real-time updates via AJAX polling

## Key Features

1. **Market Breadth & Sentiment Panel** - Composite Regime Score (0-100) calculated from:
   - Advances/Declines Ratio (30%)
   - % Stocks above SMA21 & SMA50 (30%)
   - % Stocks near 52-week highs (20%)
   - TradingView sentiment score (20%)

2. **Multi-Tab Screener Table** - Analytical dimensions:
   - Overview (price trends, setup labels)
   - Valuation (P/E, P/B, Debt/Equity, etc.)
   - Quality (ROE, ROA, margins)
   - Growth (Revenue/Earnings growth)
   - RRG (Relative Rotation Graph)
   - Intraday Pro (Gap and Go, VWAP Reclaim, etc.)
   - IPO Momentum (HOT/STABLE/FADING/BROKEN phases)
   - Journal (trade logging and performance)

3. **EnsembleCast Multi-Model Forecasting Engine**:
   - Kronos-small (deep learning time-series model)
   - Meta Prophet (additive regression for trend/seasonality)
   - ARIMA (statistical auto-regressive baseline)
   - Dynamic MAPE weighting with EMA smoothing
   - Agreement matrix and conviction levels (HIGH/LOW)

4. **AI-Powered Watchlist Batch Sorting**:
   - Kronos Sort (parallel batch forecasting)
   - Dynamic table expansion with AI Return, Bias, Conf. columns
   - Layered cache indicator badges (L=live, C=cached)
   - Stale cache eviction and adaptive spinners

5. **Smart Alert Engine** (background monitoring):
   - Regime Score Delta (≥15 point jump)
   - Swing Score Flip (weak→strong setup transition)
   - Kronos Forecast Spike (>5% predicted 5-day move)
   - Bulk/Block Deal Detection
   - Browser push notifications + persistent alert log panel

6. **Technical Analysis Tools**:
   - Pattern detection (candlestick & chart patterns)
   - Setup classification (Breakout Ready, Pullback to MA, Inside Bar Coil, etc.)
   - Volume analysis (Blue/Green/Orange bars for institutional activity)
   - Stage 2 Camp Setup Detection (volatility contraction + supply exhaustion)
   - Multi-timeframe confirmation (weekly/monthly alignment)

7. **Episodic Pivot (EP) Scoring System**:
   - Neglect score (3m/6m performance, 60-day range, volume rank)
   - Catalyst score (earnings beats, order wins, theme catalysts)
   - Repricing score (gap, volume, close location, day strength)
   - Final EP score (weighted combination)
   - EP types: Growth EP, Turnaround EP, Story EP, Volume EP, Delayed EP, Short EP
   - Confidence levels: HIGH/MEDIUM/LOW

## Data Flow

1. **TradingView Scanner** → Fetch NSE stocks with market cap ≥ ₹10,000 Cr
2. **Filter Stocks** → Apply momentum filters (SMA10>SMA21>SMA50, ATR>3%, etc.)
3. **Enrich Data** → Calculate technical indicators, fundamental ratios, extra fields
4. **Pattern Analysis** → Detect candlestick & chart patterns (parallel processing)
5. **Scoring** → Calculate intraday/swing scores, MTF confirmation, setup labels
6. **Historical Analysis** → Compute scan history metrics (first_seen, times_seen, etc.)
7. **Pattern Intelligence** → Run Screener Intelligence setup pattern scanning
8. **Classification** → Apply setup classification and volume dryup analysis
9. **Volume Alerts** → Evaluate real-time volume alert flags (Blue/Green/Orange bars)
10. **RRG Snapshot** → Update sector rotation graph data weekly
11. **Return Results** → JSON response to frontend for display

## Environment & Dependencies

- Python 3.8+
- Key Python Packages: flask, requests, pandas, numpy, torch, transformers, prophet, statsmodels, yfinance, openpyxl, einops, sentencepiece, huggingface_hub
- Optional SIMULATED_DATA mode for testing layouts without real data
- Environment variables: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ENABLE_SIMULATED_DATA

## Usage

1. Install dependencies: `pip install -r requirements.txt`
2. Launch: `python app.py` (or `py app.py` on Windows)
3. Access UI: http://127.0.0.1:5000

The system is designed for institutional-grade analysis with real-time data processing, sophisticated AI forecasting, and comprehensive technical analysis capabilities.