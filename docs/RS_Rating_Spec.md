# Spec: RS Rating Column for Screener UI

## Objective
Add a new column **RS Rating** to the main screener table so users can see each stock’s Relative‑Strength percentile (0‑100) directly in the UI. The column must be:
- Present in the column‑dropdown, labeled **RS Rating**.
- Hidden by default, toggleable.
- Right‑aligned numeric values from the backend field `relative_strength_rating`.
- Sortable (ascending/descending) using the existing column‑sorting mechanism.
- Accompanied by a tooltip: *"Relative Strength percentile vs peers (0‑100). Higher is stronger."*

## Tech Stack
- Front‑end: Vanilla JavaScript (static/js/app.js), HTML (templates/index.html).
- Back‑end: Flask Python (`app/services/rs_service.py` already provides `relative_strength_rating`).

## Commands
- **Dev server**: `python run.py`
- **Run tests**: `pytest`
- **Lint**: `flake8 .`

## Project Structure
```
static/
    js/
        app.js                # Column configuration lives here
templates/
    index.html                # Screener table markup
app/
    services/
        rs_service.py          # Calculates relative_strength_rating
tests/
    unit/
        test_column_config.py # New unit test for column definition
    e2e/
        test_rs_rating_column.py # New Playwright test for UI toggle
```

## Code Style
```js
// Column definition example (matches existing style)
{
    id: 'relative_strength_rating',
    name: 'RS Rating',
    sortField: 'relative_strength_rating',
    isVisible: false,          // hidden by default
    align: 'right',
    canToggle: true,
    tooltip: 'Relative Strength percentile vs peers (0‑100). Higher is stronger.'
},
```
All objects in `masterColumnsConfig` use 4‑space indentation, trailing commas, single quotes.

## Testing Strategy
- **Unit**: Verify `masterColumnsConfig.overview` contains an entry with `id: 'relative_strength_rating'` and correct properties.
- **E2E (Playwright)**: Open the column dropdown, check the **RS Rating** checkbox, verify the column appears with numeric values for each row, and test sorting by clicking the header.
- Coverage target ≥ 90 % for new files; overall suite ≥ 85 %.

## Boundaries
- **Always**: Run the full test suite after changes; do not merge if any test fails.
- **Ask first**: Any change to the backend payload name or type.
- **Never**: Modify unrelated UI components, change CSS layout, or commit secrets.

## Success Criteria
1. Column appears in UI dropdown and can be toggled on/off.
2. When visible, column shows correct numeric RS values (0‑100) for each stock.
3. Sorting by the column works (ascending/descending).
4. All existing tests pass; new unit and e2e tests pass.
5. Spec file (`docs/RS_Rating_Spec.md`) is committed.
