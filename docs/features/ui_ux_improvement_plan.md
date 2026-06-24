# UI/UX Improvement Plan – MomentumScan Stock Screener

## 1. Design Read
**Reading this as:** a data‑dense trading dashboard for active traders and institutional users, with a professional, trustworthy, action‑oriented vibe, leaning toward a refined, semi‑custom design system that balances information density with visual clarity.

## 2. Dial Settings
| Dial | Value | Rationale |
|------|-------|-----------|
| **DESIGN_VARIANCE** | **4** (low‑moderate) | Dashboards benefit from predictable layouts, clear alignment, and limited asymmetry to aid rapid scanning. |
| **MOTION_INTENSITY** | **3** (low) | Excessive animation distracts from fast‑moving market data; subtle hover/press feedback and micro‑transitions are enough. |
| **VISUAL_DENSITY** | **7** (high) | The screen must show many metrics, charts, and controls simultaneously for traders who need quick situational awareness. |

*Baseline (7/6/4) shifted toward lower variance & motion, higher density.*

## 3. Current UI Observations
**Strengths**
- Responsive layout using CSS Grid/Flex.
- Dark‑mode support via `data-theme`.
- Custom SVG icons and badge components.
- Good separation of concerns (header, nav, workspace views).
- Uses specialized charting libs (Lightweight Charts, Chart.js).

**Areas for Improvement**
- **Inconsistent styling:** inline `style=` attributes, scattered custom CSS classes, multiple font‑families loaded without a clear hierarchy.
- **Component duplication:** buttons, selects, tabs are re‑implemented with ad‑hoc HTML/CSS.
- **Information density feels cluttered:** dashboard packs many metrics into a single bar; visual hierarchy could be strengthened.
- **Accessibility gaps:** missing ARIA labels, focus outlines, and semantic markup in several custom controls.
- **Motion & feedback:** hover/active states exist but lack consistent motion primitives.
- **Responsive behavior:** sidebar and panels may not gracefully collapse on narrow screens.
- **Theme consistency:** hard‑coded colors may not adapt automatically.
- **Scalability:** adding new widgets or metrics requires manual HTML/CSS edits.

## 4. Recommended Improvements (Prioritized)

| Priority | Area | Recommendation | Expected Impact |
|----------|------|----------------|-----------------|
| 1 | **Design System Foundation** | Adopt a lightweight, utility‑first component library (e.g., **shadcn/ui** built on Radix UI + Tailwind) or create an internal token‑based design system. Define scales for spacing, typography, color, radius, shadow, motion. | Consistency, faster iteration, easier theming, reduced CSS bloat. |
| 2 | **Typography Rationalization** | Limit to **two** font families: Geist Variable (or Inter) for UI/data, Outfit (or a neutral sans) for headings. Set up a typographic scale and apply uniformly. | Cleaner visual hierarchy, reduced font‑loading overhead, improved readability. |
| 3 | **Color System & Contrast Audit** | Replace ad‑hoc RGBA values with CSS variables from a defined palette. Ensure WCAG AA contrast for text vs. background. Create dark‑mode variants for each token. | Better accessibility, reliable theme switching, less guesswork when adding new UI. |
| 4 | **Component Library Consolidation** | Replace custom implementations with reusable components: Button, Input/Select, Toggle/Switch, Tabs, Card, Tooltip/Popover, Accordion/Collapsible Panel. | Reduces code duplication, ensures consistent interaction patterns, improves accessibility. |
| 5 | **Dashboard Layout Refactor** | Break the dense `breadth‑bar` into logical groups (Market Regime, Breadth Metrics, Sentiment, Sector Heatmap). Use a responsive grid (2‑column desktop, 1‑column tablet/mobile) with consistent gap. Consider collapsible sections for less‑critical metrics. Replace inline `style=` with utility classes. | Improves scannability, reduces cognitive load, adapts better to different screen sizes. |
| 6 | **Screener Controls Refinement** | Group related controls (search, sector, preset) into a compact toolbar with consistent spacing. Replace custom select‑dropdown with a reusable Select component (with search if needed). Add a “Clear Filters” button. Ensure Scan button has clear loading/disabled states. | Faster filter setup, fewer mis‑clicks, clearer feedback. |
| 7 | **Range‑Filters Panel Enhancements** | Convert each filter group into a collapsible section (accordion). Standardize input fields using shared Form controls. Add reset‑all and apply buttons. Make panel responsive (collapsible to a drawer on mobile). | Less overwhelming UI, better use of vertical space, easier to adjust multiple criteria. |
| 8 | **Stat‑Card & Metric Widget Upgrade** | Wrap each metric in a Card component with consistent padding, border‑radius, and subtle shadow/outline. Use value + label layout. Retain sparklines but ensure proportional sizing and accessible aria‑label. Add tooltip on hover showing exact value and change. | Clearer visual separation, improves legibility of numbers, adds micro‑interaction feedback. |
| 9 | **Alert Log & Settings UX** | Make alert log a scrollable list with distinct item styles. Replace inline‑style Alert Settings panel with a Drawer/Slide‑over from the right. Use Switch toggles for each alert type. Add “Mark all as read” or “Clear” action with confirmation. | More scalable, easier to manage many alerts, better touch/friendly on mobile. |
| 10 | **Accessibility (a11y) Enhancements** | Ensure every interactive element has an accessible name. Add focus‑visible outlines. Verify color contrast ratios. Use semantic HTML where possible. Test keyboard navigation. | Compliance with WCAG, inclusivity for keyboard/screen‑reader users. |
| 11 | **Performance & Rendering Optimizations** | Memoize expensive calculations. Virtualize large tables (if screener renders many rows). Debounce rapid inputs. Lazy‑load off‑screen charts/widgets. | Smoother UI during market‑hours updates, lower CPU/GPU usage. |
| 12 | **Responsive & Mobile Adaptations** | Below md: (768px), convert sidebar into a collapsible drawer (overlay) togglable via hamburger icon. Stack dashboard grid into a single column. Ensure touch targets ≥48 px. Test layout on common tablet/smartphone breakpoints. | Usable on tablets and mobile devices for traders on the go. |
| 13 | **On‑boarding & Empty States** | For screens with no data, show a friendly empty state illustration/message with a clear CTA (e.g., “Start a scan to see results”). Provide a tour/tooltip for first‑time users highlighting key areas. | Reduces confusion, improves initial user experience. |
| 14 | **Documentation & Design Tokens** | Export design system tokens (JSON/JS) for use in frontend and design tools. Create a Storybook or component showcase for each reusable component. | Streamlines handoff between design and development, ensures long‑term consistency. |

