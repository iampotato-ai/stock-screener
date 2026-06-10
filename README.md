# MomentumScan - NSE India Stock Screener

A premium, high-performance Swing & Intraday Momentum stock screener for the National Stock Exchange of India (NSE). Powered by a lightweight Flask backend and an interactive single-page JS frontend, MomentumScan aggregates live data from TradingView, NSE announcements, bulk/block deals, corporate events, and Google News, integrating advanced deep learning predictions to deliver an institutional-grade trading dashboard.

---

## ⚡ Key Dashboard Highlights

1. **Composite Market Regime Speedometer**: A live circular dial displaying market sentiment (0–100) computed from multi-dimensional breadth signals.
2. **Sector Rotation Timeline (RRG)**: An interactive, animated 12-week sector rotation timeline on a custom canvas showing momentum paths (Leading, Weakening, Lagging, Improving).
3. **Interactive Watchlist Center**: Drag-and-drop stock organizing, renameable sections, ex-dates/announcements feed, bulk deal tracking, and **AI-powered batch sorting**.
4. **TradingView Lightweight Charts**: Interactive candlestick charting inside the trade drawer and full-screen overlay modals, featuring overlay SMAs, volume bars, and pattern detection.
5. **EnsembleCast Multi-Model Predictor**: Combines **Kronos-small** foundation model predictions with **Meta Prophet** and **ARIMA** forecasts, powered by a dynamic rolling MAPE weighting engine.
6. **🚀 IPO Momentum Hub**: Dedicated real-time screening of recent mainboard listings on the NSE/BSE, with dynamic phase tracking (**HOT**, **STABLE**, **FADING**, **BROKEN**).
7. **⛺ Stage 2 Camp Setup Detector**: Automatic pattern detection for institutional setups following key breakouts.
8. **📈 Institutional Volume Alerts**: Visual, color-coded volume overlays identifying institutional accumulation (Blue Bar), above-average volume (Green Bar), and supply dryups (Orange Bar).
9. **🔔 Smart Alert Engine**: Continuous client-side background alerting for Regime score shifts, Swing flips, Kronos return spikes, and new block/bulk deals, complete with push notifications and an in-app log panel.
10. **⚡ Keyboard Navigable Cockpit**: Seamless keyboard-driven triage (`↑ / ↓ / Enter / W`) and keyboard-accessible interactive UI components (chips, cards, pills).
11. **Advanced Risk-Calculator Drawer**: Automatically calculates target exits, shares, stop-loss lines, and position sizing guidelines tailored to current market conditions.
12. **Trade Log Journal**: Direct log-to-journal database saving with live performance stats tracking (PnL, Win Rate, Average R) backed by a robust SQLite persistence layer.

---

## 🔍 Core Features & Modules

### 1. Market Breadth & Sentiment Panel
Positioned at the top of the dashboard, this panel gives traders a quick pulse of general market internals:
* **Speedometer Gauge**: Displays the composite **Regime Score (0–100)** accompanied by a directional **Delta Badge** (e.g., `▲ 6`, `▼ 4`, or `• 0`) showing changes from the previous snapshot. It dynamically adjusts position-sizing advice:
  * **Score 75+ (Bull Run 🚀):** Full size exposure.
  * **Score 55-74 (Bullish 📈):** Standard size exposure.
  * **Score 40-54 (Neutral ⚖️):** Half size exposure.
  * **Score 20-39 (Bearish 📉):** Quarter size exposure.
  * **Score < 20 (Bear Market 🚨):** Avoid new long positions.
* **A / D Ratio Bar**: Live Advances vs. Declines chart with raw totals.
* **% Above Moving Averages**: Proportions of the universe trading above their SMA21 and SMA50.
* **52W High Proximity**: Percent of stocks trading within 5% of their annual highs.
* **New 52W H / L**: Real-time counter of stocks hitting absolute 52-week highs vs. absolute 52-week lows.
* **TV Sentiment**: Aggregated TradingView recommendation score.
* **Top Breadth Sectors**: Heatmap list of sectors sorted by the strongest internal A/D ratios.
* **Sector Rotation Heatmap Pills**: A full row of interactive, color-coded sector pills rendered beneath the breadth bar showing the breadth strength percentage of every sector. Clicking any pill instantly filters the screener table.
* **Regime History Modal**: A visual overlay modal loaded by clicking the "History" badge. It fetches and displays the last 30 snapshots with historical timestamps, regime bands (color-coded), composite scores, SMA breadth, and 52W high percentages.

