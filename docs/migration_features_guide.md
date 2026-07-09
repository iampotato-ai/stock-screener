# MomentumScan — Node.js Migration & Feature Specification Guide

This document provides a comprehensive analysis and mapping of all features, services, database models, background tasks, and mathematical algorithms implemented in the Python Flask-based **MomentumScan** stock screener. Use this as a reference manual to replicate the functionality when porting the project to **Node.js**.

---

## 1. System Architecture & Transition Map

### Monolithic Python/Flask vs. Modern Node.js Architecture
The Python application is built as a layered Flask system with a clean separation of concerns. Below is the transition map:

| Layer | Python / Flask Stack | Recommended Node.js / TypeScript Stack |
| :--- | :--- | :--- |
| **Framework** | Flask (Application Factory via `create_app`) | Fastify (Recommended for performance) or Express |
| **Language** | Python 3.8+ | TypeScript (Strict type safety) |
| **Database ORM** | SQLAlchemy (ORM) & raw SQLite helpers | Prisma (Highly recommended) or Sequelize |
| **Background Tasks** | APScheduler (In-process threads) | BullMQ (Redis-backed, reliable) or Node-Cron (Simple, in-memory) |
| **HTTP Client** | `requests` / `urllib.request` | Axios or native `undici`/`fetch` |
| **Math & Data Analysis**| Pandas, NumPy, TA-Lib | Danfo.js (Pandas-like) or raw Array/Lodash math |
| **Time-Series / ML** | Meta Prophet, XGBoost, Transformers (Kronos) | ONNX Runtime Node (for ML models) or TensorFlow.js |
| **Frontend Templates** | Jinja2 Templates (`index.html`) | React (Vite/Next.js) or Vanilla JS SPA (serving static files) |

---

## 2. Database Schema (SQLAlchemy to Prisma)