## 5. Suggested Implementation Approach (Phased)

| Phase | Scope | Key Tasks |
|-------|-------|-----------|
| **Phase 0 – Foundations** | Set up tooling & design tokens | • Install Tailwind (if not already) and configure `tailwind.config.js` with custom colors, spacing, font‑family, radius, etc.<br>• Create a global CSS file with `@layer base, components, utilities`.<br>• Define CSS variables for theme (light/dark) and import them into Tailwind via `theme.extend`. |
| **Phase 1 – Component Library** | Build/reuse UI primitives | • Create `Button`, `Input`, `Select`, `Checkbox`, `Switch`, `Badge`, `Card`, `Tooltip`, `Drawer`, `Accordion`, `Tabs` components.<br>• Storybook each component with varied states (default, hover, active, disabled, loading).<br>• Replace ad‑hoc implementations in `index.html` with these components. |
| **Phase 2 – Layout & Dashboard** | Restructure main views | • Convert the inline‑grid/dashboard layout to a component (`DashboardLayout`) using the new Card and Grid primitives.<br>• Implement collapsible sections for less‑critical metrics.<br>• Ensure all spacing uses the design‑system scale (`space‑4`, `space‑6`, etc.). |
| **Phase 3 – Forms & Filters** | Improve screener & range panels | • Replace custom filter groups with reusable `FilterGroup` (label + input/select).<br>• Wrap the whole filter panel in an `Accordion` or `CollapsibleSidebar`.<br>• Add “Clear All” and “Apply” actions. |
| **Phase 4 – Data Widgets** | Enhance metrics & charts | • Build a `MetricCard` component that accepts `label`, `value`, `trend`, `sparklineData`.<br>• Refactor sparkline rendering to use a shared `<Sparkline />` wrapper (still canvas‑based but with consistent props).<br>• Add tooltip/hover info via `Tooltip` component. |
| **Phase 5 – Navigation & Header** | Workspace nav & header polish | • Replace the button‑based tabs with a `Tabs` component (RIBBON style) that highlights active tab with underline or background.<br>• Ensure the logo and workspace switcher are accessible and have appropriate aria labels. |
| **Phase 6 – Alerts & Settings** | Improve alert workflow | • Build an `AlertList` item component (icon, timestamp, message, severity badge).<br>• Create an `AlertDrawer` that slides in from the right, housing toggle switches and action buttons.<br>• Wire up open/close via state (e.g., `isAlertDrawerOpen`). |
| **Phase 7 – Accessibility & Testing** | Audit and fix | • Run automated aXe / Lighthouse checks; fix contrast, missing labels, focus order.<br>• Add manual keyboard navigation tests.<br>• Validate screen‑reader announcements (using NVDA/VoiceOver). |
| **Phase 8 – Responsiveness & Mobile** | Adapt to narrow screens | • Implement drawer for sidebar (`<DrawerPlacement side="right">`).<br>• Change dashboard grid to `grid-cols-1` below `md`.<br>• Ensure touch‑target sizes and adjust font sizes where needed. |
| **Phase 9 – Polish & Documentation** | Final refinements | • Add micro‑interactions (scale on press, subtle hover lift).<br>• Create a `theme-toggle` (sun/moon) that persists preference in `localStorage`.<br>• Write component documentation and update any internal contributor guides. |

## 6. Success Criteria
- **Visual Consistency:** 90% of UI elements use the design‑system tokens; no stray hex values or inline `style=` attributes remain.
- **Typography:** Only two font families are loaded; all text follows the defined scale.
- **Accessibility:** No WCAG AA failures in automated axe audit; all interactive elements are keyboard operable and have discernible names.
- **Performance:** Average frame‑rate during scrolling/resizing stays above 55 fps on a mid‑tier laptop; large tables use virtualization if row count > 200.
- **Usability:** Task‑completion time for common actions (e.g., run a scan, filter by sector, view alert details) reduces by ≥20% in a quick internal usability test.
- **Responsiveness:** Layout remains usable and readable down to 320 px width (mobile portrait) with critical actions reachable within two taps.
- **Maintainability:** Adding a new metric or filter requires ≤ 30 lines of new code (mostly composition of existing components).

## 7. Next Steps (Immediate)
1. Confirm design‑system choice – adopt an existing library (shadcn/ui, Material‑UI, Ant Design) or build a custom token‑based Tailwind setup.
2. Create a token file (`src/styles/tokens.ts` or `tailwind.config.js`) defining colors, spacing, typography, radius, shadows.
3. Set up a component stub (e.g., `Button.tsx`) and replace one instance in the template (e.g., the “Scan Now” button) to validate the approach.
4. Run a quick lint/check to ensure no regressions.

Once the foundation is in place, the remaining improvements can be tackled in the outlined phases, delivering a markedly cleaner, more accessible, and trader‑friendly UI.