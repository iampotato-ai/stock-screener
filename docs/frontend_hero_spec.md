# Spec: MomentumScan Front‑end Hero Page

## Objective
- **What**: Deliver a distinctive, data‑driven hero section for the MomentumScan dashboard that showcases the “Top‑5 Momentum Picks today”.
- **Why**: Traders need an at‑a‑glance signal of the most active stocks; the hero must be instantly recognizable and reinforce the brand’s visual identity.
- **User Stories / Acceptance Criteria**
  1. As a trader, I see a prominent headline that reflects the strongest momentum magnitude.
  2. As a trader, I can hover over each ribbon segment to view ticker, price, and % change.
  3. As a trader, the CTA button navigates to the full scan view.
  4. The hero works responsively on desktop (≥1024 px) and mobile (≤480 px).
  5. The design adheres to the specified palette, typography, and the **Momentum Ribbon** signature element.

## Tech Stack
- **Backend**: Flask (Python 3.8+), exposing `/api/v1/top-momentum` JSON endpoint.
- **Frontend**: Vanilla HTML5, CSS3 (custom properties), SVG + minimal JavaScript (ES6).
- **Build / Dev**: No bundler required; static assets served from `static/`. Development server via `python run.py` (Flask factory).
- **Testing**: Pytest for API, Playwright for visual regression of the hero.

## Commands
```
# Run development server (auto‑reload)
python run.py

# Run unit tests (API + backend)
pytest

# Run visual regression test for the hero (Playwright)
npx playwright test tests/e2e/hero.spec.ts

# Lint Python code
flake8 .
```
*(Front‑end assets are plain files; linting via stylelint optional.)*

## Project Structure
```
app/                     # Flask package
  ├─ __init__.py        # create_app factory
  ├─ api/v1/            # REST blueprints
  ├─ services/           # business logic
  ├─ extensions.py
static/                   # Front‑end assets
  ├─ css/                # custom stylesheet (hero.css)
  ├─ js/                 # small JS modules (hero.js)
  ├─ img/                # optional images
templates/                # Jinja templates (index.html)

docs/                     # documentation
  └─ frontend_hero_spec.md  # ← this spec

tests/                    # pytest unit tests
  └─ test_api_top_momentum.py

e2e/                     # Playwright end‑to‑end tests
  └─ hero.spec.ts
```

## Code Style
- **HTML**: Semantic tags (`section`, `header`, `button`). Indent 2 spaces. Self‑close empty elements.
- **CSS**: Use CSS custom properties for palette (`--navy`, `--gold`, …). BEM‑style class naming (`hero__copy`, `hero__ribbon`). No IDs.
- **JS**: ES6 modules, `const`/`let`, arrow functions, no implicit globals. Prefer `fetch` with async/await.
- **Python**: PEP‑8, type hints, `black` formatting.

*Example snippet (hero.css)*
```css
:root {
  --navy: #0B1D2F;
  --gold: #F2C94C;
  --red:  #FF6B6B;
  --azure:#3AB0FF;
  --paper:#F5F5F5;
}
.hero {display:flex;gap:2rem;align-items:center;background:var(--navy);color:var(--paper);}
.hero__title{font-family:"Vollkorn SC",serif;color:var(--gold);}
```

## Testing Strategy
- **Unit**: `pytest` covers API endpoint `/api/v1/top-momentum` (returns JSON array of 5 objects, each with `symbol`, `price`, `change`). Minimum coverage 85%.
- **Integration**: Flask test client verifies that the hero template renders without error and that the CTA URL is correct.
- **E2E / Visual Regression**: Playwright captures a screenshot of the hero on desktop and mobile, compares against baseline images (tolerance 0.1%). Hover interaction asserts tooltip content.
- **Accessibility**: axe‑core integration in Playwright; check colour contrast WCAG AA, keyboard focus, `prefers-reduced-motion` handling.

## Boundaries
- **Always**:
  - Run all tests locally before committing.
  - Keep CSS specificity low (no `!important`).
  - Document any new API fields.
- **Ask first**:
  - Introduce new third‑party JS library (e.g., D3).
  - Change the JSON schema of `/api/v1/top-momentum`.
  - Modify server‑side caching strategy.
- **Never**:
  - Commit generated assets (e.g., compiled CSS) to repo.
  - Hard‑code secrets or API keys in front‑end files.
  - Remove an existing test without a replacement.

## Success Criteria
- The hero renders correctly on Chrome/Firefox/Safari latest versions.
- Hovering any ribbon segment shows an accurate tooltip (symbol, price, % change).
- CTA button navigates to `/dashboard` (or appropriate route). ✅
- Automated test suite (`pytest && npx playwright test`) passes 100% on CI.
- Visual regression diff is < 0.1% on both desktop and mobile baselines.

## Open Questions
- Should the hero retrieve data server‑side (Flask) or client‑side (fetch)?
- Is a dark‑theme toggle required for future branding extensions?
- Desired fallback for browsers with `prefers-reduced-motion` – static SVG or hidden animation?

---
*Spec created per the `spec-driven-development` skill. Review and approve before implementation.*