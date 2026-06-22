# Repository Guidelines

## Project Overview
MomentumScan is a Flask‑based stock screener for the NSE (India). It aggregates data from TradingView, Google News, Yahoo Finance, and proprietary NLP pipelines to provide swing‑ and intraday‑momentum signals, live market‑breadth dashboards, ensemble model forecasts, and an AI‑augmented watchlist.

## Architecture & Data Flow
- **Client (frontend)** → HTTP/JSON → Flask app
- **Flask app** registers the versioned ``api/v1`` blueprint and delegates to the **service layer**.
- **Service layer** (`app/services/*`) contains pure Python business logic; it queries **SQLAlchemy models** (`app/models.py`) or uses low‑level SQLite helpers for legacy paths.
- **Background scheduler** (`app/tasks/scheduler.py`) runs periodic EP refreshes, IPO updates, model training, and warm‑up tasks via APScheduler.
- Data flows back to the client as JSON responses.

## Key Directories
- `app/` – core Flask package (factory, extensions, models, services, utils, API, tasks).
- `app/api/v1/` – versioned REST endpoints.
- `app/services/` – business‑logic modules (watchlist, EP, screener, IPO, NLP, alerts, etc.).
- `app/utils/` – technical helpers (technical‑indicator calculations, forecasting, FX conversion, etc.).
- `app/extensions.py` – Flask extensions (SQLAlchemy, etc.).
- `app/tasks/` – APScheduler jobs.
- `static/` – vanilla CSS/JS assets.
- `templates/` – Jinja2 HTML templates (e.g. `index.html`).
- `tests/` – pytest unit, integration and performance tests.
- `e2e/` – Playwright end‑to‑end tests.
- `scripts/` – maintenance utilities (`verify_migration.py`, `run_performance_tests.py`, `train_ep_scoring_model.py`).
- `docs/` – design/specification documents and implementation plans.

## Development Commands
```bash
# Install runtime dependencies
pip install -r requirements.txt

# Run the app locally (dev mode)
python run.py

# Run unit / integration test suite
pytest

# Run coverage (target ≥85 % for services, ≥90 % for EP inference)
pytest --cov=app

# Execute performance benchmarks
python scripts/run_performance_tests.py

# Verify migrated API endpoints (sanity check)
python scripts/verify_migration.py

# Train the EP scoring model (placeholder implementation)
python scripts/train_ep_scoring_model.py [--dry-run]

# Run Playwright end‑to‑end suite (headless by default)
python -m pytest -q e2e/tests/*.py
``` 

## Code Conventions & Common Patterns
- **Application Factory** (`create_app`) enables multiple contexts (dev, testing, CI). 
- **Blueprint versioning** (`api/v1`) keeps routes modular and extensible. 
- **Service‑layer separation**: thin Flask view functions delegate to `app/services/*` classes that contain type‑annotated methods, explicit `db.session.commit()` handling, and raise `ValueError` for validation errors.
- **SQLAlchemy ORM** is the primary persistence mechanism; raw SQLite helpers are only used for legacy routes. 
- **Configuration** (`config.py`) provides four subclassed configs (`DevelopmentConfig`, `ProductionConfig`, `TestingConfig`, `PytestConfig`) with environment‑variable defaults for `SECRET_KEY`, `DATABASE_URL`, feature flags, and model paths.
- **Feature flags** (`ENABLE_BACKGROUND_TASKS`, `ENABLE_TELEGRAM_ALERTS`, `ENABLE_NLP_ENRICHMENT`) are toggled via env vars without code changes. 
- **Logging** uses Python's `logging` module with a rotating file handler; `LOG_TO_STDOUT` forces console output in dev. 
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes. 
- **Type hints & docstrings** are present on public APIs. 
- **Thread‑safe background jobs** use `threading.Lock` (`refresh_lock`, `ep_refresh_lock`) to guard shared state.
- **Async patterns** are limited to thread pools (e.g., forecasting workers) to avoid GIL‑related issues. 
- **Dependency injection** is performed via Flask extensions (`db`) and explicit imports; services avoid holding Flask globals.

## Important Files
- `run.py` – canonical entry point (`create_app` → `app.run`).
- `app/__init__.py` – factory, error handlers, logging, blueprint registration.
- `app/config.py` – central configuration module with env‑driven defaults.
- `app/models.py` – SQLAlchemy model definitions (User, WatchlistItem, EpWatchlist, etc.).
- `app/extensions.py` – `db = SQLAlchemy()` and init helper.
- `app/services/watchlist_service.py`, `ep_service.py`, `screener_service.py`, … – core business logic.
- `app/api/v1/*.py` – REST endpoint definitions.
- `app/tasks/scheduler.py` – APScheduler setup and background jobs.
- `requirements.txt` – pinned Python dependencies (Flask, Flask‑SQLAlchemy, APScheduler, pandas, torch, transformers, xgboost, playwright, etc.).
- `pytest.ini` – pytest configuration (`testpaths = tests`).
- `scripts/verify_migration.py`, `run_performance_tests.py`, `train_ep_scoring_model.py` – utility scripts.
- `docs/` – specifications (`frontend_hero_spec.md`, `features/*`), design plans (`superpowers/*`), and ADRs.
- `e2e/tests/` – Playwright test suite covering home page, dashboard, EP, Screener, Watchlist, IPO, RRG views.

## Runtime/Tooling Preferences
- **Python 3.8+** runtime.
- **Package manager**: `pip` with a `requirements.txt` lockfile.
- **Database**: SQLite (`scan_history.db`) for development; can be swapped via `DATABASE_URL`.
- **Background jobs**: APScheduler running in-process threads.
- **Frontend**: vanilla HTML/CSS/JS; no bundler required.
- **E2E testing**: Playwright (Python sync API). Install via `pip install playwright && playwright install`.
- **Logging**: configurable to stdout or rotating file via `LOG_TO_STDOUT`.

## Testing & QA
- **Framework**: `pytest` (configured by `pytest.ini`).
- **Unit / integration tests** live under `tests/`; fixtures in `tests/conftest.py` provide a temporary SQLite DB and a Flask app instance in `TESTING` mode.
- **Coverage expectations**: ≥ 85 % for service APIs, ≥ 90 % for EP scoring inference code.
- **Special utilities**: global `sqlite3.connect` mock redirects to per‑test DB; extensive use of `unittest.mock.patch` for external I/O (HTTP calls, data fetches).
- **Performance tests** (`tests/unit/test_screener_service_performance.py`) assert acceptable latency for repeated service calls.
- **Playwright E2E tests** (`e2e/tests/*.py`) verify that each workspace view loads, key UI elements (tabs, badges, tables) are visible, and navigation works.
- **Running all checks**:
  ```bash
  pytest && python -m pytest -q e2e/tests/*.py
  ```
- **Accessibility**: `axe‑core` integration in Playwright specs (not shown here) ensures WCAG AA compliance.

*The repository follows a classic Flask‑MVC‑like separation with clear service boundaries, environment‑driven configuration, and a solid automated test suite covering unit, integration, performance, and UI levels.*