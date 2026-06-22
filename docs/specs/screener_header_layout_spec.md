# Spec: Screener Header Fluid Layout

## Objective
Re-layout the primary screener controls (`.screener-header-primary`) to use a fluid, wide layout. The search box will stretch dynamically to utilize the banner's horizontal space, the sector and preset filter dropdowns will sit next to it, and the "Scan Now" button will always align to the far right end of the banner.

This eliminates empty blank space by expanding the search input box while keeping the primary action button ("Scan Now") prominently positioned on the right.

## Tech Stack
- Frontend: HTML5, CSS3 (Vanilla)
- Platform: Flask web application

## Success Criteria
- The "Scan Now" button is always aligned to the far right end of the banner container.
- The search input box (`.search-box`) is fluid and stretches (`flex-grow: 1` with `max-width` increased to `700px` or `none` depending on screen size) to consume the available horizontal space.
- The layout is responsive: on smaller screens, controls wrap naturally without overlapping or overflowing the container.
- Spacing between individual controls is maintained at a consistent `0.75rem`.

## Proposed Changes
Modify [style.css](file:///C:/Users/91996/Documents/My%20Projects/stock-screener/static/css/style.css):
- Revert `.screener-header-primary` to use `justify-content: space-between` to force the "Scan Now" button to the far right.
- Re-enable `flex: 1` on `.screener-header-primary-left` so the left controls container stretches.
- Update `.search-box` to have `max-width: 650px` (or `none`) so it expands into the empty space.

## Boundaries
- **Always:** Verify visual look and responsiveness on typical monitor sizes.
- **Never:** Break drop-down functionality, use inline styles, or delete necessary CSS wrapper properties.
