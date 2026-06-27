---
target: dashboard screen
total_score: 22
p0_count: 0
p1_count: 2
timestamp: 2026-06-27T04-10-57Z
slug: templates-index-html
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Live status dot + update time are good; regime gauge has no skeleton on load |
| 2 | Match System / Real World | 3 | Domain terms (SMA21, AD Ratio, Regime) natural for traders; "bm-" prefix leaks into zero UI copy |
| 3 | User Control and Freedom | 2 | No way to dismiss/minimize the regime banner; Alert Log has Clear but no undo; no filter reset on the heatmap |
| 4 | Consistency and Standards | 2 | Side-stripe border style applied on 8 different component types; alert settings uses emoji (⚙️) while rest use SVG icons; badge shapes inconsistent (round vs pill vs square `border-radius: 0px` in inline styles) |
| 5 | Error Prevention | 2 | Clear alerts has no confirmation; alert settings has no "apply" — changes fire immediately with no review |
| 6 | Recognition Rather Than Recall | 3 | Navigation tabs have icon + label; breadth metrics have no tooltips explaining what SMA21 % means for new users |
| 7 | Flexibility and Efficiency | 2 | No keyboard navigation; no way to collapse the breadth bar; sector heatmap cells not clickable to drill into sector |
| 8 | Aesthetic and Minimalist Design | 2 | Breadth bar packs 7 dense metrics in one row; sector heatmap uses side-stripe borders across 15+ cells; regime banner and Alert Log coexist at the same visual weight |
| 9 | Error Recovery | 2 | Empty alert log shows italic placeholder; no feedback if data fetch fails; no retry affordance visible |
| 10 | Help and Documentation | 1 | Zero contextual tooltips on breadth metrics; no explanation of what "Regime Score" scale means; no onboarding |
| **Total** | | **22/40** | **Acceptable — significant improvements needed** |

---

## Anti-Patterns Verdict

**LLM assessment**: The dashboard reads as competent dark-mode fintech — it does not scream AI slop at first glance. The regime gauge is genuinely distinctive. However, two AI tells are present and compounding each other: the breadth bar is a dense KPI strip (every metric at equal visual weight), and the sector heatmap leans on colored side-stripe `border-left` accents to differentiate cells — the single most-recognized AI UI tell in the impeccable detector. The overall composition is correct but the surface is unpolished: inline `style=""` attributes on nearly every structural element, `border-radius: 0px` on conviction badges and the model weights bar (jarring in a rounded design system), and the gradient-text logo mark.

**Deterministic scan (detect.mjs on style.css)**:
- **8× side-stripe `border-left` accent** (lines 5269, 5273, 5281, 5788, 6148, 6190, 6555, 6610) — affects regime banner, alert items, and heatmap cells
- **1× gradient text** (line 263) — logo "Scan" word: `background-clip: text` with a gradient. Banned by the skill
- **1× bounce easing** (line 1086) — `cubic-bezier(0.34, 1.56, 0.64, 1)` somewhere in transitions
- **6× layout-property transition** (`transition: width`, `transition: max-height`, `transition: padding-right`) — causes layout thrash on progress bars and sidebar
- **1× overused font** — Inter declared at line 4731; Cabinet Grotesk + Geist already in use and more distinctive

No false positives identified. All findings confirmed against the source.

---

## Overall Impression

The regime gauge (donut arc with score) is the single strongest visual element — distinctive and data-dense without feeling cluttered. Everything around it dilutes that strength: the breadth metrics strip has 7 items at flat hierarchy, the sector heatmap cells use side-stripe borders that read as AI scaffolding, and the Alert Log panel competes with the heatmap for the same viewport real estate. The biggest single opportunity: **establish a visual hierarchy within the breadth bar** so the regime score is anchored as the primary signal, with secondary metrics clearly subordinate.

---

## What's Working

1. **Regime gauge** — the SVG arc + score + delta + band label is the strongest designed element on screen. Contextual, data-dense, immediately readable.
2. **Navigation tab bar** — icon + label pairing is clean; the sliding active indicator is a nice touch; 9 tabs is on the edge of too many but labeled clearly enough.
3. **Live status indicator** — the green dot + "TV Live Data connected" + timestamp is a good system status pattern that actually communicates something.

---

## Priority Issues

### [P1] Side-stripe borders across heatmap and alert items
**What**: 8 `border-left: 3-4px solid [color]` instances used as category signals on heatmap cells, regime banner, and alert log entries.  
**Why it matters**: This is the single most-recognized "AI UI tell." It reads as a copy-paste from a landing page component library, not a designed product. The heatmap cells in particular look like a bulleted list with colored tabs, not a spatial data visualization.  
**Fix**: Replace heatmap cell side-stripes with a full background tint at 8–12% opacity of the category color. For the regime banner, use a full `border` (1px) or a tinted background — not a one-sided stripe. For alert log entries, use a colored dot/icon on the left, not a border.  
**Suggested command**: `$impeccable polish templates/index.html static/css/style.css`

