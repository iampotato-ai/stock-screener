# Spec: Bull Snort Filter

## Objective
Implement the Bull Snort stock screener tab, background refresh task, and backend logic in MomentumScan. 
The Bull Snort is a 4-phase institutional accumulation and breakout filter:
- **Phase 1 (Prolonged Downtrend)**: Price was >= 10% below 200 DMA in the last 6 months, and 200 DMA slope is negative.
- **Phase 2 (Base Formation)**: Price has stopped falling (no new 20-day low in last 10 sessions) and is within 5% below the 200 DMA.
- **Phase 3 (Base Volume Accumulation Score)**: Dynamic 0–100 scoring based on local Volume Pivots and Volume Surges while price was below 200 DMA.
- **Phase 4 (Bull Snort Candle Breakout)**: Today's candle has volume >= 3x its 20-day average, is a positive close, and closes in the top 35% of its daily range.

Success looks like a fully functional backend service, REST API supporting both single and universe-wide screenings, a daily APScheduler job caching the results, and a polished premium UI tab.

## Tech Stack
- **Backend**: Flask (Python 3.14+), SQLite (scan_history.db), SQLAlchemy
- **Scheduling**: APScheduler (BackgroundScheduler)
- **Frontend**: Vanilla HTML5, Vanilla CSS, Vanilla JavaScript (integrated into app.js and style.css)

## Commands
- **Run dev app**: `python run.py`
- **Run tests**: `python -m pytest` or `pytest`
- **Run coverage**: `pytest --cov=app`

## Project Structure
- `app/services/bull_snort_service.py` -> Math calculations, Phase 1-4 logic, and screening
- `app/api/v1/bull_snort.py` -> REST API endpoints (`/api/bull_snort/single` and `/api/bull_snort/screen`)
- `app/tasks/scheduler.py` -> Daily background refresh job
- `config.py` -> Configuration of feature flags (`ENABLE_BULL_SNORT`)
- `templates/index.html` -> UI markup (tab button and view section)
- `static/js/app.js` -> UI interaction, API calls, dynamic table generation
- `static/css/style.css` (or `templates/index.html` style section) -> Styling for the Bull Snort views

## Code Style
Matches existing repository guidelines: type hints, docstrings, snake_case for functions, PascalCase for classes, clean separation between view and service layer.
Example:
```python
def screen_bull_snort(
    symbols: list[str],
    vol_avg_period: int = 20,
    vol_surge_min: float = 3.0,
    close_position_min: float = 0.65,
    min_gap_history: float = 10.0,
    max_current_gap: float = 5.0,
) -> list[dict]:
    # ...
```

## Testing Strategy
- Unit tests live under `tests/unit/test_bull_snort_service.py`, `tests/unit/test_bull_snort_service_helpers.py`, and `tests/unit/test_bull_snort_api.py`.
- Ensure tests verify edge cases (insufficient data, rising DMA, etc.) and mock out external pricing calls (`fetch_historical_prices`).
- Expected coverage is >= 85% for service and helper code.

## Boundaries
- **Always do**: Gate all actions (API endpoints, scheduler jobs) behind `ENABLE_BULL_SNORT` feature flag.
- **Ask first**: Making changes to shared technical calculation utility modules (e.g. `app.utils.technical`).
- **Never do**: Run background scheduler jobs in testing environment/pytest runs (gated by `TESTING` flag).

## Success Criteria
1. `/api/bull_snort/screen` supports `GET` (screens the entire NSE universe using query parameters) and `POST` (screens the JSON-provided list of symbols).
2. `ENABLE_BULL_SNORT` is a central configuration flag in `config.py` that defaults to `False`.
3. APScheduler daily job triggers at 16:05 (Asia/Kolkata timezone) to run the screen and cache results to `current_app.config['BULL_SNORT_CACHE']`.
4. UI includes a new workspace tab "🐂 Bull Snort" with a customized run screen filter panel, status count, and detailed metrics table matching the premium dark mode aesthetic.
5. All 129+ unit and integration tests continue to pass successfully.

## Open Questions
- Should the daily scheduler cache be persisted in SQLite, or is the in-memory Flask config dictionary (`current_app.config['BULL_SNORT_CACHE']`) sufficient? (Assume Flask config dictionary for now, following `BULL_SNORT_FILTER.md`).
