# Spec: Bull Snort Screen Enhancements

## Objective
Enhance the Bull Snort screen workspace to improve usability by borrowing features from the EP Screener:
1. Add an **Active Watchlist** tab that shows bulls currently in the user's watchlist.
2. Make ticker names clickable, opening the corresponding TradingView chart in a new tab.
3. Add a **Rotation** tab (similar to EP screener's sector rotation view) to the Bull Snort workspace.
These changes aim to reduce context‑switching, provide quick access to relevant data, and give users more control over their view.

## Tech Stack
- **Backend:** Python Flask (existing `app/api/v1/bull_snort.py` endpoint)
- **Frontend:** HTML template (`templates/index.css` & inline styles in `templates/index.html`), JavaScript (likely in `static/js/app.js` or similar)
- **Styling:** Tailwind CSS (via existing `style.css`) with custom utility classes
- **Charting:** TradingView Lightweight Charts (already loaded)
- **Build/Run:** `python run.py` (Flask dev server)
- **Test:** Existing pytest suite; no new backend endpoints required for these UI changes.

## Commands
```
# Run the application locally (development)
python run.py

# Run the test suite
pytest

# Run a specific test (if needed)
pytest tests/unit/test_bull_snort_api.py -v

# Lint (if configured)
# (project may use flake8/black; adjust as needed)
flake8 .

# Format code (if configured)
black .
```

## Project Structure (relevant parts)
```
stock-screener/
├─ app/
│  ├─ api/
│  │   └─ v1/
│  │      ├─ bull_snort.py          # API endpoints for bull screener data
│  │      └─ … (other endpoint files)
│  ├─ services/
│  │   └─ bull_snort_service.py    # Business logic for bull screener calculations
│  ├─ models.py                    # SQLAlchemy models (if new DB fields needed)
│  └─ utils/
│      └─ technical.py             # Helper functions (price fetching, etc.)
├─ static/
│  ├─ js/
│  │   └─ app.js                   # Main frontend logic (if exists)
│  └─ css/
│      └─ style.css                # Tailwind‑generated stylesheet
├─ templates/
│  └─ index.html                   # Main SPA shell; contains workspace views
├─ tests/
│  ├─ unit/
│  │   └─ test_bull_snort_api.py   # Existing bull screener API tests
│  └─ … (other test files)
└─ docs/
   └─ features/
      └─ bull_snort_enhancements_spec.md  # this file
```

## Code Style
- **Python:** Follow PEP 8, use type hints where practical, keep functions small and focused.
  ```python
  def get_bull_snort_watchlist(user_id: int) -> List[Dict[str, Any]]:
      """Return bull screener rows for tickers in the user's watchlist."""
      ...
  ```
- **JavaScript/ES6:** Use `const`/`let`, arrow functions for callbacks, modularize with IIFE or ES modules if applicable.
  ```javascript
  const openTradingView = (symbol: string) => {
      window.open(`https://www.tradingview.com/chart/?symbol=${symbol}`, '_blank');
  };
  ```
- **HTML:** Use semantic elements where possible, keep inline styles to a minimum; rely on Tailwind classes.
  ```html
  <button class="btn btn-primary" onclick="openTradingView('RELIANCE')">
      RELIANCE
  </button>
  ```
- **CSS/Tailwind:** Extend `tailwind.config.js` for any new colors or spacing; avoid arbitrary values when possible.

## Testing Strategy
- **Unit Tests:** Test any new backend helper functions (e.g., watchlist filtering) with pytest; aim for ≥80% coverage on new code.
- **Integration Tests:** Verify that the new endpoints (if any) return correct JSON structure and status codes.
- **End‑to‑End (E2E):** Use existing Playwright suite to ensure:
  - The Bull Snort workspace loads without errors.
  - The “Active Watchlist” tab appears and shows data when the user has watchlist items.
  - Clicking a ticker opens a new tab/window to TradingView (can be validated by checking `window.open` call or navigating to a mock URL).
  - Rotation tab displays expected content (placeholder or actual data).
- **Manual QA:** Verify UI layout on common screen sizes (desktop, tablet, mobile) and ensure no overlapping elements.

## Boundaries
- **Always:**
  - Run existing test suite before committing; ensure no regressions.
  - Follow the existing code style (PEP8 for Python, consistent JS formatting).
  - Keep UI changes within the Bull Snort workspace only (do not modify other workspaces unless absolutely necessary).
  - Preserve backward compatibility: existing Bull Snort API responses should remain unchanged.
- **Ask First:**
  - Adding new backend endpoints or modifying existing ones (e.g., to fetch watchlist‑filtered data).
  - Introducing new JavaScript libraries or changing the build process.
  - Altering the global layout (header, nav, or sidebar) outside the Bull Schnort container.
- **Never:**
  - Commit secret keys, API tokens, or sensitive config files.
  - Remove or disable existing tests without explicit approval.
  - Break the existing navigation flow (e.g., removing the Bull Snort tab from the workspace nav bar).

## Success Criteria
- [ ] **Watchlist Tab:** A new tab labeled “Watchlist” appears in the Bull Snort workspace header alongside existing tabs (e.g., “Scanner”, “Settings”). Selecting it displays a table of bull screener results limited to tickers present in the user's watchlist (if any). If the watchlist is empty, a helpful empty‑state message is shown.
- [ ] **Clickable Ticker:** In all Bull Snort tables (Scanner, Watchlist, any other), the ticker symbol column is rendered as a clickable link/button that opens `https://www.tradingview.com/chart/?symbol=<TICKER>` in a new browser tab.
- [ ] **Rotation Tab:** A new tab labeled “Rotation” appears; selecting it shows a sector‑rotation style view (similar to the EP screener’s rotation tab) – at minimum, it should render a placeholder heading and a table or chart indicating sector strength/weakness for bull screens. The exact content can be defined later but must not break the layout.
- [ ] **Responsiveness:** All new controls and tabs render correctly and are usable at widths down to 320 px (mobile portrait). The layout does not overflow or require horizontal scrolling.
- [ ] **No Regression:** All existing Bull Snort functionality (scan, filters, export, snapshot, etc.) continues to work as before. All related unit and integration tests pass.
- [ ] **Code Quality:** New code follows the defined style guidelines, is appropriately commented, and does not introduce linting errors.