### [P1] Breadth bar: 7 metrics at equal visual weight
**What**: The breadth-bar packs A/D Ratio, % Above MA, Near 52W High, New 52W H/L, TV Sentiment, Scan Hit Rate, and Top Breadth Sectors in a horizontal strip with no established hierarchy. Every metric renders at roughly the same font size and visual emphasis.  
**Why it matters**: Traders landing here for a morning read cannot immediately tell *which number matters most right now*. The regime gauge (most important) is dwarfed by the equal-weight strip to its right. This is a cognitive load failure — 7 items at identical weight exceeds working memory.  
**Fix**: Group into Primary (Regime, A/D Ratio, Scan Hit Rate) and Secondary (rest). Make primary values visually larger or bolder. Suppress the Top Breadth Sectors column into a "details" interaction rather than inline.  
**Suggested command**: `$impeccable layout templates/index.html`

### [P2] Gradient text on logo mark
**What**: `.logo-text h1 span` uses `background: linear-gradient(135deg, ...)` + `-webkit-background-clip: text` — an absolute ban in the impeccable skill.  
**Why it matters**: Gradient text is decorative rather than meaningful and reads as AI-generated styling. The "Scan" word uses gradient where a single, confident brand color would communicate more authority.  
**Fix**: Replace with a solid `var(--color-m-blue-dark)` or the amber accent (#F59E0B). One solid color on the brand word is stronger than a gradient.  
**Suggested command**: `$impeccable polish static/css/style.css`

### [P2] `border-radius: 0px` on badges and bars (inline styles)
**What**: Conviction badges (`.conviction-badge`) and the model weights bar (`.model-weights-bar`) both have `border-radius: 0px` in inline `<style>` blocks. This makes them square in a design system that uses 6px/10px/16px radii everywhere.  
**Why it matters**: Flat-cornered elements in a rounded system look unfinished and inconsistent. The conviction badge spec in DESIGN.md calls for 6px radius — the implementation overrides it to 0.  
**Fix**: Remove the `border-radius: 0px` override from the inline `<style>` blocks in `index.html`; let the design-system class handle it.  
**Suggested command**: `$impeccable polish templates/index.html`

### [P2] Alert Log panel: empty state + layout tension
**What**: The Alert Log sidebar sits at full height alongside the sector heatmap, showing "No alerts triggered in this session." in italic muted text. It occupies roughly 25% of the dashboard width as a permanently visible empty panel.  
**Why it matters**: An empty log panel competing for real estate with the sector heatmap reduces the heatmap's legibility. The panel adds visual weight without adding information value when empty.  
**Fix**: Collapse the Alert Log to a minimized state (just the header bar with the notification count badge) when empty. Expand on click/alert. This makes the heatmap full width by default — which is a better information density trade.  
**Suggested command**: `$impeccable layout templates/index.html`

---

## Persona Red Flags

**Alex (Power User / Active Trader)**:  
- No keyboard shortcuts anywhere. Switching from Dashboard → Screener requires a mouse click on the tab. A trader monitoring intraday momentum wants `D`, `S`, `W` hotkeys.
- Sector heatmap cells are not clickable — can't drill into a sector from the dashboard. Would expect clicking "Consumer Durables 49%" to jump to a pre-filtered screener view.
- The regime score change delta (`▲4`) has no history. Alex wants to see the trend, not just the current delta.

**Sam (Accessibility-Dependent User)**:  
- The regime gauge is an SVG arc with no `aria-label` or `role` attribute. A screen reader gets nothing from it.
- Color alone distinguishes heatmap cell values (red → orange → green gradient on cell text). No other encoding (pattern, icon, text label) carries the rank. Fails WCAG 1.4.1.
- The alert log settings panel (absolutely positioned with z-index 100) has no focus trap. Tab from inside the panel will leak to the page behind it.

**Project-Specific: Swing Trader using MomentumScan for morning market read**:  
- Profile: Opens dashboard at 9:15 AM, needs the regime + top sector read in under 15 seconds, then moves to Screener.
- Red flags: The breadth bar takes ~3s to parse due to equal visual weight. The regime banner below the breadth bar (same priority zone) doubles the time to reach the heatmap. There's no "morning summary" mode — the trader sees the same full-detail view during research and during the live session.

---

## Minor Observations

- Emoji in navigation tabs (🚀 IPO Momentum, 🚀 EP Screener, 🐂 Bull Snort) mixes emoji with SVG icon tabs — inconsistent icon language across the nav bar.
- `font-size: 0.7rem` on the IPO hot-count badge and similar elements is below the 12px legibility floor. These badges will be unreadable at 1x on standard DPI.
- The "TV Live Data connected" status text is in the top-right at very small size — important system status that most users will never read.
- The `workspace-sliding-cap` active indicator presumably slides to the active tab, but on a 9-tab bar it will need sub-pixel accuracy; confirm it handles the `🐂 Bull Snort` tab width correctly.
- `bounce easing` at line 1086 (`cubic-bezier(0.34, 1.56, 0.64, 1)`) — identify which element uses this and replace with `cubic-bezier(0.16, 1, 0.3, 1)` (ease-out-quart).

---

## Questions to Consider

- The regime gauge is the most designed element on screen. What if the rest of the breadth bar served the regime — showing context *for* the regime score, not alongside it at equal weight?
- The Alert Log is always visible even when always empty for most sessions. Does it need to be a persistent sidebar, or could it be a floating notification drawer (triggered by the bell icon) that the user opens when they hear an alert?
- The heatmap cells currently show only percentage. What would a version look like that shows relative rank (the color gradient) AND gives an absolute sense of whether 49% is historically high or low for Consumer Durables?