### 2. Multi-Tab Screener Table
Filter, sort, and search the NSE universe through dedicated analytical dimensions:
* **Overview Tab**: Spot core price trends, setup labels (e.g. *Breakout Ready*, *Pullback to MA*, *Inside Bar Coil*, *Vol Coil*, *Bullish Div*, and *Stage 2 Camp*), ATR metrics, and moving average status.
* **Valuation Tab**: View fundamental value metrics like P/E, P/B, Debt/Equity, EV/EBITDA, and Quick Ratio.
* **Quality Tab**: Evaluate capital efficiency via ROE, ROA, Gross/Operating/Net Margins, and basic financial health.
* **Growth Tab**: Track momentum through Quarterly and Yearly Revenue and Earnings Growth rates.
* **RRG (Relative Rotation Graph Proxy) & Animated Timeline**: A dual-view workspace featuring:
  * **Stocks View**: A static scatter plot mapping individual stocks' short-term vs. medium-term relative performance.
  * **Sectors View (Timeline)**: An animated 12-week rotation timeline on a high-DPI custom canvas displaying faded historical trails, playback controls (Play, Pause, Reset, Scrubber, Weeks Select), and click-to-filter sector hit testing.
* **Intraday Pro Tab**: Track real-time day trading configurations including *Gap and Go*, *VWAP Reclaim*, *High RVOL Movers*, and *Confluence setups*.
* **🚀 IPO Momentum Tab**: A dedicated screening tab for recent mainboard IPOs. Track critical listing metrics, relative volume ratio, ATH drawdowns, and classify listing lifecycles into distinct phases (**HOT**, **STABLE**, **FADING**, **BROKEN**). Supports age filtering, sector filters, exchange toggle (NSE/BSE), and volume alert overlays.
* **Journal Tab**: Logs and reviews executed trades, complete with metrics showing total trades, win rates, average risk-to-reward (R) achieved, and total PnL.

### 3. TradingView Lightweight Charts Integration
Replaces simple static sparklines with interactive, high-fidelity daily candlestick charts:
* **Rich Layout**: Plots complete daily OHLCV bars (last 120 bars by default with 2-year history available via scrollback).
* **Moving Average Lines**: Overlays SMA 10 (Yellow), SMA 21 (Cyan), and SMA 50 (Purple) directly on top of the price bars.
* **Volume Overlay**: Displays volume histograms constrained to the bottom of the chart, color-coded by institutional volume flags.
* **Pattern Markers**: Client-side detection displays visual markers for key price patterns:
  * **Inside Bars**: Yellow/amber circles positioned above coiling ranges.
  * **Breakouts**: Green upward arrows indicating price breakout on volume expansion.
* **Full-Screen Overlay Modals**: Clicking the chart inside the drawer opens a modal overlay charting workspace (`90vw` width) with backdrop blurs and ESC-key close handlers.
* **Responsive Styling**: Automatic chart resizing via `ResizeObserver` and dynamic color scheme adjustment synchronized with the global Light/Dark theme.

### 4. EnsembleCast Multi-Model Forecasting Engine
Instead of relying on a single prediction model, MomentumScan implements a sophisticated multi-model ensemble forecasting engine:
* **Three-Model Blend**: Combines **Kronos-small** (deep learning time-series model) with **Meta Prophet** (additive regression for trend/seasonality) and **ARIMA** (statistical auto-regressive baseline).
* **Dynamic MAPE Weighting**: Computes rolling Mean Absolute Percentage Error (MAPE) historically on-the-fly for any requested stock. Model weights are dynamically assigned based on performance (inverse of MAPE) and smoothed via Exponential Moving Average (EMA).
* **Agreement & Conviction**: Calculates a directional **Agreement Matrix** (comparing prediction path directions between models) and an overall **Conviction Level** (HIGH / LOW) accompanied by a **Divergence Score** measuring variance between predictions.
* **Confidence Envelopes**: Displays P10 to P90 statistical confidence intervals alongside expectations paths.
* **Forecast Candlesticks**: Renders future expectation windows (3D, 5D, 10D) as translucent purple forecast candles.
* **On-the-Fly Dynamic Backtester**: Slices historical price ranges on-the-fly to test model accuracy and displays MAE, MAPE, Directional Accuracy %, and Band Hit Rate % indicators.

