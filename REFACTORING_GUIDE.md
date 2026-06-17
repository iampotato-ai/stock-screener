# Stock Screener Application Refactoring Guide

## Current State Analysis

The `app.py` file has grown to approximately 378.5KB, indicating a monolithic structure that violates separation of concerns principles. Key issues include:

1. **Mixed Responsibilities**: Web routes, business logic, data access, and configuration are intertwined
2. **Difficult Navigation**: Finding specific functionality requires extensive searching
3. **Testing Challenges**: Unit testing is complicated due to tight coupling
4. **Scalability Limitations**: Adding new features increases complexity exponentially
5. **Team Collaboration Difficulties**: Merge conflicts likely when multiple developers work on different features

## Refactoring Goals

1. Separate concerns into distinct layers (presentation, business logic, data access)
2. Organize code by feature/domain rather than technical type
3. Improve testability through dependency injection and clear interfaces
4. Enhance maintainability with consistent patterns and conventions
5. Enable parallel development by reducing coupling between features
6. Preserve all existing functionality during refactoring

## Progress So Far

### Completed (Phase 1 - Foundation)
- ✅ Application factory pattern (`app/__init__.py`, `config.py`, `run.py`)
- ✅ Configuration management (`config.py`)
- ✅ NLP service encapsulation (`app/services/nlp_service.py`, `app/utils/helpers.py`, `app/utils/constants.py`)
- ✅ API blueprint structure (`app/api/v1/__init__.py`, `app/api/v1/announcements.py`)
- ✅ Verified endpoints work with fallback to keyword classification

### In Progress (Phase 2 - Core Services)
- ✅ Migrated watchlist business logic to service (`app/services/watchlist_service.py`)
- ✅ Created watchlist API blueprint (`app/api/v1/watchlist.py`) and EP watchlist API (`app/api/v1/ep_watchlist.py`)
- ✅ Migrated journal business logic to service (`app/services/journal_service.py`)
- ✅ Created journal API blueprint (`app/api/v1/journal.py`)
- ✅ Migrated market breadth business logic to service (`app/services/market_breadth_service.py`)
- ✅ Created market breadth API blueprint (`app/api/v1/market_breadth.py`)
- ✅ Migrated alert business logic to service (`app/services/alert_service.py`)
- ✅ Created alert API blueprint (`app/api/v1/alerts.py`)
- ✅ Migrated IPO business logic to service (`app/services/ipo_service.py`)
- ✅ Created IPO API blueprint (`app/api/v1/ipo.py`)
- ✅ Migrated news business logic to service (`app/services/news_service.py`)
- ✅ Created news API blueprint (`app/api/v1/news.py`)
- ✅ Migrated screener business logic to service (`app/services/screener_service.py`)
- ✅ Created screener API blueprint (`app/api/v1/screener.py`)
- ✅ Started migrating database helpers to `app/database.py`
- ⏳ Migrating database helpers and raw SQL queries to a data access layer
- ✅ Setting up background worker (APScheduler) using the NLP service singleton

### Planned (Phase 3 - Completeness)
- ✅ Created `app/database.py` with database helper functions for raw SQLite access
- ⏳ Completing model migration (all tables to `app/models.py` or using raw SQLite via `app/database.py`)
- ⏳ Migrating remaining utility functions to `app/utils/`
- ⏳ Adding environment-based configuration for external APIs and feature flags
- ⏳ Writing unit tests for service layer
- ⏳ Writing integration tests for API endpoints
- ⏳ Performance testing and optimization
- ⏳ Final cleanup and switch over to new factory

## Proposed Directory Structure (Updated)
```
stock-screener/
│
├─ app.py                      # Kept for now, will be replaced by factory later
├─ run.py                      # New entry point using application factory
├─ config.py                   # Configuration management
│
├─ /app                        # Main application package
│   ├─ __init__.py             # Application factory
│   ├─ extensions.py           # Flask extensions (db teardown, NLP singleton)
│   ├─ models.py               # SQLAlchemy models (to be expanded)
│   ├─ database.py             # Database helper functions (get_db, close_db)
│   │
│   ├─ /api                    # REST API endpoints
│   │   ├─ __init__.py
│   │   └─ /v1                 # API versioning
│   │       ├─ __init__.py
│   │       ├─ announcements.py    # NLP processing endpoint
│   │       ├─ screener.py         # (to be created) market data and screening
│   │       ├─ watchlist.py        # (created) watchlist management
│   │       ├─ journal.py          # (created) trade journal
│   │       ├─ alerts.py           # (created) alert processing
│   │       ├─ ipo.py              # (created) IPO handling
│   │       ├─ news.py             # (created) news and corporate events
│   │       └─ market_breadth.py   # (to be created) market breadth indicators
│   │
│   ├─ /services               # Business logic layer
│   │   ├─ __init__.py
│   │   ├─ nlp_service.py        # NLP processing (completed)
│   │   ├─ watchlist_service.py  # (created)
│   │   ├─ screener_service.py   # (to be created)
│   │   ├─ journal_service.py    # (created)
│   │   ├─ alert_service.py      # (created)
│   │   ├─ ipo_service.py        # (created)
│   │   ├─ news_service.py       # (created)
│   │   └─ market_breadth_service.py  # (to be created)
│   │
│   ├─ /utils                  # Cross-cutting utilities
│   │   ├─ __init__.py
│   │   ├─ constants.py          # Central constants (NLP models, scores, etc.)
│   │   ├─ helpers.py            # All NLP/text processing functions (completed)
│   │   └─ exceptions.py         # (to be created)
│   │
│   └─ /tasks                  # Background tasks (APScheduler jobs)
│       └─ scheduler.py        # (to be created) uses nlp_service singleton
│
├─ /migrations                 # Flask-Migrate directory (if using Flask-Migrate)
│
├─ /tests                      # Test suite
│   ├─ unit/
│   └─ integration/
│
├─ /scripts                    # Utility scripts
│   └─ init_db.py
│
├─ instance/                   # Instance-specific config (not in version control)
│   └── config.py
│
└─ /requirements/
    ├─ base.txt
    ├─ development.txt
    ├─ production.txt
    └─ ml.txt                  # Optional: heavy NLP stack (transformers, torch)
```