## Open Questions
1. **Data Source for Watchlist Filter:** Should the bull screener watchlist view reuse the existing `/bull_snort/screen` endpoint with an additional filter parameter (e.g., `watchlist=true`) that the backend resolves against the logged‑in user’s watchlist, or should we create a dedicated endpoint (e.g., `/bull_snort/watchlist`)? 
   - *Proposed approach:* Add a query parameter `watchlist=1` to the existing screen endpoint; the backend will intersect the screener universe with the user's watchlist tickers.
2. **Rotation Tab Content:** What specific data should the Rotation tab display? The EP screener shows sector rotation based on relative strength. For Bull Snort, we could show bull‑sector strength scores (e.g., average bull score per sector) or a simple table of sector → bull count. Need clarification on the desired metric.
3. **Access to TradingView:** Should we open the chart for the raw ticker (e.g., `RELIANCE`) or need to append exchange suffix (e.g., `NSE:RELIANCE`)? The existing TradingView links elsewhere in the app likely use the format `NSE:<symbol>`; we’ll adopt that unless told otherwise.
4. **UI Placement of New Controls:** Where should the Rotation tab live? Options:
   - Add it to the existing tab row (right‑most) alongside Scanner, Watchlist, etc.
   - Place it in a secondary toolbar (e.g., near the search/preset controls).
   - Use a dropdown menu for less‑frequently used items (Rotation).
   Suggest placing it in the tab row for immediate visibility, but open to feedback.