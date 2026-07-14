# MomentumScan - NSE India Stock Screener

A premium, high-performance Swing & Intraday Momentum stock screener for the National Stock Exchange of India (NSE). Powered by a lightweight Flask backend and an interactive single-page JS frontend, MomentumScan aggregates live data from TradingView, NSE announcements, bulk/block deals, corporate events, and Google News, integrating advanced deep learning predictions to deliver an institutional-grade trading dashboard.

## Project Status

✅ **Refactor Complete** – The application has been migrated from a monolithic `app.py` to a clean, layered architecture:
- **Presentation Layer** – Flask API blueprints (`/app/api/v1/`) and React‑style vanilla JS frontend.
- **Business Logic Layer** – Service classes (`/app/services/`) for each domain (screener, EP, bull‑snort, watchlist, journal, alerts, IPO, news, market breadth).
- **Data Access Layer** – SQLAlchemy models (`/app/models.py`) and helper functions (`/app/database.py`).
- **Background Processing** – APScheduler‑based worker (`/app/tasks/scheduler.py`) for nightly EP scoring, data refreshes, and NLP enrichment.
- **Configuration & Utilities** – Centralized config (`config.py`), constants, and helper modules (`/app/utils/`).
- **Testing** – Unit tests for services and integration tests for API endpoints.

The refactor ensures maintainability, testability, and scalability while preserving all existing functionality.

---

## ⚡ Key Dashboard Highlights

1. **Composite Market Regime Speedometer** – Live circular dial showing market sentiment (0‑100) derived from multi‑dimensional breadth signals.
2. **Sector Rotation Timeline (RRG)** – Interactive, animated 12‑week sector rotation on a custom canvas (Leading, Weakening, Lagging, Improving).
3. **Interactive Watchlist Center** – Drag‑and‑drop stock organizing, renameable sections, ex‑dates/announcements feed, bulk‑deal tracking, and **AI‑powered batch sorting** (Kronos‑driven with caching).
4. **TradingView Lightweight Charts** – Interactive candlestick charting inside the trade drawer & full‑screen overlay modals, with SMA overlays, volume histograms, and client‑side pattern detection.
5. **EnsembleCast Multi‑Model Predictor** – Combines **Kronos‑small** (deep‑learning time‑series), **Meta Prophet**, and **ARIMA** forecasts using a rolling MAPE‑weighted ensemble.
6. **🚀 IPO Momentum Hub** – Real‑time screening of recent NSE/BSE mainboard listings with dynamic phase tracking (**HOT**, **STABLE**, **FADING**, **BROKEN**).
7. **⛺ Stage 2 Camp Setup Detector** – Automatic detection of post‑breakout consolidation patterns (tight range, low volume) preceding potential breakouts.
8. **📈 Institutional Volume Alerts** – Color‑coded volume bars:
   - **Blue Bar** – Institutional accumulation (price up & volume > max down‑volume of last 10 down‑days).
   - **Green Bar** – Above‑average volume (price up & volume > 50‑day volume SMA).
   - **Orange Bar** – Supply dry‑up (volume ≤ 20 % of 50‑day SMA).
9. **🔔 Smart Alert Engine** – Continuous client‑side background monitoring for:
   - Regime score jumps ≥15 points
   - Swing score flips (weak → strong)
   - Kronos forecast spikes (>5 % expected 5‑day move)
   - Bulk/block deal detections
   Delivered via browser push notifications and an in‑app log panel.
10. **⚡ Keyboard Navigable Cockpit** – `↑`/`↓`/`Enter`/`W` for tray navigation, plus full ARIA keyboard support for all interactive components.
11. **Advanced Risk‑Calculator Drawer** – Computes target exits, position size, stop‑loss, and risk‑reward ratios based on current market conditions.
12. **Trade Log Journal** – Persistent SQLite journal with trade performance stats (PnL, win rate, average R) and automatic migration from `localStorage`.

## 🛠️ Recently Added Features

### Bull Snort – Institutional Accumulation & Breakout Filter
A proprietary four‑phase scanner that identifies stocks showing:
- Prior downtrend with a depressed 200‑day DMA  
- Base formation (no new lows, price near DMA)  
- Significant volume accumulation during the base (pivots & surges)  
- A breakout candle with strong volume and close in the upper part of the range  

Implemented in **`app/services/bull_snort_service.py`** and gated by the `ENABLE_BULL_SNORT` flag.

### Episodic Pivot (EP) Screener Module
Full implementation of the EP strategy for Indian markets, comprising:
- Nightly computation of neglect, catalyst, and repricing scores  
- EP watchlist with 20‑session tracking and trigger detection (red‑to‑green, range breakout, reclaim)  
- Sugar‑babies list for historic EP runners  
- Dedicated API endpoints under `/api/v1/ep/*` and detail views in the UI.

### UI/UX Refinements (Design System)
- **Conviction Badges** (HIGH/MODERATE/LOW) for prediction confidence.  
- **Glass‑Panel** containers with background‑blur and subtle shadows for premium depth.  
- **Filter Chips** and **enhanced input focus/hover states**.  
- Updated colour palette, typography, and spacing tokens (see `DESIGN.md`).  
- Accessibility improvements: keyboard navigation, focus‑visible outlines, ARIA labels, WCAG‑AA contrast compliance.

