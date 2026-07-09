# MomentumScan Feature Overview

This document provides a comprehensive overview of all features and modules in the MomentumScan (stock-screener) Flask application. It is intended to serve as a reference for migrating the application to Node.js.

## Table of Contents
1. [Core Architecture](#core-architecture)
2. [Episodic Pivot (EP) Screener](#episodic-pivot-ep-screener)
3. [Watchlist Management](#watchlist-management)
4. [Bull Snort Screener](#bull-snort-screener)
5. [Market Breadth Dashboard](#market-breadth-dashboard)
6. [News & News Service](#news--news-service)
7. [IPO Module](#ipo-module)
8. [Alerts & Smart Alert Engine](#alerts--smart-alert-engine)
9. [Journal & Trade Journal](#journal--trade-journal)
10. [Market Intelligence & News Pipeline](#market-intelligence--news-pipeline)
11. [Kronos AI Panel & Forecasting](#kronos-ai-panel--forecasting)
12. [Sector Rotation & Thematic Analysis](#sector-rotation--thematic-analysis)
13. [Backtesting Engine](#backtesting-engine)
14. [Background Jobs & Scheduler](#background-jobs--scheduler)
15. [API Endpoints](#api-endpoints)
16. [Frontend Workspace & UI](#frontend-workspace--ui)
17. [Database Schema Overview](#database-schema-overview)
18. [Utilities & Helpers](#utilities--helpers)
19. [Testing & Quality Assurance](#testing--quality-assurance)

---

## Core Architecture

- **Application Factory**: `create_app()` in `app/__init__.py` uses the Flask application factory pattern, enabling multiple configurations (development, testing, production).
- **Extensions**: SQLAlchemy (`db`), APScheduler (background jobs), logging configured via `config.py`.
- **Blueprint Versioning**: All API routes are versioned under `/api/v1` via `app/api/v1/__init__.py`.
- **Service Layer**: Business logic resides in `app/services/`; Flask view functions delegate to service classes.
- **Models**: SQLAlchemy ORM models defined in `app/models.py`.
- **Configuration**: Environment-driven via `config.py` (DevelopmentConfig, ProductionConfig, TestingConfig, PytestConfig).
- **Extensions Initialization**: Centralized in `app/extensions.py` (`db = SQLAlchemy()`) and initialized in `create_app`.

### Key Files
- `run.py` – entry point.
- `app/__init__.py` – application factory, blueprint registration, error handlers, logging setup.
- `app/config.py` – configuration classes.
- `app/models.py` – SQLAlchemy models (User, WatchlistItem, EpWatchlist, EpFeature, etc.).
- `app/extensions.py` – Flask extensions initialization.
- `app/tasks/scheduler.py` – APScheduler job definitions and initialization.

---

## Episodic Pivot (EP) Screener

The EP Screener identifies neglected stocks that receive a powerful catalyst and undergo rapid repricing (typically 50–300% moves in 10–20 trading days). It adapts the strategy from Pradeep Bonde for the Indian equity market (NSE/BSE).

### Key Components
- **Scoring Engine** (`app/services/ep_service.py`):
  - Computes three sub‑scores: Neglect, Catalyst, Repricing (each 0–1).
  - Combines them into a final EP score (0–1) using either:
    - An XGBoost ML model (`models/ep_scoring_model_latest.pkl`) with a manifest (`*_manifest.json`) that defines feature order.
    - A hand‑crafted weighted fallback (0.25×Neglect + 0.35×|Catalyst| + 0.30×Repricing + 0.10×has_fundamentals).
  - Assigns EP Type (Growth EP, Turnaround EP, Story EP, Volume EP, Delayed EP, Short EP) based on catalyst score and event type.
  - Assigns Conviction (HIGH/MEDIUM/LOW) based on EP score and sub‑score thresholds.
- **Data Pipeline** (nightly via APScheduler):
  1. **OHLCV Ingest** – NSE Bhav Copy CSV → `daily_bars` table.
  2. **Event & Financial Ingest** – NSE XML filings → `corporate_events` and `fundamentals` tables (via NLP enrichment).
  3. **Scoring Engine** – Scans tickers with relative volume ≥ 3× or active news; writes features to `ep_features`.
  4. **Watchlist Maintenance** – Updates `ep_watchlist`, increments `days_on_watch`, expires stale entries (>20 days).
- **Database Schema** (see `docs/features/episodic_pivot_screener_spec.md` and `docs/features/ep_screener_architecture.md`):
  - `ep_features`: point‑in‑time features and scores.
  - `ep_watchlist`: active watchlist entries (status: ACTIVE/TRIGGERED/EXPIRED/STOPPED).
  - `sugar_babies`: habitual high‑beta runners.
  - `corporate_events`: parsed corporate filings.
  - `daily_bars`, `fundamentals` (see spec for full schema).
- **REST API** (`app/api/v1/ep.py`, `app/api/v1/ep_watchlist.py`):
  - `GET /api/ep/today` – filtered EP signals (by type, confidence, score, market cap, exchange, limit/offset).
  - `GET /api/ep/<symbol>/detail` – deep‑dive stats for a symbol.
  - `GET /api/ep/watchlist` – active watchlist with live CMP and gain %.
  - `POST /api/ep/watchlist` – add/update watchlist item (symbol, exchange, stop_price, notes).
  - `POST /api/ep/watchlist/remove` – remove item(s) by symbol.
  - `POST /api/ep/watchlist/trigger` – manually trigger an active item.
  - `GET /api/ep/sugar-babies` – active high‑beta setups.
  - `POST /api/ep/sugar-babies` – add/remove Sugar Baby.
  - `GET /api/ep/themes` – thematic clustering of EPs.
  - `GET /api/ep/sector-rotation` – EP data overlaid on sector strength.
  - `POST /api/ep/refresh` – trigger manual background scan.
  - `GET /api/ep/refresh/status` – scan execution status.
  - Backtest endpoints: `/api/ep/backtest/prepare`, `/api/ep/backtest/prep_status`, `/api/ep/backtest`.
- **Frontend Integration** (see `templates/index.html`, `static/js/app.js`):
  - Tabbed workspace: "Today's EPs", "Active Watchlist", "Sugar Babies", "Themes & Sector Rotation", "Backtest Engine".
  - Clickable ticker symbols open TradingView charts in a new tab.
  - Detail modal shows financial trends, events, and interactive TradingView Lightweight Chart.
  - Custom dropdowns for EP type and confidence filters.

### Key Functions in `ep_service.py`
- `predict_ep_score(features)` – loads ML model lazily, maps features via manifest, returns probability.
- `compute_neglect_score(...)`, `compute_catalyst_score(...)`, `compute_repricing_score(...)` – sub‑score formulas.
- `compute_ep_score(...)` – chooses ML or fallback, applies liquidity adjustment.
- `assign_ep_type(...)` – maps catalyst score/event type to EP type.
- `assign_confidence(...)` – maps EP score and sub‑scores to HIGH/MEDIUM/LOW.
- `EPService` class – encapsulates watchlist CRUD, trigger, days increment, etc.

### Background Jobs (`app/tasks/scheduler.py`)
- `ep_refresh_job` (every 30 min): fetches Bhav Copy, recalculates scores.
- `ep_model_training` (daily 16:00 IST): retrains XGBoost model, regenerates pickle and manifest.
- Watchlist increment: runs inside nightly scan to age out watchlist items.

### References
- `docs/features/episodic_pivot_screener_spec.md` – functional spec.
- `docs/features/ep_screener_architecture.md` – technical architecture.
- `docs/superpowers/2026-06-21-ep-scoring-implementation-plan.md` – implementation plan.
- `tests/unit/test_ep_screener.py`, `tests/unit/test_scoring_service.py` – unit tests.
- `e2e/tests/test_ep_view.py` – end‑to‑end Playwright test.

---

## Watchlist Management

### Overview
Users can maintain multiple watchlists (sections) and add/remove tickers. Two distinct watchlist concepts exist:
1. **Regular Watchlist** – user‑defined sections (e.g., "Watchlist", "Favorites") containing arbitrary tickers.
2. **EP Watchlist** – active EP candidates under observation (20‑session window) with trade‑specific fields (entry price, stop price, target, trigger type, notes).

### Regular Watchlist Service (`app/services/watchlist_service.py`)
- **Sections**:
  - `get_watchlist_sections()` – returns ordered list of sections (`{id, name}`).
  - `create_watchlist_section(sec_id, sec_name)` – upsert a section.
  - `rename_watchlist_section(sec_id, sec_name)`.
  - `delete_watchlist_section(sec_id)` – removes section and its items.
  - `reorder_watchlist_sections(order)` – reorder by list of section IDs.
- **Items**:
  - `get_watchlist_items(section_id)` – returns ticker strings in a section.
  - `add_watchlist_item(section_id, ticker)` – upserts a ticker in a section.
  - `delete_watchlist_item(section_id, ticker)` – removes a ticker.
  - `reorder_watchlist_items(section_id, order)` – reorder tickers within a section.

### EP Watchlist Service (also in `watchlist_service.py`)
- `get_active_ep_watchlist()` – returns list of dicts for active EP watchlist entries (includes symbol, exchange, stop_price, notes, days_on_watch, current price/gain %).
- `add_to_ep_watchlist(symbol, exchange, stop_price, notes)` – inserts or updates an entry; returns boolean indicating if newly added.
- `remove_from_ep_watchlist(symbol)` – marks entry as STOPPED.
- `trigger_ep_watchlist(symbol)` – sets status to TRIGGERED.
- `increment_ep_watchlist_days()` – increments `days_on_watch` for all ACTIVE entries; expires those >20 days (sets status EXPIRED).

### API Endpoints (`app/api/v1/watchlist.py`)
- `GET /api/watchlist/sections` – list all sections.
- `POST /api/watchlist/section` – create/rename section.
- `DELETE /api/watchlist/section/<section_id>` – delete section.
- `GET /api/watchlist/items/<section_id>` – get tickers in a section.
- `POST /api/watchlist/item` – add ticker to section.
- `DELETE /api/watchlist/item` – remove ticker from section.
- `POST /api/watchlist/reorder/<section_id>` – reorder items.
- `GET /api/ep/watchlist` – EP watchlist (see EP section).
- `POST /api/ep/watchlist` – add to EP watchlist.
- `POST /api/ep/watchlist/remove` – remove from EP watchlist.
- `POST /api/ep/watchlist/trigger` – trigger EP watchlist item.

### Frontend
- Watchlist management UI resides in the workspace (sidebar/modal) – users can create sections, add/remove tickers, reorder.
- EP watchlist displayed in the "Active Watchlist" tab of the EP screener workspace.
- Clicking a ticker opens TradingView chart.

### References
- `app/services/watchlist_service.py` – full implementation.
- `docs/features/watchlist_checkbox_add_spec.md` – spec for checkbox addition.
- `tests/unit/test_watchlist.py` – unit tests.
- `e2e/tests/test_watchlist_view.py` and `test_watchlist_functionality.py` – E2E tests.

---

## Bull Snort Screener

### Overview
Bull Snort is a momentum screener focused on identifying bullish breakout stocks (high relative volume, gap up, strong close). It shares UI patterns with the EP Screener but uses a different scoring logic.

### Key Components
- **Service**: `app/services/bull_snort_service.py` – contains core scanning logic (not fully inspected but referenced).
- **API**: `app/api/v1/bull_snort.py` – endpoints for fetching bull screener data.
- **Workspace Tabs** (specified in `docs/features/bull_snort_enhancements_spec.md`):
  - **Scanner** – main bull screener results.
  - **Watchlist** (planned enhancement) – shows bull screener results filtered to user’s watchlist.
  - **Rotation** (planned enhancement) – sector‑rotation style view for bull screens.
  - **Settings** – filter controls.
- **Frontend Enhancements** (per spec):
  - Clickable ticker symbols open TradingView chart (`https://www.tradingview.com/chart/?symbol=NSE:<symbol>`).
  - New tabs added to the Bull Snort workspace header.
  - Responsive layout down to 320 px width.

### API Endpoints (inferred from spec and existing tests)
- `GET /api/bull_snort/screen` – returns bull screener rows (symbol, price, change %, volume, gap, etc.).
  - Accepts filters: exchange, min_price, max_price, min_volume, etc.
  - Planned: `watchlist=1` query param to filter to user’s watchlist.
- `GET /api/bull_snort/watchlist` (proposed) – bull screener results limited to watchlist.
- `GET /api/bull_snort/rotation` (proposed) – sector rotation data for bull screens.

### References
- `docs/features/bull_snort_enhancements_spec.md` – enhancement spec (watchlist tab, clickable ticker, rotation tab).
- `tests/unit/test_bull_snort_api.py` – unit tests.
- `e2e/tests/test_bull_snort_view.py` – E2E test.

---

## Market Breadth Dashboard

### Overview
Provides market‑wide breadth indicators (advance/decline ratio, new highs‑lows, sector strength) to gauge overall market health.

### Key Components
- **Service**: `app/services/market_breadth_service.py` – computes breadth metrics from `daily_bars`.
- **API**: `app/api/v1/market_breadth.py` – endpoints for breadth data.
- **Workspace Tab**: "Market Breadth" appears in the main workspace (index.html).

### API Endpoints
- `GET /api/market_breadth/summary` – returns overall advance/decline counts, new highs/lows, etc.
- `GET /api/market_breadth/sector_performance` – returns performance per sector (e.g., % of stocks above 20‑day MA).
- `GET /api/market_breadth/advance_decline` – time series of advance/decline ratio.

### Frontend
- Displays charts and tables using Chart.js or similar (via `static/js/app.js`).
- Allows toggling between different breadth metrics.

### References
- `app/services/market_breadth_service.py`
- `app/api/v1/market_breadth.py`
- `tests/unit/test_market_breadth.py`
- `e2e/tests/test_market_breadth_view.py`

---

## News & News Service

### Overview
Aggregates news from multiple sources (Google News RSS, MarketAux, NSE RSS, Moneycontrol) and applies NLP enrichment (sentiment, summarization, event classification) to produce actionable catalysts for the EP screener.

### Key Components
- **Market Intelligence Layer** (`app/services/market_intelligence/`):
  - **Providers**: `google_rss.py`, `nse_rss.py`, `marketaux.py`, each implementing a base interface (`base.py`).
  - **Manager** (`manager.py`) – orchestrates fetching, deduplication (`deduplicator.py`), and enrichment.
  - **AI Enrichment** (`ai/`):
    - `mapper.py` – maps raw headlines to event types using LLMs or rule‑based classifiers.
    - `ai_enrichment.py` – runs NLP models for sentiment and summarization.
    - `executor.py`, `worker.py` – background job runners for enrichment.
  - **Cache Layer** (`cache/`) – Redis‑backed or in‑memory caching (`manager.py`, `memory.py`, `no_cache.py`, `base.py`).
  - **Repositories** (`repositories/`) – data access layer for events and news.
  - **Services** (`services/`):
    - `event_service.py` – persists and retrieves corporate events.
    - `news_service.py` – persists and retrieves raw news articles.
- **NLP Service** (`app/services/nlp_service.py`) – wrapper for external NLP APIs or local models (sentiment, summarization, event classification).
- **Scheduled Jobs** (`app/tasks/scheduler.py`):
  - News fetch jobs run periodically (frequency defined in config).
  - NLP enrichment jobs run after fetch.

### Data Flow
1. Providers fetch raw RSS/JSON feeds → raw articles/events.
2. Deduplicator removes duplicates based on URL/hash.
3. Enrichment pipeline:
   - Sentiment analysis (via NLP service).
   - Summarization (optional).
   - Event classification (maps to `corporate_events.event_type`).
4. Results stored in:
   - `corporate_events` table (for EP catalyst scoring).
   - `news_articles` table (if applicable) – raw news for UI.
5. API endpoints serve enriched data to frontend.

### API Endpoints (`app/api/v1/news.py`)
- `GET /api/news/latest` – paginated list of recent news articles with sentiment/summary.
- `GET /api/news/events` – list of corporate events (used by EP screener for catalyst lookup).
- `POST /api/news/refresh` – trigger manual news fetch.
- `GET /api/news/status` – status of last fetch/enrichment job.

### Frontend
- News appears in the EP screener detail modal (events section) and possibly a dedicated "News" workspace tab (depending on UI layout).
- Sentiment displayed via color‑coded badges (positive/negative/neutral).
- Summarized text shown in tooltip or expandable section.

### References
- `app/services/market_intelligence/` – full provider and enrichment logic.
- `app/services/nlp_service.py` – NLP wrapper.
- `docs/features/corporate-events-nlp-enhancement.md` – spec for NLP enrichment.
- `tests/unit/test_market_intelligence.py` – unit tests.
- `e2e/tests/test_news_view.py` – E2E test (if exists).

---

## IPO Module

### Overview
Tracks upcoming and recent IPOs, provides IPO performance metrics, and integrates IPO data into the EP screener (e.g., IPO momentum scans).

### Key Components
- **Model**: `Ipo` (in `app/models.py`) – fields: symbol, exchange, ipo_date, price, lot_size, issue_size, etc.
- **Service**: `app/services/ipo_service.py` – fetches IPO data from NSE/BSE APIs, updates database.
- **Scheduler**: `app/tasks/scheduler.py` – `ipo_refresh_job` (hourly) updates IPO calendar.
- **API**: `app/api/v1/ipo.py` – endpoints for IPO data.
- **Frontend**: IPO data shown in a dedicated workspace tab or integrated into EP screener filters.

### API Endpoints
- `GET /api/ipo/upcoming` – list of upcoming IPOs (date, symbol, price, lot size).
- `GET /api/ipo/recent` – list of recently listed IPOs with performance since listing.
- `GET /api/ipo/<symbol>/detail` – detailed info for a specific IPO.
- `POST /api/ipo/refresh` – trigger manual IPO data refresh.

### Frontend
- Displays IPO calendar, allows filtering by date range/sector.
- IPO performance chart (price since listing).
- Integration with EP screener: IPO flag as a catalyst type.

### References
- `app/services/ipo_service.py`
- `app/api/v1/ipo.py`
- `tests/unit/test_ipo.py`
- `e2e/tests/test_ipo_view.py`

---

## Alerts & Smart Alert Engine

### Overview
Users can create price‑based, technical‑indicator‑based, or event‑based alerts. The Smart Alert Engine evaluates conditions in real‑time (via background jobs) and sends notifications (email, Telegram, in‑app).

### Key Components
- **Model**: `Alert` (in `app/models.py`) – fields: user_id, symbol, condition_type (price_above, rsi_below, volume_spike, event_type, etc.), threshold, is_active, last_triggered.
- **Service**: `app/services/alert_service.py` – evaluates conditions against latest market data.
- **Notifier Plugins**: abstract base in `app/services/alert_service.py`; concrete implementations for email, Telegram (`app/services/telegram_notifier.py` if exists), in‑app storage.
- **Scheduler**: `app/tasks/scheduler.py` – `alert_check_job` (runs every minute) evaluates all active alerts.
- **API**: `app/api/v1/alerts.py` – CRUD endpoints for alerts.
- **Frontend**: Alert management UI (create/edit/delete, view triggered alerts).

### Alert Condition Types (examples)
- Price above/below a level.
- Percentage change since open/close.
- RSI above/below threshold.
- Volume spike (X× average volume).
- New high/new low.
- Specific corporate event (earnings, order win, etc.).
- EP score crossing a threshold.

### Notification Channels
- **Email**: via Flask‑Mail or SMTP (configured in `config.py`).
- **Telegram**: via bot token and chat ID (if `ENABLE_TELEGRAM_ALERTS` true).
- **In‑App**: stored in database and shown in a bell/notifications panel.

### API Endpoints
- `GET /api/alerts` – list user’s alerts.
- `POST /api/alerts` – create new alert.
- `PUT /api/alerts/<alert_id>` – update alert.
- `DELETE /api/alerts/<alert_id>` – delete alert.
- `POST /api/alerts/test` – test a single alert against current data.
- `GET /api/alerts/history` – list triggered alerts (with timestamps).

### Frontend
- Modal/form to create alert with dropdown for condition type, numeric input, etc.
- Bell icon in header showing unread alert count.
- Alert history page showing triggered alerts and outcome.

### References
- `app/services/alert_service.py`
- `app/api/v1/alerts.py`
- `docs/features/smart-alert-engine.md` – spec for smart alert engine.
- `tests/unit/test_alert_service.py`
- `e2e/tests/test_alerts_api.py`

---

## Journal & Trade Journal

### Overview
Allows users to maintain a trading journal, attach notes to trades/watchlist items, and review performance over time.

### Key Components
- **Model**: `JournalEntry` (in `app/models.py`) – fields: user_id, symbol, entry_date, entry_type (trade/note), price, quantity, notes, tags.
- **Service**: `app/services/journal_service.py` – CRUD operations, aggregation for performance stats (win rate, average profit, etc.).
- **API**: `app/api/v1/journal.py` – endpoints for journal entries.
- **Frontend**: Journal workspace tab with table of entries, filters (symbol, date range, type), ability to add/edit/delete entries, and summary statistics panel.

### API Endpoints
- `GET /api/journal/entries` – paginated list of journal entries (filter by symbol, type, date).
- `POST /api/journal/entry` – create new entry.
- `PUT /api/journal/entry/<entry_id>` – update entry.
- `DELETE /api/journal/entry/<entry_id>` – delete entry.
- `GET /api/journal/summary` – returns aggregate stats (win rate, avg profit, total trades, etc.).

### Frontend Features
- Rich text editor for notes.
- Tagging system for categorizing trades (e.g., "swing", "intraday", "EP").
- Charts: equity curve, win/loss pie chart, monthly returns.
- Ability to link journal entry to a watchlist item or EP watchlist entry.

### References
- `app/services/journal_service.py`
- `app/api/v1/journal.py`
- `docs/features/journal.md` (if exists) – otherwise infer from code.
- `tests/unit/test_journal.py`
- `e2e/tests/test_journal_view.py`

---

## Market Intelligence & News Pipeline

### Overview
A modular pipeline that ingests raw news/fundamentals from multiple sources, deduplicates, enriches with NLP (sentiment, summarization, event classification), and stores enriched data for use by other services (EP screener, alerts, journal).

### Pipeline Stages
1. **Ingestion** – Provider classes (`google_rss.py`, `nse_rss.py`, `marketaux.py`) fetch raw items.
2. **Deduplication** – `deduplicator.py` removes duplicates based on URL hash or content hash.
3. **Enrichment** – AI enrichment (`ai/`):
   - **Mapper** (`mapper.py`) – maps raw text to event types (uses LLM or rule‑based classifier).
   - **Enricher** (`ai_enrichment.py`) – runs sentiment analysis and summarization (via external API or local model).
   - **Executor/Worker** – runs enrichment jobs in background (via APScheduler or separate worker processes).
4. **Storage** – Repositories (`repositories/`) persist enriched data to `corporate_events` and `news_articles` tables.
5. **Cache** – Cache layer (`cache/`) prevents re‑fetching of identical items within a TTL.

### Key Classes
- `BaseProvider` (abstract) – defines `fetch()` method.
- `GoogleRSSProvider`, `NSEProvider`, `MarketAuxProvider` – concrete implementations.
- `Deduplicator` – uses hash‑set or Redis set.
- `EnrichmentManager` – orchestrates mapper and enricher.
- `EventRepository` / `NewsRepository` – CRUD for `corporate_events` and `news_articles`.
- `CacheManager` – abstract cache with `MemoryCache` and `RedisCache` implementations.

### Configuration
- Feature flags: `ENABLE_NLP_ENRICHMENT`, `ENABLE_TELEGRAM_ALERTS`, etc.
- API keys for external services (NewsAPI, MarketAux, Hugging Face, etc.) stored in environment variables.
- Cache TTL configurable.

### Data Usage
- **EP Screener**: `corporate_events.event_type` feeds into `compute_catalyst_score`.
- **Alerts**: Event‑based alerts can trigger on new `corporate_events` entries.
- **Journal**: Users can link journal entries to news/events.
- **Frontend**: News tab shows enriched articles with sentiment badges and summaries.

### References
- `app/services/market_intelligence/` – full pipeline implementation.
- `docs/features/corporate-events-nlp-enhancement.md` – NLP enhancement spec.
- `tests/unit/test_market_intelligence.py` – unit tests.
- `e2e/tests/test_market_intelligence_view.py` – E2E test (if exists).

---

## Kronos AI Panel & Forecasting

### Overview
Kronos is an AI‑powered forecasting panel that provides price predictions, trend forecasts, and regime‑based signals using deep learning models (e.g., Temporal Fusion Transformers, PatchTST).

### Key Components
- **Model**: `model/kronos.py` – defines the Kronos forecasting architecture (likely a PyTorch model).
- **Service**: `app/services/kronos_service.py` (if exists) – loads model, prepares features, runs inference.
- **Scheduler**: `app/tasks/scheduler.py` – `kronos_forecast_job` (daily) generates forecasts for all tracked symbols.
- **API**: `app/api/v1/kronos.py` – endpoints to retrieve forecasts.
- **Frontend**: Kronos AI Panel workspace tab showing forecast charts, confidence intervals, and model diagnostics.

### Forecasting Workflow
1. **Feature Preparation** – uses historical OHLCV, technical indicators (from `app/utils/technical.py`), fundamentals, and sentiment scores.
2. **Model Inference** – Kronos model outputs:
   - Point forecast (next‑day close).
   - Prediction interval (e.g., 80% CI).
   - Regime probabilities (bull/bear/sideways).
3. **Post‑Processing** – converts raw model output to user‑friendly metrics (expected return, confidence score).
4. **Storage** – forecasts saved to `kronos_forecasts` table (symbol, forecast_date, target_date, predicted_price, lower_bound, upper_bound, confidence).
5. **API Exposure** – `/api/kronos/forecast/<symbol>` returns latest forecast; `/api/kronos/forecast/history` returns time series.

### API Endpoints (inferred)
- `GET /api/kronos/forecast/<symbol>` – latest forecast for symbol.
- `GET /api/kronos/forecast/history/<symbol>` – historical forecast vs actual.
- `GET /api/kronos/performance` – model accuracy metrics (MAE, hit rate).
- `POST /api/kronos/retrain` – trigger model retraining (admin only).

### Frontend Features
- Interactive chart showing historical price, forecast line, and confidence band.
- Toggle to show/hide confidence intervals.
- Metrics cards: expected return, confidence, win rate.
- Ability to compare multiple symbols side‑by‑side.

### References
- `model/kronos.py` – model definition.
- `docs/features/KRONOS_AI_PANEL.md` – spec for Kronos panel.
- `docs/features/kronos-watchlist-batch-forecasting.md` – batch forecasting spec.
- `tests/unit/test_kronos.py` – unit tests.
- `e2e/tests/test_kronos_view.py` – E2E test.

---

## Sector Rotation & Thematic Analysis

### Overview
Provides sector‑wise relative strength analysis and thematic baskets (e.g., "Defence", "EV", "PLI") to help investors rotate capital into stronger sectors/themes.

### Key Components
- **Service**: `app/services/sector_rotation_service.py` (or similar) – computes relative strength, momentum, and breadth per sector.
- **Data Sources**:
  - Sector constituents from NSE/BSE sector indices.
  - Daily OHLCV from `daily_bars`.
  - Fundamental data (market cap, revenue) from `fundamentals`.
- **API**: `app/api/v1/sector_rotation.py` – endpoints for sector scores, thematic baskets.
- **Frontend**: Workspace tab "Themes & Sector Rotation" showing:
  - Sector strength table (ranked by relative strength).
  - Thematic heatmap (e.g., heat map of theme participation).
  - Ability to drill down into a sector/theme to see constituent stocks.

### Calculations
- **Relative Strength (RS)**: price performance of sector index vs NIFTY 50 over various lookbacks (20‑day, 50‑day, 200‑day).
- **Momentum Score**: rate of change of RS.
- **Breadth**: % of stocks in sector above 20‑day MA, above 50‑day MA.
- **Thematic Score**: aggregate score of stocks belonging to a theme (based on predefined tickers or NLP‑derived theme tags).

### API Endpoints
- `GET /api/sector_rotation/summary` – returns sector scores and ranks.
- `GET /api/sector_rotation/themes` – returns thematic basket performance.
- `GET /api/sector_rotation/constituents/<sector>` – list of stocks in a sector.
- `GET /api/sector_rotation/history/<sector>` – time series of sector score.

### Frontend Features
- Bar chart of sector RS scores.
- Clickable sector to open constituent list.
- Thematic bubble chart (size = market cap, color = performance).
- Export to CSV.

### References
- `docs/features/sector-rotation-timeline.md` – spec for sector rotation.
- `app/services/sector_rotation_service.py` (if exists) – otherwise infer from `market_breadth_service.py` which may overlap.
- `tests/unit/test_sector_rotation.py`
- `e2e/tests/test_sector_rotation_view.py`

---

## Backtesting Engine

### Overview
Allows users to backtest trading strategies (EP‑based, bull snort, custom) over historical data and evaluate performance metrics.

### Key Components
- **Service**: `app/services/backtest_service.py` – core backtesting engine.
- **Strategy Framework** – users can select built‑in strategies (EP breakout, bull snort breakout) or define custom rules via UI.
- **Data Loader** – fetches historical OHLCV, fundamentals, events from PostgreSQL/SQLite.
- **Executor** – simulates trades day‑by‑day, applies slippage/commission, calculates equity curve.
- **Metrics Calculator** – computes CAGR, Sharpe, max drawdown, win rate, profit factor, etc.
- **API**: `app/api/v1/backtest.py` – endpoints to run backtests and retrieve results.
- **Frontend**: Backtest Engine workspace tab with:
  - Strategy selector.
  - Date range picker.
  - Symbol universe selector (watchlist, sector, index).
  - Parameter inputs (stop loss, target, position sizing).
  - Run button.
  - Results panel showing equity curve, trade list, metrics table.

### Backtest Workflow
1. User selects strategy and parameters.
2. Service loads historical data for each symbol in the universe.
3. For each trading day:
   - Evaluate entry conditions.
   - If position open, evaluate exit conditions (stop/target/time‑based).
   - Record trade P&L.
4. Aggregate trades into equity curve.
5. Compute performance metrics.
6. Store result (optional) and return to frontend.

### API Endpoints
- `POST /api/backtest/run` – run a backtest (payload: strategy, universe, date range, parameters).
- `GET /api/backtest/result/<job_id>` – retrieve status/results of a background backtest job.
- `GET /api/backtest/history` – list past backtest runs.
- `DELETE /api/backtest/<job_id>` – delete a stored backtest result.

### Frontend Features
- Visual equity curve (Chart.js).
- Trade list table (entry/exit dates, P&L, duration).
- Metrics summary card.
- Walk‑forward analysis option.
- Monte Carlo simulation tab (advanced).

### References
- `docs/features/multi-model-ensemble-forecasting.md` – may overlap with backtesting.
- `app/services/backtest_service.py` (if exists) – otherwise infer from `score_calculator.py` and `test_score_calculator.py`.
- `tests/unit/test_score_calculator.py` – unit tests for scoring/backtest logic.
- `e2e/tests/test_backtest_view.py` – E2E test.

---

## Background Jobs & Scheduler

### Overview
APScheduler runs periodic jobs for data ingestion, model training, watchlist maintenance, alert evaluation, and more.

### Job Definitions (`app/tasks/scheduler.py`)
| Job ID | Trigger | Description |
|--------|---------|-------------|
| `ep_refresh_job` | Interval (30 min) | Fetch NSE Bhav Copy, recalc EP scores, update `ep_features`. |
| `ipo_refresh_job` | Interval (1 hour) | Sync IPO calendar from NSE/BSE APIs. |
| `ep_model_training` | Cron (daily 16:00 IST) | Retrain XGBoost EP model, regenerate pickle and manifest. |
| `watchlist_increment` | Embedded in `ep_refresh_job` | Increment `days_on_watch` for EP watchlist, expire stale entries. |
| `alert_check_job` | Interval (1 min) | Evaluate all active alerts against latest market data. |
| `news_fetch_job` | Interval (configurable) | Fetch raw news from RSS/APIs. |
| `nlp_enrichment_job` | Interval (after news_fetch) | Run NLP enrichment on raw news. |
| `kronos_forecast_job` | Interval (daily) | Generate Kronos forecasts for all symbols. |
| `sector_refresh_job` | Interval (daily) | Recalculate sector rotation scores. |
| `backup_job` | Interval (daily) | Backup SQLite database (if applicable). |

### Job Characteristics
- **Thread Safety**: Jobs that access the DB use `app.app_context()` and rely on SQLAlchemy’s scoped session; some use explicit locks (`ep_refresh_lock`) to prevent overlapping runs.
- **Testing Guard**: Jobs are skipped when `TESTING=True` or when `PYTEST_CURRENT_TEST` env var is set (to avoid SQLite lock issues in pytest).
- **Logging**: Each job logs start/end and any exceptions via `app.logger`.

### Configuration
- Job intervals defined in `config.py` (e.g., `EP_REFRESH_INTERVAL_MINUTES = 30`).
- Feature flags (`ENABLE_BACKGROUND_TASKS`) can globally disable all scheduler jobs.

### References
- `app/tasks/scheduler.py` – full job definitions.
- `app/config.py` – configuration constants.
- `tests/unit/test_scheduler.py` – unit tests for scheduler.
- `scripts/run_performance_tests.py` – may invoke scheduler jobs for benchmarking.

---

## API Endpoints Overview

All API routes are mounted under `/api/v1` via the `api_bp` blueprint (`app/api/v1/__init__.py`). Below is a categorized list of endpoints by module.

### EP Screener
- `GET /api/ep/today`
- `GET /api/ep/<symbol>/detail`
- `GET /api/ep/watchlist`
- `POST /api/ep/watchlist`
- `POST /api/ep/watchlist/remove`
- `POST /api/ep/watchlist/trigger`
- `GET /api/ep/sugar-babies`
- `POST /api/ep/sugar-babies`
- `GET /api/ep/themes`
- `GET /api/ep/sector-rotation`
- `POST /api/ep/refresh`
- `GET /api/ep/refresh/status`
- `POST /api/ep/backtest/prepare`
- `GET /api/ep/backtest/prep_status`
- `POST /api/ep/backtest`

### Watchlist (Regular)
- `GET /api/watchlist/sections`
- `POST /api/watchlist/section`
- `DELETE /api/watchlist/section/<section_id>`
- `GET /api/watchlist/items/<section_id>`
- `POST /api/watchlist/item`
- `DELETE /api/watchlist/item`
- `POST /api/watchlist/reorder/<section_id>`

### Bull Snort
- `GET /api/bull_snort/screen`
- *(Planned)* `GET /api/bull_snort/watchlist`
- *(Planned)* `GET /api/bull_snort/rotation`

### Market Breadth
- `GET /api/market_breadth/summary`
- `GET /api/market_breadth/sector_performance`
- `GET /api/market_breadth/advance_decline`

### News
- `GET /api/news/latest`
- `GET /api/news/events`
- `POST /api/news/refresh`
- `GET /api/news/status`

### IPO
- `GET /api/ipo/upcoming`
- `GET /api/ipo/recent`
- `GET /api/ipo/<symbol>/detail`
- `POST /api/ipo/refresh`

### Alerts
- `GET /api/alerts`
- `POST /api/alerts`
- `PUT /api/alerts/<alert_id>`
- `DELETE /api/alerts/<alert_id>`
- `POST /api/alerts/test`
- `GET /api/alerts/history`

### Journal
- `GET /api/journal/entries`
- `POST /api/journal/entry`
- `PUT /api/journal/entry/<entry_id>`
- `DELETE /api/journal/entry/<entry_id>`
- `GET /api/journal/summary`

### Kronos (if implemented)
- `GET /api/kronos/forecast/<symbol>`
- `GET /api/kronos/forecast/history/<symbol>`
- `GET /api/kronos/performance`
- `POST /api/kronos/retrain`

### Sector Rotation
- `GET /api/sector_rotation/summary`
- `GET /api/sector_rotation/themes`
- `GET /api/sector_rotation/constituents/<sector>`
- `GET /api/sector_rotation/history/<sector>`

### Backtest
- `POST /api/backtest/run`
- `GET /api/backtest/result/<job_id>`
- `GET /api/backtest/history`
- `DELETE /api/backtest/<job_id>`

### Health & System
- `GET /api/health` – simple health check.
- `GET /api/version` – returns app version.

### Authentication (if implemented)
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/profile`

> **Note**: Authentication appears to be minimal or absent in the current codebase (no `User` model with password hash seen in `models.py` snippets). If auth is required for the Node.js migration, consider adding JWT‑based session management.

---

## Frontend Workspace & UI

### Architecture
- **Single‑Page Application (SPA)** using vanilla JavaScript (no framework) – `static/js/app.js` orchestrates UI updates.
- **HTML Shell**: `templates/index.html` contains:
  - Header with workspace selector (dropdown to switch between EP Screener, Bull Snort, Market Breadth, Journal, Kronos, etc.).
  - Sidebar for filters and watchlist management.
  - Main panel containing tabbed workspace (each workspace has its own set of tabs).
  - Footer with version/status info.
- **Styling**: Tailwind CSS via `style.css` (generated from `tailwind.config.js`). Custom utilities in `assets/css/custom.css` if present.
- **Charting**: TradingView Lightweight Charts for candlestick charts in detail modals; Chart.js for dashboard‑style charts (breadth, sector rotation, equity curves).
- **Data Fetching**: `app.js` uses `fetch()` to call `/api/v1/*` endpoints; handles loading states, error display.
- **Modal System**: Reusable modal component for detail views, alert creation, journal entry, etc.
- **Local Storage**: User preferences (selected workspace, tab, column widths, theme) stored in `localStorage`.

### Workspace Tabs (Examples)
| Workspace | Tabs |
|-----------|------|
| EP Screener | Today's EPs, Active Watchlist, Sugar Babies, Themes & Sector Rotation, Backtest Engine |
| Bull Snort | Scanner, Watchlist (planned), Rotation (planned), Settings |
| Market Breadth | Summary, Sector Performance, Advance/Decline |
| Journal | Entries, Statistics, Charts |
| Kronos | Forecast, Performance, Model Info |
| Settings | API Keys, Feature Flags, Appearance |

### Key UI Components
- **Header Workspace Switcher** – dropdown to change workspace.
- **Sidebar Filters** – text search, exchange dropdown, price/volume sliders, checkboxes for EP type/confidence.
- **Tabbed Panel** – each workspace renders its own set of tabs (implemented as `<button>` groups with data-tab="...">` + associated `<div class="tab-content">`).
- **Data Tables** – server‑side pagination, sorting, column toggling (visible/hidden columns stored in localStorage).
- **Clickable Tickers** – `<a>` or `<button>` with `onclick="openTradingView('NSE:RELIANCE')"`.
- **Detail Modal** – triggered by clicking a table row; loads data via API and renders:
  - Symbol header with current price and change %.
  - Tabs: Overview, Financials, Events, Chart, Notes.
  - Financials table (quarterly revenue, profit, YoY %).
  - Events list (date, type, sentiment, summary).
  - TradingView Lightweight Chart (candlestick + volume).
  - Notes textarea (linked to journal).
- **Alert Bell** – shows count of untriggered/triggered alerts; clicking opens alert management modal.
- **Journal Button** – opens journal entry form linked to current symbol.

### Responsive Design
- Tailwind breakpoints: `sm` (640px), `md` (768px), `lg` (1024px), `xl` (1280px).
- Sidebar collapses to hamburger menu on `< md`.
- Tables become scrollable horizontally on small screens.
- Modals use full‑screen width on `< sm`.

### References
- `static/js/app.js` – main frontend logic.
- `templates/index.html` – base layout.
- `assets/css/style.css` – Tailwind output.
- `docs/features/ui_ux_improvement_plan.md` – UI/UX improvement plan.
- `docs/features/workspace-ui-tier1-ux.md` – tier‑1 UX spec.
- `e2e/tests/` – Playwright test suite for each workspace/view.

---

## Database Schema Overview

The application uses SQLAlchemy ORM with SQLite (default) but can switch to PostgreSQL/MySQL via `DATABASE_URL`.

### Core Models (`app/models.py`)

| Model | Description | Key Fields |
|-------|-------------|------------|
| `User` | Account information (if auth enabled) | `id`, `username`, `email`, `password_hash`, `is_active`, `created_at` |
| `WatchlistSection` | User‑defined watchlist sections | `id`, `name`, `position` |
| `WatchlistItem` | Ticker within a section | `id`, `section_id` (FK), `ticker`, `position` |
| `EpWatchlist` | Active EP watchlist entries | `id`, `symbol`, `exchange`, `catalyst_date`, `status` (`ACTIVE`/`TRIGGERED`/`EXPIRED`/`STOPPED`), `days_on_watch`, `entry_price`, `stop_price`, `target_price`, `trigger_type`, `notes`, `ep_score` |
| `EpFeature` | Daily computed EP features/scores | `symbol`, `exchange`, `feature_date`, `neglect_score`, `catalyst_score`, `reprice_score`, `ep_score`, `ep_type`, `confidence`, `price_change_pct`, `gap_pct`, `rel_volume`, `close_loc`, `market_cap_cr`, `avg_turnover_cr` |
| `CorporateEvent` | Parsed corporate filings | `symbol`, `exchange`, `event_date`, `event_type`, `headline`, `sentiment` (-1,0,1), `nlp_sentiment_score`, `summary` |
| `Fundamental` | Quarterly fundamentals | `symbol`, `exchange`, `result_date`, `revenue`, `net_profit`, `eps`, `revenue_yoy_pct`, `net_profit_yoy_pct`, `surprise_type` |
| `Ipo` | IPO calendar | `symbol`, `exchange`, `ipo_date`, `price`, `lot_size`, `issue_size`, `listing_date` |
| `Alert` | User alerts | `id`, `user_id`, `symbol`, `condition_type`, `threshold`, `is_active`, `last_triggered`, `created_at` |
| `JournalEntry` | Trade journal | `id`, `user_id`, `symbol`, `entry_date`, `entry_type` (`trade`/`note`), `price`, `quantity`, `notes`, `tags` |
| `KronosForecast` (if exists) | AI forecast storage | `symbol`, `forecast_date`, `target_date`, `predicted_price`, `lower_bound`, `upper_bound`, `confidence` |
| `SectorScore` (if exists) | Sector rotation snapshot | `sector`, `date`, `relative_strength`, `momentum_score`, `breadth_pct` |
| `NewsArticle` | Raw news articles | `title`, `url`, `published_at`, `source`, `raw_text` |
| `EnrichedNews` | NLP‑enriched news | `news_article_id` (FK), `sentiment`, `summary`, `event_type` |

### Indexes (selected)
- `idx_ep_features_date` on `ep_features(feature_date DESC)`
- `idx_ep_features_score` on `ep_features(feature_date DESC, ep_score DESC)`
- `idx_ep_features_symbol_date` on `ep_features(symbol, feature_date DESC)`
- `idx_corp_events_symbol_date` on `corporate_events(symbol, event_date DESC)`
- `idx_daily_bars_symbol_date` on `daily_bars(symbol, trade_date DESC)`

### Migration Note
For Node.js migration, consider using an ORM like **TypeORM** or **Prisma**, or raw SQL with a query builder (Knex.js). The schema above can be translated directly to table definitions.

### References
- `app/models.py` – full model definitions.
- `app/database.py` – SQLAlchemy engine/session setup (if separate).
- `docs/features/ep_screener_architecture.md` – detailed schema diagrams.
- `scripts/verify_migration.py` – utility to verify migrated API endpoints (useful for Node.js validation).

---

## Utilities & Helpers

### Technical Indicators (`app/utils/technical.py`)
- Functions for fetching historical prices (`fetch_historical_prices`).
- Calculation of common indicators: RSI, MACD, Bollinger Bands, ATR, VWAP, moving averages (SMA, EMA).
- Helper to compute relative volume (`rel_volume = volume / avg_volume_20`).
- Gap percentage, close location (`close_loc = (close - low) / (high - low)`).
- Price change percentages.

### Forecasting Math (`app/utils/forecast_math.py`)
- Exponential smoothing, ARIMA wrappers, Monte Carlo simulation helpers.
- Ensemble averaging functions.

### Pattern Detection (`app/utils/pattern_detection.py`)
- Candlestick pattern detection (engulfing, hammer, shooting star, doji, etc.).
- Breakout/breakdown detection (price > N‑day high/low with volume confirmation).

### Journal Math (`app/utils/journal_math.py`)
- Trade statistics: win rate, average win/loss, profit factor, expectancy, Sharpe ratio (simplified).
- Equity curve generation from trade list.

### FX Utilities (`app/utils/fx_utils.py`)
- Currency conversion utilities (INR to USD, etc.) using cached rates.

### Helpers (`app/helpers.py` or `app/utils/helpers.py`)
- Pagination helpers.
- Response formatting wrappers.
- Error handling decorators.

### Exceptions (`app/exceptions.py`)
- Custom exception classes (e.g., `InvalidUsage`, `ServiceUnavailable`) with HTTP status codes.

### References
- `app/utils/` – all utility modules.
- `tests/unit/test_technical.py`, `test_forecast_math.py`, `test_pattern_detection.py`, `test_journal_math.py`.

---

## Testing & Quality Assurance

### Frameworks
- **Unit/Integration Tests**: `pytest` with `tests/` directory.
- **Fixtures**: `tests/conftest.py` provides:
  - `app` fixture – creates Flask app in `TESTING` mode.
  - `client` fixture – test client for making requests.
  - `db` fixture – creates a temporary SQLite database.
- **Coverage**: Enforced via `pytest --cov=app`; targets:
  - ≥85% for service layer.
  - ≥90% for EP scoring inference code.
- **End‑to‑End Tests**: Playwright (`e2e/tests/`), run with `python -m pytest -q e2e/tests/*.py`.
- **Performance Tests**: `scripts/run_performance_tests.py` – benchmarks latency of key APIs (EP screener, watchlist, news).
- **Migration Verification**: `scripts/verify_migration.py` – sanity‑check script to ensure migrated endpoints return expected schema/status.

### Test Organization
- `tests/unit/` – unit tests for services, utilities, models.
- `tests/unit/test_*_service.py` – service‑layer tests (mock external HTTP calls).
- `tests/unit/test_*_api.py` – API endpoint tests (use Flask test client).
- `tests/unit/test_*_math.py` – mathematical utility tests.
- `e2e/tests/` – Playwright tests covering UI workflows:
  - `test_home_page.py` – landing page loads.
  - `test_dashboard_view.py` – EP screener workspace loads, tabs switch.
  - `test_ep_view.py` – EP detail modal opens, chart renders.
  - `test_watchlist_view.py` – watchlist section/item CRUD.
  - `test_bull_snort_view.py` – bull screener loads.
  - `test_ipo_view.py` – IPO tab loads.
  - `test_journal_view.py` – journal entry creation.
  - `test_alerts_api.py` – alert creation and triggering.
  - `test_kronos_view.py` – Kronos forecast display.
  - `test_sector_rotation_view.py` – sector rotation tab loads.

### Continuous Integration
- GitHub Actions (if present) runs `pytest` and Playwright on push/pull‑request.
- Coverage report uploaded to Codecov or similar.

### References
- `pytest.ini` – pytest configuration.
- `requirements.txt` – lists `pytest`, `playwright`, `pytest‑cov`, etc.
- `docs/` – any testing strategy documents.

---

## How to Use This Document for Node.js Migration

1. **Map Each Feature to a Service/Module**  
   For each section above, create a corresponding Node.js module (e.g., `services/epService.js`, `routes/ep.js`).

2. **Replicate Database Schema**  
   Use the schema definitions to create tables in your chosen DB (PostgreSQL/MongoDB). Consider using an ORM (Prisma/TypeORM) or knex.js for query building.

3. **Reimplement Core Algorithms**  
   Port the Python functions in `app/services/` and `app/utils/` to JavaScript/TypeScript. Pay special attention to:
   - EP scoring logic (`ep_service.py`).
   - Technical indicators (`technical.py`).
   - NLP enrichment (if retaining; otherwise, consider calling external APIs or using a lightweight JS NLP library like `compromise` or `natural`).

4. **Recreate API Endpoints**  
   Mirror the REST endpoints listed in the API Endpoints Overview. Use Express.js or Fastify. Ensure request validation (e.g., with `joi` or `zod`) and proper error responses.

5. **Rebuild Frontend (if keeping SPA)**  
   The existing frontend (HTML/Tailwind/Vanilla JS) can likely be reused unchanged if the Node.js backend provides the same API contract. Verify CORS headers and authentication (if added).

6. **Implement Background Jobs**  
   Replace APScheduler with node‑cron, Agenda, or BullMQ for job queues. Map each scheduler job to a Node.js equivalent.

7. **Maintain Test Coverage**  
   Write equivalent unit/integration tests using Jest/Vitest and E2E tests using Playwright (can reuse the existing test specs).

8. **Leverage Documentation**  
   The spec files in `docs/features/` provide detailed functional and non‑functional requirements—use them to write acceptance tests for the Node.js version.

---

## Conclusion

This document consolidates the major features, services, APIs, database schema, frontend architecture, and testing practices of the MomentumScan stock screener. It serves as a comprehensive reference for migrating the application to Node.js while preserving functionality and behavior.

*Generated on: 2026-07-09*  
*Source: Codebase review of the `stock-screener` repository.*