### 5. AI-Powered Watchlist Batch Sorting
Sort and prioritize watchlists by predictive strength:
* **Kronos Sort (⚡)**: Triggers parallel batch forecasting on the backend (capping threads at 8 to prevent Yahoo Finance throttling).
* **Dynamic Table Expansion**: Expands the watchlist sidebar with `# Rank`, `AI Return`, `Bias`, and `Conf.` columns.
* **Layered Cache Indicator Badges**: Shows `L` for live forecast calculations and `C` for database/memory cache hits. Serving subsequent cache requests in `<0.07` seconds.
* **Stale Cache Eviction**: Automatically resets in-memory cache elements to prevent memory leaks from deleted tickers.
* **Adaptive Spinners**: Renders CSS-based `.small-spinner` loader animations inside the row cells during active batch queries.
* **Last Sorted Label**: Updates a visible timestamp label showing the freshness of current rankings.

### 6. Smart Alert Engine & Persistent Log Panel
A background monitoring layer that evaluates setup conditions on every scan loop and triggers push notifications:
* **Four Alert Categories**:
  1. **Regime Score Delta**: Fired if the market regime score jumps $\ge 15$ points in a single scan.
  2. **Swing Score Flip**: Tracks watchlist stocks that cross from a weak/neutral setup ($< 6$) to a strong/elite setup ($\ge 8$).
  3. **Kronos Forecast Spike**: Warns when the batch model predicts a $> 5\%$ upward move over 5 days.
  4. **Bulk/Block Deal Detection**: Notifies when institutional trades are registered for any stock on watch.
* **Browser Push Notifications**: Supports native browser notifications (with opt-in permission checks).
* **Persistent Alert Log Panel**: In-session sidebar panel logging all triggered alerts with color-coded severity accents (Bullish, Swing, Kronos, Deal, Info). Supports a global clear option and custom configuration toggles.

### 7. Institutional Volume Alerts & Dryup Indicators
Tracks volume behavior to pinpoint accumulation and supply exhaustion:
* **Blue Bar (Institutional Accumulation)**: Highlighted when the current day is an up day, and volume exceeds `max_down_vol_10` (the highest volume registered on down-days in the last 10 down-days). Represents heavy buyer absorption.
* **Green Bar (Above Average Volume)**: Highlighted when the current day is an up day, and volume exceeds the 50-day Volume SMA.
* **Orange Bar (Volume Dryup / Supply Exhaustion)**: Highlighted when volume drops to $\le 20\%$ of the 50-day Volume SMA. Indicates that selling pressure has dried up, often preceding explosive breakout moves.

### 8. Stage 2 Camp Setup Detection
Programmatic identification of Stage 2 Consolidation structures (colloquially called "The Camp"):
* Detects when a stock enters a tight consolidation range after a strong Stage 1 upward run (at least a $15\%$ rally).
* Evaluates volatility contraction (tightening range compared to historical ATR).
* Tracks institutional buying days (count of high-volume accumulation up-days).
* Flags setups where recent volume shows extreme dryups (Orange Bar conditions), indicating supply exhaustion before potential breakouts.

### 9. Workspace UI & Tier 1 UX Refinements
The user interface has been optimized for clean layouts, speed, and day-to-day usability:
* **Dual-Band Screener Header**: Splits controls into a Primary Band (Search, Sector, Presets, Scan CTA) and a Secondary Band (Columns, Density, Auto-Refresh, Export, Snapshot) to maximize vertical space.
* **Compact Trade Ticket**: Fixed at the top of the Trade Drawer, displaying entry, stop-loss, risk amount, risk/share, position sizing, and R:R multiples (to Target 1) for rapid calculation.
* **Collapsible Drawer Modules**: Secondary analytics (Ensemble Forecasts, Pattern Intelligence, History & Notes) are wrapped in collapsible `<details>` components, keeping risk assessment clean and upfront.
* **Sticky Action Footer**: Persistent button bar at the bottom of the trade drawer containing primary CTA actions ("Save to Journal", "Open in TradingView") that remain accessible without scrolling.
* **Dynamic Risk Warning Banners**: Automatically floats warnings (e.g., lack of multi-timeframe alignment, earnings announcement within 5 days) at the top of the drawer.
* **Keyboard Navigation**: Press `ArrowUp` / `ArrowDown` to navigate table rows, `Enter` to open the trade drawer, and `W` to immediately add the selected stock to the watchlist.
* **Keyboard Accessibility (ARIA)**: Native key event handling (`Enter`/`Space`) and ARIA role buttons bound globally to filters, cards, and sector pills.

