# Spec: Fix Watchlist Checkbox Add and Notifications

## Objective
Fix the bulk "Add Selected to Watchlist" action from the Screener checkboxes, which is currently broken due to HTML attribute quoting syntax errors. Additionally, replace intrusive native `alert()` calls with modern, non-blocking toast notifications using the app's existing `showToast` system, ensuring users are notified of successful additions for both bulk and single additions.

## Tech Stack
- Frontend: Vanilla HTML, CSS, JavaScript (running in browser)
- Backend: Flask (Python 3.12/3.14), SQLite database, SQLAlchemy ORM

## Commands
- **Dev Server**: `py run.py` (Runs on `http://127.0.0.1:5000`)
- **Watchlist Integration Tests**: `py -m tests.test_watchlist`

## Project Structure
- `static/js/app.js` — Client-side JavaScript containing the UI event handling and fetch calls.
- `app/api/v1/watchlist.py` — Flask blueprint routes for watchlist operations.

## Code Style
Event handlers should be registered programmatically on dynamically created elements rather than using inline HTML event handler strings that require double-quote escaping.
```javascript
// Good
const menuItem = document.createElement('div');
menuItem.className = 'floating-menu-item';
menuItem.addEventListener('click', (e) => {
    e.stopPropagation();
    addMultipleStocksToSection(sec.id, tickersArray);
    menu.remove();
});

// Bad
html += `<div class="floating-menu-item" onclick="addMultipleStocksToSection('${sec.id}', ${JSON.stringify(tickersArray)})">...</div>`;
```

## Testing Strategy
- **Manual Verification**: Run a scan in the Screener, check checkboxes, verify that "Add Selected to Watchlist" lists the sections, and clicking a section adds the selected stocks without javascript syntax errors. Verify that a success toast is shown.
- **Unit/Integration Tests**: Run the Python script `tests.test_watchlist` to verify that the backend API continues to work correctly.

## Boundaries
- **Always**: Use programmatic event listeners (`addEventListener`) for dynamically generated DOM elements.
- **Always**: Use the existing `showToast(message, type)` function for user feedback.
- **Never**: Introduce inline `onclick="..."` with JSON-stringified payloads that can break quoting.

## Success Criteria
1. Selecting multiple stocks in the screener and clicking "+ Add Selected to Watchlist" works correctly and adds the stocks to the selected watchlist section in the DB.
2. An elegant toast notification is shown to the user upon successfully adding stocks (both for bulk selection addition and single stock addition).
3. Under no circumstances should javascript syntax errors (like `SyntaxError: Unexpected end of input`) occur when clicking a section in the dropdown menu.

## Open Questions
- None.