## Migration Strategy (Phase-wise)

### Phase 1: Foundation (Completed)
1. Create application factory pattern
2. Move configuration to `config.py`
3. Extract NLP logic to `app/services/` and `app/utils/`
4. Set up API blueprint structure
5. Create `run.py` as new entry point
6. Verify NLP service works with fallback

### Phase 2: Core Services & API (Current)
1. **Create service classes** for each major feature:
   - Start with simpler modules (watchlist, journal)
   - Move business logic from `app.py` to service classes
   - Keep services free of Flask-specific objects; use dependency injection or `current_app` when needed
2. **Create API blueprints** for each feature:
   - Move route handlers to appropriate API modules
   - Update route handlers to call service layer
   - Use the `api_bp` object defined in `app/api/v1/__init__.py`
3. **Migrate database helpers**:
   - Move raw SQLite functions to `app/database.py`
   - Use Flask's `teardown_appcontext` for connection closing
4. **Set up background worker**:
   - Move APScheduler logic to `app/tasks/scheduler.py`
   - Initialize scheduler in app factory after extensions are ready
   - Use `extensions.nlp_service` for NLP processing in background jobs

### Phase 3: Completeness & Testing
1. **Complete model migration**:
   - Move all table definitions to `app/models.py` (or keep raw SQL in `app/database.py` if preferred)
   - Ensure relationships and constraints are preserved
2. **Centralize constants**:
   - Move remaining magic numbers/strings to `app/utils/constants.py`
   - Replace hard-coded URLs with values from `config.py`
3. **Add missing utilities**:
   - Create `app/utils/exceptions.py` for custom exceptions
   - Move any remaining helper functions to `app/utils/helpers.py`
4. **Testing**:
   - Write unit tests for service layer (they can run without Flask context)
   - Write integration tests using Flask's test client for API endpoints
   - Mock external APIs and NLP models in tests
5. **Performance & Optimization**:
   - Profile critical paths
   - Implement caching where appropriate (using Flask-Caching or similar)
   - Ensure lazy loading of heavy resources (like NLP models)
6. **Final Switch Over**:
   - Once all functionality is ported and tested, replace `app.py` with a thin wrapper that uses the factory:
     ```python
     # app.py (new)
     from app import create_app
     app = create_app()
     if __name__ == '__main__':
         app.run(host='0.0.0.0', port=5000, debug=True)
     ```
   - Remove the old monolithic blocks from the previous `app.py` (or keep it as backup)

## Benefits Achieved So Far
* **Separation of concerns** – Web Layer (API) ↔ Business Logic (Services) ↔ Data Access (Models/Database)
* **Reusability** – The NLP service can be imported anywhere (CLI job, background worker, another API endpoint) without pulling in Flask request/objects.
* **Maintainability** – Changes to NLP logic live in one place (`helpers.py` + `nlp_service.py`).
* **Scalability** – Adding new features follows the same pattern; teams can work on different services simultaneously.
* **Testability** – Services can be unit-tested in isolation; the factory pattern makes it easy to swap configurations (e.g., testing with an in‑memory SQLite DB).

## Specific Notes on NLP Service
- The NLP service is a singleton initialized at app startup via `app/extensions.nlp_service`
- Models are loaded lazily on first use (efficient for production)
- The service is safe to use in background workers (APScheduler) and request handlers without Flask context
- Falls back gracefully to keyword-based classification when NLP models are unavailable or fail
- Configuration-controlled via `NLP_MODELS_ENABLED` environment variable

## Immediate Next Steps
1. ✅ Completed screener migration following the established pattern:
   - Created `app/services/screener_service.py`
   - Created `app/api/v1/screener.py`
   - Migrated screener-related code from `app.py` to these new locations
   - Updated `app/api/v1/__init__.py` to import the screener module
   - Verified the new component works correctly
2. ✅ Set up the background worker scheduler:
   - Created `app/tasks/scheduler.py`
   - Initialized scheduler in `app/__init__.py` after extensions are ready
   - Uses `extensions.nlp_service` for NLP processing in the EP refresh job (placeholder - actual implementation may vary)
3. 🔄 Complete market breadth service migration (if not already done)
4. 🔄 Migrate database helpers and raw SQL queries to a data access layer (`app/database.py`)