### 10. Relational SQLite Backend Persistence
Migrated from limited local storage to a relational SQLite database (`scan_history.db`):
* **Relational Schema**: Manages tables for `watchlist_sections`, `watchlist_items`, `trade_journal`, `kronos_forecasts`, `rrg_history`, `pattern_cache`, `pattern_signals`, and `ipo_listings` with indexing and `ON DELETE CASCADE` integrity rules.
* **Automatic Browser Migration**: Automatically detects and migrates legacy watchlists and journal entries from browser `localStorage` on first startup, safely clearing local keys upon confirmation.
* **REST API Architecture**: Exposes RESTful endpoints for watchlist management, journal entries, and cache hits.

### 11. Catalysts & News Sidebar Scanner
The right-hand side panel serves as a real-time catalyst scanner for watchlist stocks:
* **Corporate Announcements**: Aggregates official filings from NSE. A background keyword classifier tags announcements as *Financials*, *Dividends*, *Catalysts*, or *General Board Meetings*. Clicking an announcement opens a mock **SEBI LODR Filing Document** viewer.
* **Catalysts & News**: Pulls Google News RSS feeds for the selected ticker.
* **Corporate Events**: Monitors ex-dates for dividends, splits, bonuses, and AGMs.
* **Block & Bulk Deals**: Identifies institutional blocks and large market transactions, listing buyer/seller names and transaction values.

---

## 🛠️ Backend Architecture & Calculations

### Composite Score Formulas

#### 1. Regime Score (0–100)
Calculated using weighted breadth internals:
$$\text{Score} = (\text{AD Ratio} \times 30) + (\text{MA Breadth \%} \times 30) + (\text{52W High Breadth \%} \times 20) + (\text{Sentiment \%} \times 20)$$

#### 2. Intraday Momentum Score (IMS) (0–10)
Uses real-time data to score intraday momentum:
* Price above VWAP (+2)
* Positive price change (+2)
* RVOL > 1.5 (+2)
* Current volume > 10-day average (+2)
* Price near daily high (+2)

#### 3. Swing Score (0–10)
Scores standard swing setups:
* Price above SMA10 (+2)
* SMA10 > SMA21 (+2)
* SMA21 > SMA50 (+2)
* ATR% > 3% (+2)
* Positive Weekly Performance (+2)

#### 4. Institutional Volume alerts
* **Blue Bar (Accumulation)**: $\text{Current Volume} > \text{max\_down\_vol\_10}$ AND $\text{Current Close} > \text{Previous Close}$
* **Green Bar (Above Average)**: $\text{Current Volume} > \text{volume\_sma\_50}$ AND $\text{Current Close} > \text{Previous Close}$ AND NOT Blue Bar
* **Orange Bar (Volume Dryup)**: $\text{Current Volume} \le 0.20 \times \text{volume\_sma\_50}$

#### 5. EnsembleCast Dynamic Weighting
Weights for the Prophet, ARIMA, and Kronos models are calculated by:
$$w_m = \frac{\frac{1}{\text{MAPE}_m}}{\sum_j \frac{1}{\text{MAPE}_j}}$$
Where $\text{MAPE}_m$ is the Mean Absolute Percentage Error of model $m$ over a rolling 20-day validation window. The raw weights are then smoothed via an Exponential Moving Average (EMA):
$$\text{Smoothed Weight}_t = \alpha \cdot w_t + (1 - \alpha) \cdot \text{Smoothed Weight}_{t-1}$$

#### 6. IPO Momentum Phases
* **HOT**: $\text{Days since Listing} \le 10$ AND $\text{Current Price vs. Issue Price} > 15\%$
* **STABLE**: $\text{Current Price vs. Listing Close} > 5\%$
* **BROKEN**: $\text{Current Price vs. Listing Close} < -10\%$
* **FADING**: Default intermediate cooling phase.

---

## 🚀 Setup & Run Instructions

### Prerequisites
Make sure you have **Python 3.8+** installed.

### 1. Install Dependencies
Navigate to the root directory and install the necessary libraries:
```bash
pip install flask requests pandas openpyxl torch transformers huggingface_hub einops sentencepiece prophet statsmodels
```

> [!NOTE]
> PyTorch is used for running the local Kronos model prediction pipeline. To install a CPU-only light version of PyTorch on Windows (recommended for faster load times and smaller disk footprint), run:
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> ```

### 2. Launch the Application
Run the Flask server:
```bash
python app.py
```
*Alternatively, on Windows, use:*
```bash
py app.py
```

### 3. Open the UI
Open your web browser and navigate to:
```
http://127.0.0.1:5000
```