### Performance & Reliability
- Caching layers for EP scores, fundamentals, and NLP results to reduce redundant API calls.  
- Background data refresh cooldowns (60 s) to avoid excessive external requests.  
- Comprehensive test suite (>150 unit/integration tests) with CI‑ready configuration.  
- Docker‑ready `Dockerfile` (optional) and `docker‑compose.yml` for quick spin‑up.

---

## 📂 Project Structure (post‑refactor Overview

### Documentation
- [Feature Overview](docs/FEATURES_OVERVIEW.md)
- [Migration Feature Guide](docs/migration_features_guide.md)

```
stock-screener/
│
├─ app.py                     # Thin wrapper: from app import create_app; app = create_app()
├─ run.py                     # Preferred entry point using the application factory
├─ config.py                  # Environment‑based configuration (dev/prod/test)
│
├─ /app                       # Main application package
│   ├─ __init__.py           # Application factory & extension registration
│   ├─ extensions.py         # Flask extensions (SQLAlchemy, teardown, NLP singleton)
│   ├─ models.py             # SQLAlchemy models for all domain entities
│   ├─ database.py           # Helper functions for raw SQLite access (used by services)
│   │
│   ├─ /api                  # REST API
│   │   ├─ __init__.py       # Defines api_bp Blueprint
│   │   └─ /v1               # API version 1
│   │       ├─ announcements.py
│   │   ├─ alerts.py
│   │   ├─ ep.py
│   │   ├─ ep_watchlist.py
│   │   ├─ ipo.py
│   │   ├─ journal.py
│   │   ├─ market_breadth.py
│   │   ├─ news.py
│   │   ├─ screener.py
│   │   └─ watchlist.py
│   │
│   ├─ /services             # Business logic layer
│   │   ├─ alert_service.py
│   │   ├─ bull_snort_service.py
│   │   ├─ ep_service.py
│   │   ├─ ipo_service.py
│   │   ├─ journal_service.py
│   │   ├─ market_breadth_service.py
│   │   ├─ news_service.py
│   │   ├─ screener_service.py
│   │   └─ watchlist_service.py
│   │
│   ├─ /tasks                # Background workers (APScheduler)
│   │   └─ scheduler.py
│   │
│   └─ /utils                # Cross‑cutting utilities
│       ├─ constants.py
│       ├─ helpers.py        # NLP/text processing helpers
│       └─ exceptions.py
│
├─ /tests                    # Test suite
│   ├─ unit/
│   └─ integration/
│
├─ /docs                     # Design specs, architecture decisions, feature specs
│
├─ /scripts                  # Utility scripts (e.g., model training, DB migrations)
│
├─ requirements/
│   ├─ base.txt
│   ├─ development.txt
│   ├─ production.txt
│   └─ ml.txt                # Optional heavy NLP stack (transformers, torch)
│
├─ .env                      # Environment variables (not committed)
├─ .gitignore
└─ README.md
```

---

## 🚀 Setup & Run Instructions

### Prerequisites
- **Python 3.8+** (recommended 3.11)
- **Git**
- (Optional) **Docker & Docker‑Compose** for containerized deployment

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/stock-screener.git
cd stock-screener
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements/development.txt
```
*For production:*  
```bash
pip install -r requirements/production.txt
```
*If you need the full NLP/ML stack (Kronos, Prophet, transformers, etc.):*  
```bash
pip install -r requirements/ml.txt
```

### 4. Configure Environment
Copy `.env.example` to `.env` and adjust values:
```bash
cp .env.example .env
# Edit .env with your API keys (NEWS_API_KEY, etc.) and feature flags:
ENABLE_BULL_SNORT=true
ENABLE_NLP_MODELS=true
```
See `config.py` for all available options.

### 5. Initialise the Database
```bash
flask db upgrade   # if using Flask‑Migrate, otherwise the app creates tables on first run
```
*The application will automatically create `scan_history.db` in the instance folder on startup.*

### 6. Run the Application
**Development (with auto‑reload):**
```bash
flask run   # or: python run.py
```
**Production (using Gunicorn):**
```bash
gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
```

### 7. Access the Dashboard
Open your browser to **http://127.0.0.1:5000**

### 8. Run Tests
```bash
# Unit tests
pytest tests/unit/
# Integration tests
pytest tests/integration/
# All tests
pytest
```

---

## 📚 Documentation & Further Reading

- **[Design Guide](DESIGN.md)** – Colour palette, typography, spacing, component specifications.
- **[Product Vision](PRODUCT.md)** – Target audience, use‑cases, and anti‑references.
- **[Refactor Guide](REFACTORING_GUIDE.md)** – Detailed walk‑through of the migration from monolith to layered architecture.
- **[API Reference]** – Auto‑generated via Swagger/OpenAPI (launch the app and visit `/apidocs` if enabled).
- **[Deployment Guide](DEPLOYMENT.md)** – Docker, Gunicorn, Nginx, and systemd instructions (if present).

---

## � acknowledgments

- Data sources: NSE, BSE, TradingView, screener.in, Yahoo Finance, Google News.
- Open‑source libraries: Flask, SQLAlchemy, TA‑Lib, Prophet, Kronos (via HuggingFace), Pandas, NumPy, Chart.js/Lightweight Charts.
- Inspired by the episodic pivot methodology of Pradeep Bonde and institutional volume‑price concepts from traders such as Stan Weinstein.

---

**Happy trading!** 🚀  
*Maintained by the open‑source community – contributions welcome via pull requests.*