# MomentumScan - NSE India Stock Screener

A premium, high-performance Swing & Intraday Momentum stock screener for the National Stock Exchange of India (NSE). Powered by a lightweight Flask backend and an interactive single-page JS frontend, MomentumScan aggregates live data from TradingView, NSE announcements, bulk/block deals, corporate events, and Google News to deliver a institutional-grade trading dashboard.

---

## ⚡ Key Dashboard Highlights

1. **Composite Market Regime Speedometer**: A live circular dial displaying market sentiment (0–100) computed from multi-dimensional breadth signals.
2. **Interactive Watchlist Center**: Drag-and-drop stock organizing, renameable sections, ex-dates/announcements feed, and bulk deal tracking.
3. **Advanced Risk-Calculator Drawer**: Automatically calculates target exits, shares, stop-loss lines, and position sizing guidelines tailored to current market conditions.
4. **Trade Log Journal**: Direct log-to-journal database saving with live performance stats tracking (PnL, Win Rate, Average R).

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

---

### 2. Multi-Tab Screener Table
Filter, sort, and search the NSE universe through dedicated analytical dimensions:
* **Overview Tab**: Spot core price trends, multi-timeframe confirmations (Weekly + Daily trends), setup labels (e.g. *Breakout Ready*, *Pullback to MA*, *Inside Bar Coil*, *Vol Coil*, *Bullish Div*), ATR metrics, and moving average flirting status.
* **Valuation Tab**: View fundamental value metrics like P/E, P/B, Debt/Equity, EV/EBITDA, and Quick Ratio.
* **Quality Tab**: Evaluate capital efficiency via ROE, ROA, Gross/Operating/Net Margins, and basic financial health.
* **Growth Tab**: Track short-term and long-term momentum through Quarterly and Yearly Revenue and Earnings Growth rates.
* **RRG (Relative Rotation Graph Proxy)**: A scatter plot mapping short-term (1W) vs. medium-term (1M) relative performance against the market median. Includes a dynamic **Sector Heatmap** grid.
* **Intraday Pro Tab**: Track real-time day trading configurations including:
  * *Gap and Go* (strong gaps with volume follow-through).
  * *VWAP Reclaim* (prices crossing and holding above VWAP).
  * *High RVOL Movers* (highest relative volume spikes).
  * *Confluence setups* (overlap of strong daily swing and intraday setups).
* **Journal Tab**: Logs and reviews executed trades, complete with metrics showing total trades, win rates, average risk-to-reward (R) achieved, and total PnL.

---

### 3. News, Corporate Actions & institutional Catalysts
The right-hand side panel serves as a real-time catalyst scanner for watchlist stocks:
* **Corporate Announcements**: Aggregates official filings from NSE. A background keyword classifier tags announcements as *Financials*, *Dividends*, *Catalysts*, or *General Board Meetings*. Clicking an announcement opens a mock **SEBI LODR Filing Document** viewer.
* **Catalysts & News**: Pulls Google News RSS feeds for the selected ticker.
* **Corporate Events**: Monitors ex-dates for dividends, splits, bonuses, and AGMs.
* **Block & Bulk Deals**: Identifies institutional blocks and large market transactions, listing buyer/seller names and transaction values.

---

### 4. Interactive UI Utilities
* **Drag-and-Drop Columns**: Reorder headers on the fly by dragging. Columns can also be dynamically resized.
* **Custom Filter Presets**: Save your range filters (RVOL limits, P/E limits, change limits, and score values) into custom presets that can be applied or deleted in a click.
* **Auto-Refresh Engine**: During market hours, the dashboard auto-scans every 2 minutes with an inline countdown timer.
* **Clickable Stat Cards**: Clicking on cards like *Elite Swing*, *Sector Leaders*, or *Breakout Ready* applies instant filters to the grid.
* **Excel Exporter**: Downloads the entire filtered dataset across all tabs into a clean, multi-sheet `.xlsx` file.

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
pip install flask requests pandas openpyxl
```

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
