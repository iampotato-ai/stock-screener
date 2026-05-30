# MomentumScan - NSE India Stock Screener

A premium, high-performance Swing & Intraday Momentum stock screener for the National Stock Exchange of India (NSE). Powered by a lightweight Flask backend and an interactive single-page JS frontend, MomentumScan aggregates live data from TradingView, NSE announcements, bulk/block deals, corporate events, and Google News, integrating advanced deep learning predictions to deliver an institutional-grade trading dashboard.

---

## ⚡ Key Dashboard Highlights

1. **Composite Market Regime Speedometer**: A live circular dial displaying market sentiment (0–100) computed from multi-dimensional breadth signals.
2. **Interactive Watchlist Center**: Drag-and-drop stock organizing, renameable sections, ex-dates/announcements feed, bulk deal tracking, and **AI-powered batch sorting**.
3. **TradingView Lightweight Charts**: Interactive candlestick charting inside the trade drawer and full-screen overlay modals, featuring overlay SMAs, volume bars, and pattern detection.
4. **Kronos Candlestick AI Predictor**: Direct integration of the `Kronos-small` foundation model for generating multi-day price path predictions, trend bias, and Monte Carlo confidence intervals.
5. **Advanced Risk-Calculator Drawer**: Automatically calculates target exits, shares, stop-loss lines, and position sizing guidelines tailored to current market conditions.
6. **Trade Log Journal**: Direct log-to-journal database saving with live performance stats tracking (PnL, Win Rate, Average R) backed by a robust SQLite persistence layer.

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
* **Overview Tab**: Spot core price trends, multi-timeframe confirmations (Weekly + Daily trends), setup labels (e.g. *Breakout Ready*, *Pullback to MA*, *Inside Bar Coil*, *Vol Coil*, *Bullish Div*), ATR metrics, and moving average flirting status.
* **Valuation Tab**: View fundamental value metrics like P/E, P/B, Debt/Equity, EV/EBITDA, and Quick Ratio.
* **Quality Tab**: Evaluate capital efficiency via ROE, ROA, Gross/Operating/Net Margins, and basic financial health.
* **Growth Tab**: Track short-term and long-term momentum through Quarterly and Yearly Revenue and Earnings Growth rates. Includes an active warning banner clarifying when simulated metrics are active.
* **RRG (Relative Rotation Graph Proxy)**: A scatter plot mapping short-term (1W) vs. medium-term (1M) relative performance against the market median. Includes a dynamic **Sector Heatmap** grid.
* **Intraday Pro Tab**: Track real-time day trading configurations including *Gap and Go*, *VWAP Reclaim*, *High RVOL Movers*, and *Confluence setups*.
* **Journal Tab**: Logs and reviews executed trades, complete with metrics showing total trades, win rates, average risk-to-reward (R) achieved, and total PnL.

### 3. TradingView Lightweight Charts Integration
Replaces simple static sparklines with interactive, high-fidelity daily candlestick charts:
* **Rich Layout**: Plots complete daily OHLCV bars (last 120 bars by default with 2-year history available via scrollback).
* **Moving Average Lines**: Overlays SMA 10 (Yellow), SMA 21 (Cyan), and SMA 50 (Purple) directly on top of the price bars.
* **Volume Overlay**: Displays color-coded volume histograms constrained to the bottom of the chart.
* **Pattern Markers**: Client-side detection displays visual markers for key price patterns:
  * **Inside Bars**: Yellow/amber circles positioned above coiling ranges.
  * **Breakouts**: Green upward arrows indicating price breakout on volume expansion.
* **Full-Screen Overlay Modals**: Clicking the chart inside the drawer opens a modal overlay charting workspace (`90vw` width) with backdrop blurs and ESC-key close handlers.
* **Responsive Styling**: Automatic chart resizing via `ResizeObserver` and dynamic color scheme adjustment synchronized with the global Light/Dark theme.

### 4. Kronos Candlestick AI Predictor & Tab Workspace
Integrates the `Kronos-small` foundation model for deep learning time-series forecasting:
* **Expectations Path**: Projects expected future closes as a dashed purple path (averaged over 10 parallel Monte Carlo runs to filter prediction noise).
* **Forecast Candlesticks**: Displays future prediction windows (3D, 5D, 10D) as translucent purple/pink forecast candles.
* **Confidence Envelopes**: Shades the P10 to P90 statistical confidence boundaries to visualize forecast volatility.
* **Adaptive Volatility Temperature**: Computes the 14-day ATR% of the stock dynamically to scale the model's generation temperature `T`. Uses tighter temperature bounds for consolidations and wider bounds for volatile momentum plays.
* **Dedicated AI Forecast Tab**: A full workspace containing length selectors, large-scale lightweight forecasting charts, prediction grids, and a "Forecast vs Actual" visualizer to analyze tracking performance.
* **On-the-Fly Dynamic Backtester**: Computes tracking accuracy metrics (MAE, MAPE, Directional Accuracy %, and Band Hit Rate %) dynamically by slicing historical price ranges on-the-fly for any newly searched ticker.

### 5. AI-Powered Watchlist Batch Sorting
Sort and prioritize watchlists by predictive strength:
* **Kronos Sort (⚡)**: Clicking the lightning button triggers parallel batch forecasting on the backend (capping threads at 8 to prevent Yahoo Finance throttling).
* **Dynamic Table Expansion**: Expands the watchlist sidebar with `# Rank`, `AI Return`, `Bias`, and `Conf.` columns.
* **Layered Cache Indicator Badges**: Shows `L` for live forecast calculations and `C` for database/memory cache hits. Serving subsequent cache requests in `<0.07` seconds.
* **Stale Cache Eviction**: Automatically resets in-memory cache elements to prevent memory leaks from deleted tickers.
* **Adaptive Spinners**: Renders CSS-based `.small-spinner` loader animations inside the row cells during active batch queries.
* **Last Sorted Label**: Updates a visible timestamp label showing the freshness of current rankings.

### 6. Relational SQLite Backend Persistence
Migrated from limited local storage to a relational SQLite database (`scan_history.db`):
* **Relational Schema**: Manages tables for `watchlist_sections`, `watchlist_items`, `trade_journal`, and `kronos_forecasts` with indexing and `ON DELETE CASCADE` integrity rules.
* **Automatic Browser Migration**: Automatically detects and migrates legacy watchlists and journal entries from browser `localStorage` on first startup, safely clearing local keys upon confirmation.
* **REST API Architecture**: Exposes RESTful endpoints for sections, individual watchlist items, journal entries, and cache hits.

### 7. Catalysts & News Sidebar Scanner
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

---

## 🚀 Setup & Run Instructions

### Prerequisites
Make sure you have **Python 3.8+** installed.

### 1. Install Dependencies
Navigate to the root directory and install the necessary libraries:
```bash
pip install flask requests pandas openpyxl torch transformers huggingface_hub einops sentencepiece
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
