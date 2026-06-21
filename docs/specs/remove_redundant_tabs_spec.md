# Spec: Remove Redundant Table Tabs

## Objective
Remove the redundant `Valuation`, `Quality`, and `Growth` tabs from the main screener table workspace (`#view-screener`), leaving only `Overview` and `R:R Setups`. This streamlines the layout since all fundamental, quality, and growth details are now fully aggregated and visible in the collapsible sections of the detail drawer card (the "trader's drawer").

## Tech Stack
- Frontend: HTML5, CSS3, JavaScript (Vanilla)
- Backend: Flask web application

## Success Criteria
- The tab bar (`#screener-tabs` inside `#view-screener`) displays only the `Overview` and `⚖️ R:R Setups` tabs.
- The `Valuation`, `Quality`, and `Growth` tabs are completely removed from the table list view, preventing clutter.
- The collapsible detail sections (Valuation, Quality, Growth) in the trader's drawer remain fully functional and default to being open and visible when opening a stock's detail drawer from either the `Overview` or `R:R Setups` view.
- The multi-sheet Excel export functionality is preserved and continues to include all 4 datasets (Overview, Valuation, Quality, and Growth) as it is highly valuable for offline analysis.
- No console errors are thrown when switching tabs, filtering, scanning, or opening the detail drawer.

## Proposed Changes

### [index.html](file:///c:/Users/91996/Documents/My%20Projects/stock-screener/templates/index.html)
- Remove the tab buttons for Valuation, Quality, and Growth from the `#screener-tabs` container.
- Update the asset version query string parameter to bust the cache (increment from `1.0.60` to `1.0.61`).

### [app.js](file:///c:/Users/91996/Documents/My%20Projects/stock-screener/static/js/app.js)
- Ensure all logic relating to the detail drawer remains fully intact and loads data successfully.
- Keep the `exportToExcel` function configured to export the detailed datasets for Overview, Valuation, Quality, and Growth tabs.

## Boundaries
- **Always:** Verify visual look and responsiveness on typical monitor sizes.
- **Never:** Break drop-down functionality, use inline styles, or delete necessary CSS wrapper properties.
- **Never:** Disable the data rendering/populating code for the detail drawer sections.
