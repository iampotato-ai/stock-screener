# Spec: Remove AI Forecast Tab

## Objective
Remove the "AI Forecast" workspace tab and associated workspace views (`#view-ai-forecast`) from the client user interface, as it is no longer being actively used by the user. Decommission all frontend hooks while keeping the backend models and forecast APIs intact to prevent breaking backend test suites, API contracts, and database integrity.

## Tech Stack
- Frontend: HTML5, CSS3, JavaScript (Vanilla), Lightweight Charts
- Backend: Flask web application, SQLAlchemy models

## Commands
- Run the dev server: `python run.py`
- Run unit/integration tests: `python -m pytest`
- Run Playwright E2E tests: `python -m pytest -q e2e/tests/*.py`

## Project Structure
- `templates/index.html` → Primary workspace HTML template containing view containers.
- `static/js/app.js` → Main frontend routing, event bindings, and UI renders.
- `e2e/tests/` → Playwright automated UI flow verification tests.
- `app/api/v1/` → Flask versioned endpoints (unchanged to preserve compatibility).
- `app/utils/forecast_math.py` → Forecast algorithm (unchanged).

## Code Style
- Clean separation of concerns: No UI references in backend models.
- Inline styles are forbidden; layout and visuals must be controlled via stylesheet rules.
- Optional chaining (`?.`) or conditional presence checks must be used when querying elements that may be absent to prevent JavaScript crashes.

## Testing Strategy
- **Unit & Integration Tests**: Backend tests (such as integration forecast route tests) must remain fully functional and pass successfully.
- **E2E Tests**: Obsolete `e2e/tests/test_ai_forecast_view.py` will be removed. All other E2E tests must pass without any selector or navigation errors.

## Boundaries
- **Always**: Keep backend endpoints, math utilities, and database tables intact to maintain compatibility and pass existing integration tests.
- **Ask first**: Deleting any backend forecast calculations or models.
- **Never**: Leave dangling JS selectors that cause `TypeError` crashes when the elements are missing from the DOM.
- **Never**: Disable the forecasting features in the trader's drawer details panel (e.g. Kronos Forecast section inside the drawer should remain operational unless specified).

## Success Criteria
- The "AI Forecast" tab is completely removed from the workspace navigation bar.
- The `#view-ai-forecast` workspace panel is completely removed from the DOM.
- Switching workspaces, loading screens, and searching stocks function correctly without throwing console errors.
- All integration and unit tests pass.
- Playwright E2E tests (excluding the removed one) run and pass successfully.

## Open Questions
1. Do we want to keep the "Kronos Forecast" panel inside the trader's detail drawer (when clicking a ticker in other workspaces)? It currently fetches and displays the forecast there.
   - *Assumption*: Yes, keep it. Only remove the dedicated workspace view/tab.
2. Do we want to keep the "Consensus Conviction" background calculations running?
   - *Assumption*: Yes, they are background/API utilities. Keep them intact.
