---
target: screener page
total_score: 24
p0_count: 0
p1_count: 2
timestamp: 2026-06-27T04-35-30Z
slug: templates-index-html-screener
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Live status dot + update time are good; pagination controls are visual but small |
| 2 | Match System / Real World | 4 | Domain terms (RVOL, IMS, MTF, setups) are highly aligned with active trading workflows |
| 3 | User Control and Freedom | 3 | Good filter flexibility; lacks a single-click "Reset All Filters" that clears chips + range values |
| 4 | Consistency and Standards | 2 | Icon style mismatch (emoji in range filter buttons vs SVG in header); button shape padding variations |
| 5 | Error Prevention | 2 | Min/Max inputs allow cross-over (e.g. Min > Max) causing silent blank tables with no error warning |
| 6 | Recognition Rather Than Recall | 2 | Dense column headers (MTF, IMS, RVOL) have no tooltips explaining calculations or abbreviations |
| 7 | Flexibility and Efficiency | 3 | Setup and MTF filter chips allow rapid filtering; "Best Swing Setups" is a useful efficiency shortcut |
| 8 | Aesthetic and Minimalist Design | 2 | High visual noise; five rows of control buttons and chips stack up to a wall of inputs; gradient top borders on KPI summary cards clash with flat theme |
| 9 | Error Recovery | 2 | Blank state shows a generic empty row; no prompt to reset filters |
| 10 | Help and Documentation | 1 | No tooltips on table headers or filter labels to guide first-time users |
| **Total** | | **24/40** | **Acceptable — improvements needed** |

---

## Anti-Patterns Verdict

**LLM assessment**: The screener page has very high information density, which is appropriate for a trading tool, but suffers from "layout sameness" and decorative visual noise.
The main tells are:
- **Gradient Top Borders** on the KPI summary cards (Elite Swing, Strong Swing, etc.). These clash with the flat, dark-mode styling of the table below and look like templates.
- **Emoji vs SVG Icon Mismatch**: The range filter buttons use inline emojis (`🎯`, `💾`, `🧹`) while the secondary control buttons use structured SVG icons (`Columns`, `Compact`, `Export`). This breaks typographic consistency.
- **Visual Grid Crowding**: Stacking five horizontal strips of inputs, buttons, and chips before the user even reaches the data table creates a high cognitive load wall.

---

## Overall Impression

The main screener has all the right functionality, but the controls are arranged in a flat, monotone grid that feels cluttered. The day-range slider in the table is an excellent real-world fit, but the table columns itself are so dense that they bleed together. The biggest opportunity: **clean up the filters visual footprint** by using consistent SVG icons, removing the gradient borders, and adding helpful tooltips to the table headers so the user can easily read the columns.

---

## What's Working

1. **Intraday Day-Range Slider** — The slider visual representation of the current price relative to day high/low is high-end, clean, and extremely useful.
2. **Setup and MTF Filter Chips** — Quick tabs at the bottom of the filters box allow rapid, responsive local filtering with clear active states.
3. **Data Formatting** — Column alignment (right-aligned numbers, left-aligned text) and formatting (tabular numerals for scores, clean short abbreviations like 2.28M) is neat.

---

## Priority Issues

### [P1] Control Layout: Extreme vertical stack (5 rows of inputs)
**What**: Five consecutive rows of search boxes, buttons, range filters, and chip bars stack up before the data table.  
**Why it matters**: Sighted users face a wall of visual noise. The actual table (the primary tool) is pushed down, forcing a scroll to see more than 5–8 rows at once.  
**Fix**: Consolidate the range filters into a collapsible drawer or collapsible accordian, and align control buttons to a consistent layout grid.  
**Suggested command**: `$impeccable layout templates/index.html`

### [P1] Icon Language: Emoji/SVG inconsistency
**What**: Emojis are used for icons in range filter buttons (🎯 Best Swing, 💾 Save, 🧹 Clear) and chips (🧠 Elite, 🚀 Breakout, 🛡️ Earnings-Safe), while clean SVGs are used for controls.  
**Why it matters**: Emojis look unpolished and clash with the professional, high-contrast visual tokens of the app design system.  
**Fix**: Replace emojis in buttons and tags with consistent, minimal inline SVGs (or remove them for text-only buttons where SVGs are redundant).  
**Suggested command**: `$impeccable polish templates/index.html`

### [P2] Mismatched KPI Card Borders
**What**: The top KPI summary cards (Elite Swing, Strong Swing, etc.) use thick, multi-colored top borders.  
**Why it matters**: This is a classic template aesthetic that doesn't match the rest of the application's clean flat borders.  
**Fix**: Replace the thick gradient borders with standard 1px solid borders (`var(--panel-border)`) and a subtle colored text color/tag to indicate card category.  
**Suggested command**: `$impeccable colorize static/css/style.css`

### [P2] Missing Column Header Tooltips
**What**: Dense abbreviations in headers (RVOL, IMS, MTF, Setup indicators) have no explanation on hover.  
**Why it matters**: Jordan (First-Time User) cannot distinguish what "IMS" means vs "Swing" or "MTF" and must recall or guess.  
**Fix**: Implement `data-tip` tooltips on the table headers (`<th>`) explaining each metric clearly.  
**Suggested command**: `$impeccable typeset templates/index.html`

---

## Persona Red Flags

**Alex (Power User / Active Day-Trader)**:  
- No keyboard shortcut to trigger a new scan or clear filters instantly.
- Range filters require clicking inside each min/max input box; would benefit from a quick slide range or simple presets.

**Jordan (First-Timer / Swing Trader)**:  
- Dense list of abbreviations (RVOL, IMS, MTF, 2TF/1TF/0TF) without any onboarding guide or tooltips.
- The distinction between "Elite Swing" and "Strong Swing" cards is unclear (what are the mathematical score filters?).

---

## Questions to Consider

- Could we move the Range Filters panel into a sliding sidebar drawer (similar to the stock trade drawer) or make it collapsible by default to give the table more space?
- Could we replace the emoji set with clean SVG outlines to elevate the screen's premium visual quality?