The database schema manages watchlists, trading logs, time-series forecasts, and market intelligence. Below is the complete translation of [models.py](file:///c:/Users/91996/Documents/My%20Projects/stock-screener/app/models.py) into a **Prisma schema (`schema.prisma`)** targeting SQLite.

```prisma
datasource db {
  provider = "sqlite"
  url      = "file:./scan_history.db"
}

generator client {
  provider = "prisma-client-js"
}

// 1. User & Authentication
model User {
  id           Int      @id @default(autoincrement())
  createdAt    DateTime @default(now())
  updatedAt    DateTime @updatedAt
  username     String   @unique
  email        String   @unique
  passwordHash String
}

// 2. Watchlist & Organization
model WatchlistSection {
  id       String          @id
  name     String
  position Int             @default(0)
  items    WatchlistItem[]
}

model WatchlistItem {
  id        Int              @id @default(autoincrement())
  sectionId String
  section   WatchlistSection @relation(fields: [sectionId], references: [id], onDelete: Cascade)
  ticker    String
  position  Int              @default(0)

  @@unique([sectionId, ticker])
}

// 3. Trade Journal
model TradeJournal {
  id         String  @id
  ticker     String
  name       String
  date       String
  setupLabel String
  swingband  String
  entry      Float
  stop       Float
  target1    Float
  target2    Float
  target3    Float
  riskAmount Float
  qty        Int
  status     String  // "ACTIVE", "CLOSED", etc.
  exitPrice  Float?
  exitDate   String?
  pnl        Float?
  rAchieved  Float?
  notes      String?
}

// 4. Market Breadth History
model BreadthHistory {
  date          String @id // Format YYYY-MM-DD
  time          String?
  advances      Int
  declines      Int
  unchanged     Int
  pctSma21      Float
  pctSma50      Float
  pct52High     Float
  avgRecommend  Float
  regimeScore   Int
  regimeBand    String
}

// 5. Kronos AI Forecasts
model KronosForecast {
  id          Int      @id @default(autoincrement())
  ticker      String
  generatedAt DateTime
  predLen     Int
  forecastJson String  // JSON serialized string
  lastClose   Float
  modelType   String   @default("kronos")

  @@index([ticker])
}

// 6. RRG (Relative Rotation Graph) History
model RrgHistory {
  id             Int      @id @default(autoincrement())
  week           String
  sector         String
  jdkRs          Float
  jdkRsMomentum  Float
  score          Int
  quadrant       String  // "Leading", "Weakening", "Lagging", "Improving"
  snappedAt      DateTime

  @@unique([week, sector])
}

// 7. Technical Pattern Cache & Signals
model PatternCache {
  ticker        String   @id
  generatedAt   DateTime
  patternName   String?
  patternGrade  String?
  patternDesc   String?
  candlestickJson String? // JSON serialized candlestick data
  patternBias   Float    @default(0.0)
  maxDownVol10  Float?
  volumeSma50   Float?
}

model PatternSignal {
  id          Int      @id @default(autoincrement())
  ticker      String
  timeframe   String   @default("D")
  signalType  String   // "candle" | "chart"
  pattern     String
  direction   Int      // 100 bullish, -100 bearish
  confidence  Float?
  description String?
  detectedAt  DateTime
  barDate     String?  // ISO date

  @@index([ticker, detectedAt])
}

// 8. IPO Hub & Cache
model IpoListing {
  ticker       String   @id
  companyName  String
  listingDate  String   // YYYY-MM-DD
  issuePrice   Float?
  listingOpen  Float?
  listingClose Float?
  exchange     String   @default("NSE")
  sector       String?
  issueSizeCr  Float?
  lotSize      Int?
  gmpAtListing Float?
  addedAt      DateTime @default(now())
}

model IpoMetricsCache {
  ticker               String   @id
  companyName          String
  listingDate          String
  exchange             String
  sector               String?
  issuePrice           Float?
  listingOpen          Float?
  listingClose         Float?
  issueSizeCr          Float?
  lotSize              Int?
  gmpAtListing         Float?
  listingGainPct       Float?
  currentVsIssuePct    Float?
  currentVsListingPct  Float?
  daysSinceListing     Int
  rvolRatio            Float?
  aboveListingHigh     Int?
  drawdownFromAth      Float?
  swingScore           Int?
  patternName          String?
  momentumPhase        String?  // "HOT", "STABLE", "FADING", "BROKEN"
  currentPrice         Float?
  volume               Float?
  changePct            Float?
  dayLow               Float?
  dayHigh              Float?
  isBlueBar            Int      @default(0)
  isGreenBar           Int      @default(0)
  isOrangeBar          Int      @default(0)
  cachedAt             DateTime

  @@index([momentumPhase])
}

// 9. Historical Price & Indicator Logs
model DailyBar {
  id              Int      @id @default(autoincrement())
  symbol          String
  exchange        String
  tradeDate       String   // YYYY-MM-DD
  open            Float?
  high            Float?
  low             Float?
  close           Float?
  volume          Int?
  deliveryQty     Int?
  deliveryPct     Float?
  turnover        Float?
  prevClose       Float?
  gapPct          Float?
  closeLoc        Float?   // (close - low) / (high - low)
  atr14           Float?
  relVolume20     Float?
  relVolume50     Float?
  priceChangePct  Float?
  intradayRangePct Float?

  @@unique([symbol, exchange, tradeDate])
  @@index([symbol, tradeDate])
  @@index([tradeDate])
}

// 10. Fundamentals (Earnings Reports)
model Fundamental {
  id                        Int      @id @default(autoincrement())
  symbol                    String
  exchange                  String
  resultDate                String
  quarter                   String   // e.g. "Q1FY26"
  revenue                   Float?
  revenueYoyPct             Float?
  revenueQoqPct             Float?
  netProfit                 Float?
  netProfitYoyPct           Float?
  ebitda                    Float?
  ebitdaMargin              Float?
  eps                       Float?
  epsYoyPct                 Float?
  guidanceText              String?
  surpriseType              String?  // "BLOWOUT", "BEAT", etc.
  consecutiveQuartersGrowth Int?
  source                    String?

  @@unique([symbol, exchange, quarter])
}

// 11. Corporate Actions & Market Events
model CorporateEvent {
  id                 Int      @id @default(autoincrement())
  symbol             String
  exchange           String
  eventDate          String
  eventType          String?
  headline           String?
  sentiment          Int?     // Numeric sentiment scale
  catalystScore      Float?
  source             String?
  rawUrl             String?
  nlpSentimentScore  Float?
  nlpCategory        String?
  summary            String?
  impactMagnitude    Float?

  @@index([symbol, eventDate])
}

model MarketEvent {
  id                  Int      @id @default(autoincrement())
  symbol              String
  externalId          String   @unique
  eventType           String   // EARNINGS, DIVIDEND, SPLIT, BULK_DEAL, INSIDER
  eventDate           String
  title               String
  details             String?
  ratio               String?  // for splits
  amount              Float?   // for dividends
  sentiment           String?  // "Positive", "Negative", "Neutral"
  sentimentConfidence Float?
  importance          String?  // "Low", "Medium", "High", "Critical"
  catalystScore       Float?
  whyItMatters        String?
  aiVersion           String   @default("v1")
  uniqueHash          String   @unique
  source              String   @default("NSE")
  insertedAt          DateTime @default(now())

  @@index([symbol, eventDate])
  @@index([eventType])
}

// 12. Momentum Score Tracking
model MomentumScore {
  id                  Int      @id @default(autoincrement())
  symbol              String
  exchange            String   @default("NSE")
  date                String
  totalScore          Int
  technicalScore      Int      // 0-30
  fundamentalScore    Int      // 0-25
  momentumScore       Int      // 0-20
  institutionalScore  Int      // 0-15
  riskLiquidityScore  Int      // 0-10
  badges              String   // Stringified JSON array of strings
  calculatedAt        DateTime @default(now())

  @@unique([symbol, exchange, date])
  @@index([date])
  @@index([totalScore])
}

// 13. Market Intelligence Ingestion Models
model NewsArticle {
  id                  Int      @id @default(autoincrement())
  symbol              String
  externalId          String   @unique
  title               String
  url                 String   @unique
  summary             String?
  source              String?
  sentiment           String?
  sentimentConfidence Float?
  importance          String?
  whyItMatters        String?
  aiVersion           String   @default("v1")
  publishedAt         DateTime
  insertedAt          DateTime @default(now())

  @@index([symbol, publishedAt])
}

model NewsFetchLog {
  id           Int      @id @default(autoincrement())
  provider     String
  symbol       String
  status       String   // "SUCCESS" | "ERROR"
  latencyMs    Int?
  errorMessage String?
  recordsCount Int      @default(0)
  timestamp    DateTime @default(now())

  @@index([timestamp])
}

model SugarBaby {
  id            Int     @id @default(autoincrement())
  symbol        String  @unique
  exchange      String
  addedDate     String?
  avgBurstPct   Float?
  avgBurstDays  Float?
  episodeCount  Int?
  notes         String?
  isActive      Int     @default(1)
}

model ScanHistory {
  date   String
  ticker String

  @@id([date, ticker])
}

model ScanPriceLog {
  date       String
  ticker     String
  close      Float?
  swingband  String?
  setupLabel String?

  @@id([date, ticker])
}
```

---

## 3. Core Domain Features & Algorithmic Logic

### 3.1 Composite Market Regime Speedometer
Displays current market sentiment (0–100) using multi-indicator inputs.
*   **Formula & Inputs**:
    *   **Advances/Declines Ratio**: A ratio of advancing vs declining stocks.
    *   **SMA 21 / 50 Position**: Percentage of index constituents trading above their 21-day and 50-day Simple Moving Averages.
    *   **52-Week Highs**: Percentage of stocks within 2% of their 52-week highs.
    *   **Regime Score**: Aggregated in `market_breadth_service.py` to create a score between 0 and 100:
        *   `>= 75`: **Extreme Bullish**
        *   `55 - 74`: **Bullish**
        *   `45 - 54`: **Neutral / Sideways**
        *   `25 - 44`: **Bearish**
        *   `< 25`: **Extreme Bearish**

### 3.2 Sector Rotation Timeline (RRG - Relative Rotation Graph)
Plots relative sector strength vs. the Nifty 50 benchmark over a rolling 12-week timeline.
*   **Formulas ([rrg_math.py](file:///c:/Users/91996/Documents/My%20Projects/stock-screener/app/utils/rrg_math.py))**:
    *   **JDK RS (Relative Strength)**:
        $$\text{JDK RS} = \frac{100.0 + \text{Sector Return}}{100.0 + \text{Benchmark Return}} \times 100.0$$
        *(Falls back to 100.0 if benchmark return is -100%)*
    *   **JDK RS Momentum**: Rate of change of JDK RS over the lookback window.
    *   **Quadrant Logic**:
        *   `JDK RS >= 100` and `Momentum >= 0` $\rightarrow$ **Leading** (Top Right)
        *   `JDK RS >= 100` and `Momentum < 0` $\rightarrow$ **Weakening** (Bottom Right)
        *   `JDK RS < 100` and `Momentum < 0` $\rightarrow$ **Lagging** (Bottom Left)
        *   `JDK RS < 100` and `Momentum >= 0` $\rightarrow$ **Improving** (Top Left)

### 3.3 Interactive Watchlist & AI Batch Sort (Kronos)
Provides drag-and-drop watchlist sections, Ex-dates/corporate action integrations, and AI sorting.
*   **AI Batch Sort (Kronos-small)**:
    *   Calls the prediction pipeline to generate future price trajectories for watchlisted stocks.
    *   Calculates a **forecast score** using expected percentage return, consistency, and drawdown.
    *   Sorts the watchlist items in descending order of their forecast scores.
    *   Caches predictions in `kronos_forecasts` to guarantee sub-second frontend rendering, updating them on a background scheduler loop.

### 3.4 Volume-Price Indicators & Camp Setup (Stage 2)
Integrates with TradingView charts to flag specific institutional activity:
1.  **Blue Bar (Institutional Accumulation)**:
    $$\text{Price Up} \quad \text{AND} \quad \text{Volume} > \max(\text{Volume of last 10 down-days})$$
2.  **Green Bar (Above Average Volume)**:
    $$\text{Price Up} \quad \text{AND} \quad \text{Volume} > 50\text{-day Simple Moving Average (SMA) of Volume}$$
3.  **Orange Bar (Supply Dry-up)**:
    $$\text{Volume} \le 20\% \text{ of 50-day SMA of Volume}$$
4.  **Stage 2 Camp Setup**:
    *   Identifies consolidation periods following a strong Stage 2 breakout.
    *   **Rule**: Stock has advanced $>50\%$ in the last 1–2 months, followed by a tight consolidation range ($<8\%$ peak-to-trough range over the last 10–20 days) on drying volume (at least 2–3 orange bars in the consolidation).

### 3.5 Episodic Pivot (EP) Screener
Developed from Pradeep Bonde's strategy targeting neglected stocks undergoing catalysts.
*   **Scoring Formulas ([ep_service.py](file:///c:/Users/91996/Documents/My%20Projects/stock-screener/app/services/ep_service.py))**:
    *   **Neglect Score**: Incorporates 3-month performance, 6-month performance, 60-day trading range, and average volume rank (Lower relative volume and trading ranges yield a higher neglect score).
    *   **Catalyst Score**: Computed from corporate announcements/earnings. Surprises or blowout earnings growth ($>100\%$ YoY profit/sales acceleration) receive a score up to 10.
    *   **Repricing Score**: Based on the Day-1 EP breakout candle:
        $$\text{Repricing Score} = (\text{Gap \%} \times 0.4) + (\text{Relative Volume} \times 0.4) + (\text{Close Location} \times 0.2)$$
        *Close location (0-1) represents where the close is relative to the daily range (1.0 = close at high).*
    *   **Final EP Score**:
        $$\text{EP Score} = (\text{Neglect} \times 0.3) + (\text{Catalyst} \times 0.4) + (\text{Repricing} \times 0.3)$$
*   **EP Watchlist Transitions**:
    *   A stock added to the watchlist sits in **ACTIVE** status for up to 20 days.
    *   If it breaks out of the day-1 trigger range, it moves to **TRIGGERED**.
    *   If 20 days pass without a trigger, the status updates to **EXPIRED**.

### 3.6 Bull Snort Filter
An institutional breakout filter that looks for accumulation bases.
*   **Algorithm Phases ([bull_snort_service.py](file:///c:/Users/91996/Documents/My%20Projects/stock-screener/app/services/bull_snort_service.py))**:
    *   **Phase 1 (Downtrend & Declining 200 DMA)**: The stock must have a historical gap between 200 DMA and price $>10\%$ in the last 6 months (126 days). The 20-day slope of the 200 DMA must be negative.
    *   **Phase 2 (Base Formation)**: Price consolidates. The stock must have recorded no new 10-day low, and the current price must be within $5\%$ of the 200 DMA.
    *   **Phase 3 (Volume Accumulation)**: Computes volume pivots and volume surges during the base (where close < 200 DMA):
        *   *Volume Pivot*: A volume bar that is a local maximum over a $\pm 2$ day window.
        *   *Volume Surge*: Volume $\ge 2\times$ 20-day volume SMA.
        *   $$\text{Accumulation Score} = (50\% \times \text{Pivot Score}) + (50\% \times \text{Surge Score})$$
    *   **Phase 4 (Breakout Candle)**: The breakout day must have:
        1.  Volume Surge $\ge 3\times$ 20-day volume SMA.
        2.  Positive price change (close > prev close).
        3.  Strong close: close location in the top 35% of the daily range.
    *   **Final Score**: Weighted average of volume ratio, price change %, close position, base accumulation, and DMA gaps.

### 3.7 EnsembleCast Multi-Model Predictor
Blends three models into a weighted forecast trajectory ([legacy_routes.py](file:///c:/Users/91996/Documents/My%20Projects/stock-screener/app/api/v1/legacy_routes.py) & [forecast_math.py](file:///c:/Users/91996/Documents/My%20Projects/stock-screener/app/utils/forecast_math.py)):
1.  **Kronos-small** (Deep learning transformer) - Weight: 50%
2.  **Prophet** (Additive time-series seasonality) - Weight: 30%
3.  **ARIMA/SARIMA** (Mean reversion) - Weight: 20%
*   **Dynamic Weighting**: Weights adjust dynamically based on each model's rolling 20-day Mean Absolute Percentage Error (MAPE) on the target symbol:
    $$\text{Score}_m = \frac{1}{\text{MAPE}_m} \qquad \text{Weight}_m = \frac{\text{Score}_m}{\sum \text{Scores}}$$
*   **Divergence Score**: Standard deviation of the forecasts normalized by the ensemble prediction. A divergence $>3\%$ flags a **⚠️ Low Conviction** warning badge.

### 3.8 IPO Momentum Hub
Screens recent IPOs (mainboard listings) to track listing day returns and momentum.
*   **Phase Classification**:
    *   **HOT**: Listing date $<90$ days ago, listing close above issue price, and current price above listing price.
    *   **STABLE**: Days since listing $>90$, current price above issue price, drawdown from lifetime high $<15\%$.
    *   **FADING**: Current price still above issue price, but drawdown from lifetime high $>20\%$ or sliding below listing close.
    *   **BROKEN**: Current price is trading below the initial IPO issue price.

### 3.9 Smart Alert Engine
Monitors server data streams client-side and triggers system/browser alerts for:
*   Regime Score jumps $\ge 15$ points.
*   Swing Score state flips (e.g., "watch/weak" to "strong/elite").
*   Ensemble Forecast expected 5-day move spikes $>5\%$.
*   Real-time bulk/block trade notifications.

---

## 4. REST API Endpoint Catalog

All REST routes are defined on the Flask API version 1 blueprint (`api_bp`).

| Endpoint | Method | Service Method called | Description | Request/Response Payload |
| :--- | :--- | :--- | :--- | :--- |
| `/watchlist` | GET | `watchlist_service.get_watchlist_sections()` | Returns all watchlist sections and nested stock symbols. | **Response**: `[{"id": "1", "name": "Long Term", "items": ["RELIANCE", "TCS"]}]` |
| `/watchlist/sections` | POST | `watchlist_service.create_watchlist_section(id, name)` | Creates a new watchlist section. | **Body**: `{"id": "new_id", "name": "Swing Trading"}` |
| `/watchlist/sections/<id>` | PUT | `watchlist_service.rename_watchlist_section(id, name)` | Renames a specific section. | **Body**: `{"name": "Updated Section Name"}` |
| `/watchlist/sections/<id>` | DELETE| `watchlist_service.delete_watchlist_section(id)` | Deletes a section and removes all watchlisted items. | **Response**: `{"success": true}` |
| `/watchlist/items` | POST | `watchlist_service.add_watchlist_item(section_id, ticker)` | Adds a stock ticker to a specific watchlist section. | **Body**: `{"section_id": "1", "ticker": "INFY"}` |
| `/watchlist/items` | DELETE| `watchlist_service.delete_watchlist_item(section_id, ticker)` | Removes a stock ticker from a section. | **Body**: `{"section_id": "1", "ticker": "INFY"}` |
| `/watchlist/sections/reorder` | PUT | `watchlist_service.reorder_watchlist_sections(order)` | Reorders sections list. | **Body**: `{"order": ["2", "1", "3"]}` |
| `/watchlist/sections/<section_id>/reorder` | PUT | `watchlist_service.reorder_watchlist_items(section_id, order)` | Reorders items inside a section. | **Body**: `{"order": ["TCS", "RELIANCE"]}` |
| `/scan` | GET | `screener_service.get_scan_results()` | Gets the latest cached or live TradingView scan results. | **Query**: `live=true`, `limit=50` |
| `/screener/stock/<ticker>` | GET | `screener_service.get_stock_details(ticker)` | Fetches fundamentals, yfinance details, and pattern detections. | **Response**: detailed JSON containing price data and indicators. |
| `/ep/today` | GET | `ep_service.get_ep_today()` | Returns Episodic Pivot candidates detected today. | **Query**: `ep_type=all`, `confidence=all` |
| `/ep/watchlist` | GET | `watchlist_service.get_active_ep_watchlist()` | Returns active EP watchlist items with live prices and gains. | **Response**: list of active EP watches. |
| `/ep/watchlist` | POST | `watchlist_service.add_to_ep_watchlist(symbol, exchange, stop_price, notes)` | Adds/updates an item on the EP watchlist. | **Body**: `{"symbol": "TATASTEEL", "stop_price": 140.50, "notes": "Blowout Q3"}` |
| `/ep/watchlist/remove` | POST | `watchlist_service.remove_from_ep_watchlist(symbol)` | Marks an active EP watchlist item as EXPIRED. | **Body**: `{"symbol": "TATASTEEL"}` |
| `/ep/watchlist/trigger` | POST | `watchlist_service.trigger_ep_watchlist(symbol)` | Marks an active EP watchlist item as TRIGGERED. | **Body**: `{"symbol": "TATASTEEL"}` |
| `/ep/sugar-babies` | GET | `ep_service.get_ep_sugar_babies()` | Returns the list of historical high-momentum EP runners. | **Response**: `[{"symbol": "IRFC", "avg_burst_pct": 45.2}]` |
| `/bull_snort/screen` | GET | `bull_snort_service.screen_bull_snort()` | Screens NSE symbols for Phase-4 Bull Snort breakouts. | **Query**: `live=false` |
| `/ensemble_forecast` | POST | `forecast_math.compute_forecast_metrics()` | Blends ARIMA, Prophet, and Kronos models. | **Body**: `{"ticker": "RELIANCE", "horizon": 10}` |
| `/rrg/history` | GET | `rrg_history` query | Returns historic weekly sector coordinate data for rendering RRG. | **Response**: array of RRG objects containing `jdk_rs` and `rs_momentum`. |
| `/journal` | GET/POST | `journal_service` methods | CRUD operations for the persistent SQL trade journal. | **GET**: list of trades. **POST**: create a trade. |

---

## 5. Background Task Scheduler Map

The application runs a centralized job scheduler using APScheduler ([scheduler.py](file:///c:/Users/91996/Documents/My%20Projects/stock-screener/app/tasks/scheduler.py)). Below is the task mapping to Node.js.

| Job Name / ID | Python Function | Trigger / Schedule | Node.js Replacement Option | Description |
| :--- | :--- | :--- | :--- | :--- |
| `ep_refresh_job` | `refresh_ep_task` | Interval: 30 minutes | `node-cron` or BullMQ | Runs the EP screener scanner on Nifty universe to find breakouts. |
| `ipo_refresh_job` | `refresh_ipo_task` | Interval: 1 hour | `node-cron` or BullMQ | Downloads recent listings metrics, GMP changes, and updates caches. |
| `daily_momentum_score_job` | `calculate_all_scores` | Cron: 16:30 Daily (IST) | Cron trigger at `30 16 * * 1-5` | Recalculates Momentum Confidence Scores after market close. |
| `bull_snort_refresh` | `refresh_bull_snort` | Cron: 16:05 Daily (IST) | Cron trigger at `05 16 * * 1-5` | Runs the 4-phase Bull Snort breakout scan on NSE universe. |
| `market_cap_refresh` | `refresh_market_cap_cache` | Cron: 03:00 Daily (IST) | Cron trigger at `0 3 * * *` | Fetches fresh market caps using Yahoo Finance APIs and saves to DB. |
| `mi_ingest_job` | `ingest_market_intelligence_task` | Interval: 60 minutes | BullMQ queue workers | Ingests corporate event RSS feeds, NSE/BSE announcements, and news. |
| `startup_ipo_warmup` | `startup_ipo_cache_warmup` | One-shot: 10s after startup | `setTimeout()` on startup | Populates missing IPO listings in the metrics cache on boot. |

---

## 6. Node.js Ecosystem Replacements for Python Libraries

Use this mapping table to identify NPM packages when writing your `package.json`:

| Python Library | Node.js Alternative | Usage in Stock Screener |
| :--- | :--- | :--- |
| `Flask` | `Fastify` or `Express` | REST API routes, Server configuration, Static folder serving. |
| `SQLAlchemy` | `Prisma` | Database mapping, migrations, and transactional queries. |
| `APScheduler` | `BullMQ` (with Redis) or `agenda` | Periodic background jobs (EP screeners, score calculations, news ingests). |
| `pandas` / `numpy` | `danfojs-node` or simple javascript arrays | Data manipulation, dataframe operations, vector mathematics. |
| `yfinance` | `yahoo-finance2` (NPM) | Fetching historical prices, sector/company info, and market caps. |
| `statsmodels` (ARIMA)| `arima` (NPM) or WebAssembly ARIMA | Ensemble forecasting engine. |
| `fbprophet` | JS local time-series regression libraries | Seasonality-aware forecasting models. |
| `transformers` / `torch` | `onnxruntime-node` | Loading trained PyTorch/XGBoost models (like `Kronos-small`) via ONNX. |
