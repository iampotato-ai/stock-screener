# UX Improvement Implementation Plan

> **Branch:** `feature/workspace-ui`  
> **Date:** 2026-06-01  
> **Role:** Senior Product Designer + Frontend Architect  
> **Stack:** Vanilla JS (`app.js`), HTML (`index.html`), CSS (`style.css`)

This plan is based on a full audit of the codebase and a comparison against TradingView, Finviz, Screener.in, and Tickertape. Changes are grouped into three tiers by impact vs. effort.

---

## Table of Contents

1. [Tier 1 — High Impact (Next 2 Weeks)](#tier-1--high-impact-next-2-weeks)
2. [Tier 2 — Medium Impact or Higher Effort](#tier-2--medium-impact-or-higher-effort)
3. [Tier 3 — Nice-to-Have Polish](#tier-3--nice-to-have-polish)
4. [Priority Summary Table](#priority-summary-table)

---

## Tier 1 — High Impact (Next 2 Weeks)

### 1. Split Screener Header into Two Bands

**Files:** `index.html`, `style.css`

**Problem:** The single-row `screener-controls` div packs Search, Sector, Columns, Density, Export, Snapshot, Auto-refresh, and Scan into one row — overwhelming on laptop widths.

**Fix:**

```html
<!-- BEFORE: single row -->
<div class="screener-controls">...</div>

<!-- AFTER: two-band layout -->
<div class="screener-header-primary">
  <!-- Search | Sector | Presets | Scan Now -->
</div>
<div class="screener-header-secondary">
  <!-- Columns | Density | Auto-refresh | Export | Snapshot -->
</div>
```

```css
.screener-header-secondary {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding: 0.4rem 1rem;
  border-top: 1px solid rgba(255,255,255,0.05);
  background: rgba(255,255,255,0.02);
}
@media (max-width: 1100px) {
  .screener-header-secondary { flex-wrap: wrap; }
}
```

---

### 2. Collapsible Signal Strip (Demote Per-Row Dots)

**Files:** `app.js` — `renderTable()`, `col.id === 'ticker'` block; `style.css`

**Problem:** 6–7 dots/icons (sector dot, inside-bar, vol-dryup, MA-flirting, divergence, 52W-high flame, scan-change ribbon) all render inline unconditionally — visually noisy and hard to parse.

**Fix:** Keep only the 2 highest-signal indicators always visible. Move the rest into a hover popover.

```js
// In the ticker cell build block:
const alwaysVisible = [sectorDotHtml, high52wDotHtml].filter(Boolean).join('');
const inPopover = [insideBarDotHtml, volDryUpDotHtml, maFlirtingDotHtml, divergenceDotHtml].filter(Boolean);
const stripHtml = inPopover.length
  ? `<span class="signal-strip" tabindex="0" aria-label="${inPopover.length} signals">
       ···
       <span class="signal-popover">${inPopover.join('')}</span>
     </span>`
  : '';
```

```css
.signal-strip { position: relative; cursor: pointer; font-size: 0.7rem; opacity: 0.6; }
.signal-strip:hover .signal-popover,
.signal-strip:focus .signal-popover { display: flex; gap: 4px; }
.signal-popover {
  display: none;
  position: absolute;
  bottom: 120%;
  background: var(--bg-elevated);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 6px;
  padding: 4px 8px;
  white-space: nowrap;
  z-index: 50;
}
```

---

### 3. Restructure Trade Drawer into Collapsible Sections

**Files:** `app.js` — `openTradeDrawer()` HTML template; `style.css`

**Problem:** The drawer stacks ~12 sections vertically with no visual grouping or hierarchy — clutter causes mis-prioritisation of risk signals.

**Fix:** Wrap each logical section in a native `<details>` element (zero extra JS).

```js
// In drawer render HTML:
`<details class="drawer-section" open>
  <summary class="drawer-section-title">1 · Execution & Risk</summary>
  <!-- entry, stop, qty, targets, risk calc -->
</details>

<details class="drawer-section" open>
  <summary class="drawer-section-title">2 · Market & Regime Context</summary>
  <!-- MTF warnings, breadth context -->
</details>

<details class="drawer-section">
  <summary class="drawer-section-title">3 · AI Forecast (Kronos)</summary>
  <!-- Kronos chart + table -->
</details>

<details class="drawer-section">
  <summary class="drawer-section-title">4 · History & Notes</summary>
  <!-- scan history, notes textarea -->
</details>`
```

```css
.drawer-section > summary {
  font-weight: 700;
  font-size: 0.8rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: 0.75rem 0;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  list-style: none;
}
.drawer-section[open] > summary { color: var(--color-text-primary); }
```

---

### 4. Elevate "Save to Journal" CTA + Risk Warning Banner

**Files:** `app.js` — `openTradeDrawer()` template; `style.css`

**Problem:** "Save to Journal" is buried at the bottom. MTF and earnings warnings are visually modest despite being high-impact risk signals.

**Fix 1 — Sticky drawer footer:**

```css
.drawer-actions-sticky {
  position: sticky;
  bottom: 0;
  background: var(--bg-surface);
  border-top: 1px solid rgba(255,255,255,0.08);
  padding: 0.75rem 1rem;
  display: flex;
  gap: 0.5rem;
}
```

**Fix 2 — Colored risk banner under drawer header** (uses existing `mtfScore` + `upcoming_earnings` data already in `stock` object):

```js
const warningItems = [];
if (stock.mtfScore < 1) warningItems.push('⚠️ No MTF alignment');
if (earningsInDays >= 0 && earningsInDays <= 5)
  warningItems.push(`⚠️ Earnings in ${earningsInDays}d — reduce size`);
if (warningItems.length) {
  drawerHtml += `<div class="drawer-risk-banner">${warningItems.join(' &nbsp;|&nbsp; ')}</div>`;
}
```

```css
.drawer-risk-banner {
  background: rgba(245, 158, 11, 0.12);
  border-left: 3px solid #f59e0b;
  padding: 0.5rem 1rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: #fbbf24;
  border-radius: 0 4px 4px 0;
  margin-bottom: 0.5rem;
}
```

---

### 5. Single Canonical Journal Hub + Visual Differentiation

**Files:** `app.js` — `switchWorkspace()` and screener tab click handler; `style.css`

**Problem:** `renderJournal()` is called from both the Screener "Journal" sub-tab and the Watchlist workspace — duplicate mental model confuses traders on where their canonical trade log lives.

**Fix:** In the Screener tab click handler for `currentTab === 'journal'`, redirect to the Watchlist workspace instead:

```js
// Replace inline journal render with redirect:
const watchlistTab = document.querySelector('.workspace-tab[data-view="watchlist"]');
if (watchlistTab) watchlistTab.click();
```

Give the journal table a distinct visual identity to distinguish it from the scan table:

```css
#view-watchlist .journal-table-wrap {
  background: rgba(16, 185, 129, 0.03);
  border-top: 2px solid rgba(16, 185, 129, 0.2);
}
#view-watchlist .journal-section-header {
  color: var(--color-success);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
```

---

### 6. Keyboard Navigation in Screener Table

**Files:** `app.js` — `DOMContentLoaded` handler; `style.css`

**Problem:** No keyboard navigation exists. TradingView-style `↑/↓/Enter` is a critical daily efficiency feature for power users triaging 100+ names.

**Fix:** Add `selectedRowIndex` state and wire `keydown`:

```js
let selectedRowIndex = -1;

document.addEventListener('keydown', (e) => {
  const activeWorkspace = document.querySelector('.workspace-tab.active')?.dataset.view;
  if (activeWorkspace !== 'screener') return;
  if (document.activeElement.tagName === 'INPUT') return;

  const rows = tableBody.querySelectorAll('tr:not(.skeleton-row)');
  if (!rows.length) return;

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    selectedRowIndex = Math.min(selectedRowIndex + 1, rows.length - 1);
    highlightSelectedRow(rows);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    selectedRowIndex = Math.max(selectedRowIndex - 1, 0);
    highlightSelectedRow(rows);
  } else if (e.key === 'Enter' && selectedRowIndex >= 0) {
    rows[selectedRowIndex]?.click();
  } else if ((e.key === 'w' || e.key === 'W') && selectedRowIndex >= 0) {
    const ticker = rows[selectedRowIndex]
      ?.querySelector('[data-column="ticker"] .ticker-box')
      ?.textContent?.trim()?.split(/\s/)[0];
    if (ticker) addToWatchlist(ticker, e);
  }
});

function highlightSelectedRow(rows) {
  rows.forEach(r => r.classList.remove('row-keyboard-selected'));
  rows[selectedRowIndex]?.classList.add('row-keyboard-selected');
  rows[selectedRowIndex]?.scrollIntoView({ block: 'nearest' });
}
```

```css
.row-keyboard-selected {
  outline: 2px solid var(--accent-teal);
  outline-offset: -2px;
}
```

**Shortcut reference:**

| Key | Action |
|-----|--------|
| `↑` / `↓` | Move row selection |
| `Enter` | Open trade drawer |
| `W` | Add to watchlist |
| `Esc` | Close drawer / modal |

---

### 7. Keyboard + ARIA Support for Chips, Pills, and Dropdowns

**Files:** `app.js` — after chip and pill render calls

**Problem:** All filter chips, sector pills, and stat cards are `<div>`/`<span>` with `onclick` — invisible to keyboard users and screen readers. `aria-expanded` is already on some dropdowns but not others.

**Fix:** Add a shared utility and call it after every render pass:

```js
function makeKeyboardClickable(selector) {
  document.querySelectorAll(selector).forEach(el => {
    if (!el.getAttribute('role')) el.setAttribute('role', 'button');
    if (!el.getAttribute('tabindex')) el.setAttribute('tabindex', '0');
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        el.click();
      }
    });
  });
}

// Call after rendering:
makeKeyboardClickable('.filter-chip');
makeKeyboardClickable('.sector-pill');
makeKeyboardClickable('.stat-card');
makeKeyboardClickable('.bm-sector-row');
```

---

## Tier 2 — Medium Impact or Higher Effort

### 8. Intraday Pro: Consolidate into One Primary Surface

**Files:** `app.js` — screener tab handler; `index.html`; `renderIntradayWorkspace()`

**Problem:** "Intraday" appears as both a screener sub-tab and a top-level workspace view — two overlapping but non-identical UIs create a duplicate mental model.

**Fix:**
1. Remove the Intraday sub-tab from `#screener-tabs` in `index.html`.
2. Promote the workspace view as the single Intraday surface.
3. Add per-preset empty-state messages in `renderIntradayWorkspace()`:

```js
const presetDescriptions = {
  gap_go:       'Gap & Go — Stocks gapping >1% above VWAP with follow-through',
  vwap_leaders: 'VWAP Leaders — Trading just above VWAP with strong IMS',
  high_rvol:    'High RVOL — Relative Volume ≥ 1.5× (unusual activity)',
  confluence:   'Confluence — Strong IMS + Elite/Strong Swing score',
};

// When a widget has 0 results:
widgetEl.innerHTML = `
  <div class="intraday-empty-state">
    <p class="empty-hint">${presetDescriptions[preset]}</p>
    <p>No candidates match right now. Check back after 10:15 AM.</p>
  </div>`;
```

4. Allow left-click on an intraday row to open the trade drawer; move the TradingView open to a dedicated icon button:

```js
// In intraday row render:
`<tr onclick="openTradeDrawer('${stock.clean_ticker}')">
  ...
  <td><button onclick="event.stopPropagation(); openTradingView('${stock.clean_ticker}')" title="Open in TradingView">📈</button></td>
</tr>`
```

---

### 9. Dashboard: Tie Regime Badge to Preset Suggestions

**Files:** `app.js` — `renderRegimeWarning()` and `REGIME_MESSAGES`

**Problem:** The `REGIME_MESSAGES` object already has the right guidance text but doesn't connect to any clickable action — traders read the text and then must manually navigate and filter.

**Fix:** Extend `REGIME_MESSAGES` with a `preset` field and render a clickable CTA button:

```js
const REGIME_MESSAGES = {
  'Bull Run':    { text: '...', type: 'bullish', preset: 'elite',  presetLabel: 'Use Aggressive Preset →' },
  'Bullish':     { text: '...', type: 'bullish', preset: 'strong', presetLabel: 'Use Breakout Preset →' },
  'Neutral':     { text: '...', type: 'neutral', preset: null,     presetLabel: null },
  'Bearish':     { text: '...', type: 'bearish', preset: 'watch',  presetLabel: 'Use Defensive Preset →' },
  'Bear Market': { text: '...', type: 'danger',  preset: null,     presetLabel: 'Avoid new entries' },
};

// In renderRegimeWarning() banner HTML, add:
msg.preset
  ? `<button class="btn-regime-preset" onclick="applyRegimePreset('${msg.preset}')">
       ${msg.presetLabel}
     </button>`
  : ''

// New helper function:
function applyRegimePreset(swingBand) {
  const swingFilterInput = document.getElementById('filter-swing');
  if (swingFilterInput) { swingFilterInput.value = swingBand; filterAndRender(); }
  const screenerTab = document.querySelector('.workspace-tab[data-view="screener"]');
  if (screenerTab) screenerTab.click();
}
```

---

### 10. RRG: Guidance Panel + Cross-View Filter Banner

**Files:** `index.html` (RRG workspace layout); `app.js` — RRG sector click handler

**Problem:** RRG quadrant meanings are unexplained and clicking a sector does not clearly communicate that it filters the screener.

**Fix 1 — Static guidance card** beside the canvas in `index.html`:

```html
<div class="rrg-guide-card glass-panel">
  <p class="guide-title">How to Use RRG Today</p>
  <ul>
    <li>🟢 <strong>Leading</strong> → Overweight, favour breakout entries</li>
    <li>🟡 <strong>Improving</strong> → Build watchlists, size small</li>
    <li>🔴 <strong>Weakening</strong> → Reduce exposure, tighten stops</li>
    <li>⚪ <strong>Lagging</strong> → Avoid fresh entries</li>
  </ul>
</div>
```

**Fix 2 — Toast on sector click:**

```js
// In RRG sector click handler, after selectSector():
showToast(`Screener filtered to ${sectorName} (Score: ${score}/100) — click Screener tab to view`, 'info');
```

**Fix 3 — Allow saving RRG snapshots linked to journal periods** (store `{ date, sectors }` in `localStorage` keyed to the journal entry date; link from journal row).

---

### 11. AI Forecast: Top-Line Verdict Strip + Progressive Disclosure

**Files:** `app.js` — `renderAIForecastWorkspace()`

**Problem:** Ensemble weights, agreement matrix, and full backtest table are all visible at once — the key "is this bullish?" answer is buried in technical metrics.

**Fix 1 — Verdict strip above the chart:**

```js
const direction  = forecastReturn > 1.5 ? 'Bullish' : forecastReturn < -1.5 ? 'Bearish' : 'Neutral';
const confidence = ensembleAgreement > 0.7 ? 'High' : ensembleAgreement > 0.5 ? 'Medium' : 'Low';

const verdictHtml = `
  <div class="ai-verdict-strip ai-verdict--${direction.toLowerCase()}">
    <span class="verdict-label">AI View: ${direction}</span>
    <span class="verdict-move">Expected ${forecastReturn > 0 ? '+' : ''}${forecastReturn.toFixed(1)}%</span>
    <span class="verdict-conf">Confidence: ${confidence}</span>
  </div>`;
```

**Fix 2 — Progressive disclosure with `<details>`:**

```html
<details class="ai-internals">
  <summary>Show Model Internals (ensemble weights, agreement matrix, backtest)</summary>
  <!-- existing ensemble weights + agreement matrix + backtest table -->
</details>
```

**Fix 3 — Reliability band in the drawer's AI section:**

```js
// In trade drawer Kronos block:
`<p class="ai-reliability-band">Model reliability: ${reliabilityLabel} — based on ${nForecasts} past forecasts, MAE ${mae.toFixed(1)}%</p>`
```

---

### 12. Refactor Repeated UI Patterns into Shared Factory Functions

**Files:** `app.js` — top of file, before render functions

**Problem:** Badge HTML, setup pill HTML, and filter chip HTML are constructed inline in multiple render functions (`renderTable`, `renderJournal`, `renderWatchlist`), causing visual divergence as features are added.

**Fix:** Extract shared factory functions:

```js
// --- Shared UI factories ---

function makeBadge(text, classNames, title = '') {
  return `<span class="badge ${classNames}"${title ? ` title="${escapeHtml(title)}"` : ''}>${text}</span>`;
}

function makeSetupPill(label, confidence, tags = []) {
  // Move the existing large if/else chain from renderTable() here
  let pillClass = 'setup-pill-early';
  let icon = '';
  if (label.includes('VCP'))              { pillClass = 'setup-pill-vcp';      icon = '🌀 '; }
  else if (label.includes('Breakout'))    { pillClass = 'setup-pill-breakout'; icon = '🚀 '; }
  // ... (all existing conditions) ...
  const title = tags.length
    ? `Tags: ${tags.join(', ')}\nConfidence: ${confidence}%`
    : `Confidence: ${confidence}%`;
  return `<span class="setup-pill ${pillClass}" title="${escapeHtml(title)}">${icon}${label}</span>`;
}

function makeFilterChip(value, label, activeValue, extraClass = '') {
  const isActive = activeValue === value;
  return `<button class="filter-chip${isActive ? ' active' : ''}${extraClass ? ' ' + extraClass : ''}"
    data-value="${value}" role="button" tabindex="0">${label}</button>`;
}
```

Then replace the large inline blocks in `renderTable()` with calls to these functions.

---

## Tier 3 — Nice-to-Have Polish

### 13. Responsive Breakpoints

**Files:** `style.css`

```css
/* Wide monitor: table + drawer side-by-side */
@media (min-width: 1440px) {
  #view-screener {
    display: grid;
    grid-template-columns: 1fr 420px;
    gap: 0;
  }
  .trade-drawer {
    position: sticky;
    top: 60px;
    height: calc(100vh - 60px);
    overflow-y: auto;
  }
}

/* Laptop: collapse secondary header to icon-only buttons */
@media (max-width: 1100px) {
  .screener-header-secondary .btn-label { display: none; }
  .screener-header-secondary button { padding: 0.4rem; }
}

/* Prevent fixed 400px chart height from breaking narrow views */
#drawer-tv-chart-container {
  height: clamp(250px, 30vh, 400px);
}
```

---

### 14. Micro-Interactions

**Files:** `style.css`; `app.js` — drawer open/close

```css
/* Drawer slide-in animation */
.trade-drawer {
  transform: translateX(100%);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.trade-drawer.open { transform: translateX(0); }

/* Table row hover */
.screener-table tbody tr:hover {
  background: rgba(255,255,255,0.03);
  cursor: pointer;
}

/* Filter chip active accent */
.filter-chip.active {
  background: rgba(20,184,166,0.15);
  border-color: var(--accent-teal);
  color: var(--accent-teal);
}

/* Keyboard-selected row */
.row-keyboard-selected {
  outline: 2px solid var(--accent-teal);
  outline-offset: -2px;
}
```

```js
// In openTradeDrawer(), after injecting HTML:
drawerEl.classList.remove('open');
requestAnimationFrame(() => drawerEl.classList.add('open'));

// In closeTradeDrawer():
drawerEl.classList.remove('open');
```

---

### 15. Consistent Typography Scale via CSS Custom Properties

**Files:** `style.css` — `:root` block

```css
:root {
  /* Type scale */
  --text-xs:   0.70rem;
  --text-sm:   0.80rem;
  --text-base: 0.875rem;
  --text-md:   1.00rem;
  --text-lg:   1.125rem;

  /* Spacing scale */
  --space-1: 0.25rem;
  --space-2: 0.50rem;
  --space-3: 0.75rem;
  --space-4: 1.00rem;
  --space-6: 1.50rem;
  --space-8: 2.00rem;
}
```

Then do a find-replace pass replacing hardcoded `font-size: 0.8rem`, `0.85rem`, `0.75rem`, etc. with `var(--text-sm)`, `var(--text-xs)` etc. consistently across all workspaces.

---

### 16. Color-Blind Accessible Status Labels

**Files:** `app.js` — all `val-up`/`val-down` render sites; `renderBreadthPanel()`

**Problem:** Red/green badges (`val-up`, `val-down`, regime colors) are color-only — invisible to red-green color-blind users.

**Fix:** Add `aria-label` attributes with text descriptions:

```js
// In renderTable() change % cell:
html += `<td class="text-right ${changeClass}"
  aria-label="${changeSign}${stock.change.toFixed(2)} percent change">
  ${changeSign}${stock.change.toFixed(2)}%
</td>`;

// Regime badge in renderBreadthPanel():
badge.setAttribute('aria-label', `Market regime: ${b.regimeBand}, score ${b.regimeScore} out of 100`);
```

Also consider adding a small `(▲)` / `(▼)` text symbol alongside colored values for colorblind redundancy:

```js
const arrow = stock.change >= 0 ? '▲' : '▼';
html += `<td class="text-right ${changeClass}">${arrow} ${Math.abs(stock.change).toFixed(2)}%</td>`;
```

---

## Priority Summary Table

| # | Change | Files | Est. Effort | Tier |
|---|--------|-------|-------------|------|
| 1 | Split screener header into 2 bands | `index.html`, `style.css` | 1h | 1 |
| 2 | Signal strip popover for per-row dots | `app.js`, `style.css` | 2h | 1 |
| 3 | Collapsible drawer sections (`<details>`) | `app.js`, `style.css` | 3h | 1 |
| 4 | Sticky "Save to Journal" + risk banner | `app.js`, `style.css` | 2h | 1 |
| 5 | Wire Journal sub-tab → Watchlist hub | `app.js` | 1h | 1 |
| 6 | Keyboard nav `↑/↓/Enter/W` in table | `app.js`, `style.css` | 2h | 1 |
| 7 | ARIA + keyboard for chips, pills, cards | `app.js` | 1h | 1 |
| 8 | Consolidate Intraday to one surface | `app.js`, `index.html` | 3h | 2 |
| 9 | Regime → preset suggestion button | `app.js` | 1h | 2 |
| 10 | RRG guidance panel + sector banner | `index.html`, `app.js` | 2h | 2 |
| 11 | AI verdict strip + progressive disclosure | `app.js` | 3h | 2 |
| 12 | Refactor badge/chip/pill factory functions | `app.js` | 4h | 2 |
| 13 | Responsive breakpoints (1440px, 1100px) | `style.css` | 2h | 3 |
| 14 | Drawer animation + row hover states | `style.css`, `app.js` | 1h | 3 |
| 15 | Typography scale CSS custom properties | `style.css` | 2h | 3 |
| 16 | Color-blind accessible status labels | `app.js`, `style.css` | 2h | 3 |

**Total estimated effort:** ~32 hours across all three tiers.
