# Repository Guidelines

## Project Overview
MomentumScan is a Flask‑based stock screener for the NSE (India) that provides swing‑ and intraday‑momentum signals, live market‑breadth dashboards, ensemble model forecasts, and an AI‑augmented watchlist. The backend aggregates data from TradingView, Google News, Yahoo Finance, and proprietary NLP pipelines.

## Architecture & Data Flow
- **Flask app** (`app/__init__.py`) creates the application via the factory pattern and registers the API blueprint (`app/api/v1`).
- **API layer** (`app/api/v1/*.py`) exposes REST endpoints (e.g. `/api/v1/breadth-latest`, `/api/v1/watchlist`). Requests are handled by service classes in `app/services/`.
- **Service layer** (`app/services/*.py`) contains business logic, calls the SQLAlchemy models (`app/models.py`) and performs technical calculations in `app/utils/`.
- **Persistence** uses SQLite (`scan_history.db`) via Flask‑SQLAlchemy (`app/extensions.py`).
- **Background scheduler** (`app/tasks/scheduler.py`) runs periodic scans and model forecasts.
- **Frontend** is a single‑page app served from `static/` and `templates/`, consuming the JSON API.
- **Data flow**: client → API → service → model/DB → service → API → client. Forecast generation may invoke the `model/` package (Kronos, Prophet, ARIMA).

## Key Directories
- `app/` – core Flask package (factory, models, services, utils, API blueprints, tasks, extensions).
- `app/api/v1/` – versioned REST endpoints.
- `app/services/` – business‑logic modules (e.g. `ep_service.py`, `watchlist_service.py`).
- `app/utils/` – technical helpers (technical indicators, pattern detection, forecasts).
- `tests/` – pytest suite covering API, services, models, and utility functions.
- `scripts/` – maintenance scripts (`verify_migration.py`, `run_performance_tests.py`).
- `docs/` – design/spec/plan markdown files and feature listings.
- `config.py` – configuration classes for development, production, testing.
- `run.py` – canonical entry point (`create_app` → `app.run`).

## Development Commands
```bash
# Install dependencies
pip install -r requirements.txt   # (requirements.txt not present; use the README list)

# Run the development server
python run.py   # or `py run.py`

# Run the test suite
pytest               # discovers `tests/` per pytest.ini

# Verify migration endpoints (scripts/verify_migration.py)
python scripts/verify_migration.py

# Run performance benchmark
python scripts/run_performance_tests.py
```
*Linting/formatting*: not defined in repo – adopt `flake8`/`black` locally.

## Code Conventions & Common Patterns
- **Naming**: snake_case for functions/variables, PascalCase for classes.
- **Flask factory** in `app/__init__.py` with `create_app(config_name)`.
- **SQLAlchemy models** inherit from `BaseModel` providing `to_dict`/serialization.
- **Error handling** via `register_error_handlers` in `app/__init__.py`.
- **Background tasks** scheduled with APScheduler (`app/tasks/scheduler.py`).
- **Configuration** via environment variables with sensible defaults in `config.py`.
- **Dependency injection** – extensions (`db`) are initialized in `init_extensions` and injected into the app.
- **Async patterns**: long‑running forecasts executed in separate threads limited to 8 workers (`ep_service.py`).
- **Logging**: production logging to stderr; rotating file handler in `app/__init__.py`.

## Important Files
- `README.md` – high‑level description and feature list.
- `config.py` – config class hierarchy (`DevelopmentConfig`, `ProductionConfig`, `TestingConfig`).
- `app/__init__.py` – factory, blueprint registration, error handlers.
- `app/models.py` – core SQLAlchemy models (User, WatchlistItem, ScanHistory, Forecasts, etc.).
- `app/extensions.py` – Flask extensions (SQLAlchemy).
- `run.py` – entry point for `flask run`.
- `pytest.ini` – pytest configuration (testpaths = tests).
- `scripts/verify_migration.py` – sanity‑check for migrated API endpoints.

## Runtime/Tooling Preferences
- **Language**: Python 3.8+.
- **Package manager**: `pip` (virtual environment recommended).
- **Web server**: Flask development server for local work; production should use a WSGI server (e.g. gunicorn).
- **Database**: SQLite (`scan_history.db`) – file‑based, no external DB required.
- **ML libraries**: `torch`, `transformers`, `prophet`, `statsmodels` for ensemble forecasts.
- **Static assets**: vanilla JavaScript/CSS under `static/` (no Node/Bun build step).

## Testing & QA
- **Framework**: `pytest` (discovering files matching `test_*.py` under `tests/`).
- **Run all tests**: `pytest` from repository root.
- **Key test modules**: `test_ep_screener.py`, `test_market_breadth.py`, `test_alert_service.py`, `test_database.py`, etc., covering API endpoints, service logic, and database interactions.
- **Smoke test**: `smoke_test.py` provides a quick sanity check.
- **Coverage**: not configured; add `--cov=app` to pytest command for coverage reporting if needed.
