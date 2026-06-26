# Spec: BMW M Design System for MomentumScan

## Objective
Apply the BMW M motorsport aesthetic to the MomentumScan stock screener UI. Replace the existing dark‑premium design (glass‑morphism, rounded corners, custom palette) with the BMW M system:
- Pure black canvas (`#000000`)
- White text (`#ffffff`) and grayscale surface tones
- Zero border radius for most UI elements (except circular icon buttons)
- UPPERCASE heavy headlines (font‑weight 700) and light body (weight 300)
- M‑tricolor accent (`#0066b1`, `#1c69d4`, `#e22718`) used only for brand highlights, never as button fills
- No photography anchors – depth comes from flat surfaces, 1‑px hairlines and the M stripe divider
- Font fallback: **Inter** (700/300) for headings and body; **Saira Condensed** may be used for occasional headline compression.

## Tech Stack
- Front‑end: HTML + CSS + JS (vanilla, Chart.js, lightweight‑charts)
- Backend: Python Flask (unchanged)
- Build/Test: `npm run build`, `npm test -- --coverage` (frontend assets), `pytest` (Python)
- No additional runtime dependencies required beyond existing ones.

## Commands
```bash
# Build front‑end assets (CSS/JS bundles)
npm run build

# Run UI unit tests (if any) and coverage
npm test -- --coverage

# Run Python test suite
pytest -q

# Lint front‑end CSS/JS
npm run lint -- --fix
```

## Project Structure (unchanged)
```
templates/          # Jinja HTML templates
static/css/         # Stylesheets (design‑tokens.css, style.css, …)
static/js/          # UI scripts
app/                # Flask server code
tests/              # Python tests
```

## Code Style (BMW M system)
- **CSS variables** (`design‑tokens.css`) replace the current palette with BMW M tokens:
```css
:root {
  /* Canvas & surface */
  --color-canvas: #000000;            /* pure black */
  --color-surface-card: #1a1a1a;      /* dark card */
  --color-surface-elevated: #262626;
  --color-surface-soft: #0d0d0d;

  /* Text */
  --color-on-canvas: #ffffff;        /* white on black */
  --color-on-dark: #ffffff;
  --color-body: #bbbbbb;             /* light gray for body copy */
  --color-muted: #7e7e7e;

  /* M‑tricolor */
  --color-m-blue-light: #0066b1;
  --color-m-blue-dark:  #1c69d4;
  --color-m-red:        #e22718;

  /* Spacing – 4px base unit */
  --space-xxs: 4px;
  --space-xs: 8px;
  --space-sm: 12px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 40px;
  --space-xxl: 64px;
  --spacing-section: 96px; /* between major bands */

  /* Rounded – zero everywhere */
  --radius-none: 0px;
  --radius-full: 9999px; /* circular icons */

  /* Typography */
  --font-heading: 'Inter', sans-serif; /* fallback for BMW Type */
  --font-body:    'Inter', sans-serif;

  --typography-display-xl:   var(--font-heading) 80px 700 1 0;    /* h1 */
  --typography-display-lg:   var(--font-heading) 56px 700 1.05 0; /* sub‑hero */
  --typography-display-md:   var(--font-heading) 40px 700 1.1 0;
  --typography-display-sm:   var(--font-heading) 32px 700 1.15 0;
  --typography-title-lg:     var(--font-heading) 24px 700 1.3 0;
  --typography-title-md:     var(--font-heading) 20px 400 1.4 0;
  --typography-title-sm:     var(--font-heading) 18px 400 1.4 0;
  --typography-label-uppercase: var(--font-heading) 14px 700 1.3 1.5px;
  --typography-body-md:      var(--font-body) 16px 300 1.5 0;
  --typography-body-sm:      var(--font-body) 14px 300 1.5 0;
  --typography-button:       var(--font-heading) 14px 700 1 1.5px;
  --typography-nav-link:     var(--font-heading) 14px 400 1.4 0.5px;
}
```
- **All UI components** (buttons, inputs, cards, chips, nav‑items) must reference the new CSS variables. Rounded corners: `border-radius: var(--radius-none)` except for circular icon buttons (`--radius-full`).
- **Remove glass‑morphism**: delete `glassmorphism.css` imports and any `backdrop-filter` rules. Replace with flat background colors defined above.
- **Hairline borders**: use `1px solid var(--color-body)` for dividers and table outlines.
- **M‑stripe divider**: a 4‑px high horizontal bar using the three tricolor stops (linear‑gradient). Add a utility class `.m-stripe-divider`.
- **Button styles** (example):
```css
.button-primary {
  background: var(--color-canvas);
  color: var(--color-on-canvas);
  border: 1px solid var(--color-on-canvas);
  border-radius: var(--radius-none);
  padding: var(--space-md) var(--space-lg);
  font: var(--typography-button);
  text-transform: uppercase;
  letter-spacing: 1.5px;
}
```
- **Uppercase enforcement**: `text-transform: uppercase;` on all headline and button text.

## Testing Strategy
- **Visual regression**: capture screenshots of key pages (Dashboard, Screener) before and after; diff to ensure only style changes.
- **CSS lint**: run `stylelint` on the CSS bundle.
- **Functional tests**: existing Jest/Playwright tests (if any) must still pass; UI interactions are unchanged, only styling.
- **Accessibility**: run `axe-core` on the rendered pages to verify WCAG 2.1 AA contrast (white on black meets >21:1).

## Boundaries
- **Always do**: Update only styling files (`design‑tokens.css`, `style.css`, component CSS). Do **not** modify any Python business logic.
- **Ask first**: Changing component class names that are referenced in JS (e.g., `.glass-panel`). If a rename is needed, confirm the change with the owner.
- **Never do**: Introduce new UI libraries, alter data fetching, remove existing tests.

## Success Criteria
- UI renders with a pure black background and white text throughout.
- All rounded corners are removed (except circular icons).
- Typography matches BMW M specs (weights, uppercase, letter‑spacing).
- M‑tricolor stripe appears only as a decorative divider and in the brand logo (if present).
- No glass‑morphism effects remain; background is flat.
- All existing functional tests (`npm test`, `pytest`) pass.
- Visual regression diff shows only CSS changes, no layout shifts that break content.

## Open Questions
- Do we keep the existing `logo-icon` SVG or replace it with an M‑styled logo? (If no, we leave it unchanged.)
- Should we rename the `.glass-panel` class to `.panel` for clarity, or keep it and just restyle? (Current plan: keep class name to avoid JS changes.)
- Any custom CSS utilities (`.grid-overlay`, `.glow-blob`) that rely on blur should be removed – confirm no scripts depend on them.

---
*Spec prepared by the assistant. Review and approve before implementation.*