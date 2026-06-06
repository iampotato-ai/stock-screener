# Tier 1 UX Improvements – Implementation Plan

> **Branch:** `feature/workspace-ui`  
> **Date:** 2026-06-06  
> **Role:** Senior Product Designer + Frontend Architect  
> **Scope:** Tier 1 items only (high impact, low–medium effort)

This document turns the Tier 1 review items into concrete implementation steps for the workspace UI.

---

## 1. Simplify Screener Header & Filters

**Goal:** Make the primary daily actions (search, sector filter, preset selection, Scan Now) visually dominant, and demote advanced controls (columns, density, export, snapshot, auto-refresh) into a secondary band.

### 1.1. Restructure header into primary + secondary bands

**Files:** `templates/index.html`, `static/css/style.css`

1. In `index.html`, inside `#view-screener`, replace the current single `dashboard-controls` block for the screener header with two bands:

```html
<!-- BEFORE: single band wrapping everything -->
<section class="dashboard-controls glass-panel" id="screener-controls">
  <!-- search, sector, presets, chips, columns, density, export, snapshot, auto-refresh, Scan Now -->
</section>

<!-- AFTER: two-band layout -->
<section class="dashboard-controls glass-panel" id="screener-controls">
  <div class="screener-header-primary">
    <!-- Search | Sector | Preset | Scan Now -->
  </div>
  <div class="screener-header-secondary" id="screener-advanced-controls">
    <!-- Columns | Density | Auto-refresh | Export | Snapshot | Save Preset -->
  </div>
</section>
```

2. Keep the existing HTML chunks, but move them into the appropriate band:

- **Primary band (`.screener-header-primary`):**
  - Search box (`#search-input`)
  - Sector custom select (`#sector-select-wrapper`)
  - Preset selector (if present) or default preset chip group
  - Primary CTA button (`#btn-scan-now`)

- **Secondary band (`.screener-header-secondary`):**
  - Column chooser button (`#btn-columns`)
  - Density toggle (`#btn-density`) if present
  - Auto-refresh toggle (`#btn-auto-refresh`)
  - Export to Excel (`#btn-export-excel`)
  - Layout snapshot (`#btn-snapshot`) and `Save Preset` if any

3. In `style.css`, add layout for the two bands:

```css
.screener-header-primary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 0.75rem 0.5rem;
}

.screener-header-primary-left {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
}

.screener-header-secondary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  padding: 0.4rem 0.75rem 0.6rem;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(15, 23, 42, 0.75);
}

@media (max-width: 1100px) {
  .screener-header-secondary button {
    padding-inline: 0.45rem;
  }
  .screener-header-secondary .btn-label {
    display: none;
  }
}
```

4. Wrap the left side of the primary band with a helper div for alignment:

```html
<div class="screener-header-primary">
  <div class="screener-header-primary-left">
    <!-- search-box, sector-select, preset control -->
  </div>
  <button id="btn-scan-now" class="btn btn-primary">Scan Now</button>
</div>
```

> **Behavioral guideline:** Primary band should render even on narrow laptops without overflow; secondary band is allowed to wrap to two rows.

---

## 2. Create a Compact, Always-Visible Trade Ticket Block

**Goal:** Put core execution fields (entry, stop, risk amount, qty, R:R, targets) in a compact ticket at the top of the trade drawer, so a swing trader can size the trade without scrolling through analysis.

### 2.1. Structure the trade ticket inside the drawer

**Files:** `static/js/app.js`, `static/css/style.css`

1. In `app.js`, locate `openTradeDrawer(symbol)` and the HTML template used to build the drawer. Near the top of the drawer content (right after the header with ticker and close button), insert a `trade-ticket` block:

```js
const drawerHtml = `
  <div class="trade-drawer-header"> ... </div>

  <section class="trade-ticket">
    <div class="trade-ticket-row">
      <div class="tt-field">
        <label for="tt-entry">Entry</label>
        <input type="number" id="tt-entry" step="0.05" value="${entry.toFixed(2)}">
      </div>
      <div class="tt-field">
        <label for="tt-stop">Stop Loss</label>
        <input type="number" id="tt-stop" step="0.05" value="${stop.toFixed(2)}">
      </div>
      <div class="tt-field">
        <label for="tt-risk-amount">Risk ₹</label>
        <input type="number" id="tt-risk-amount" step="100" value="${defaultRisk.toFixed(0)}">
      </div>
    </div>

    <div class="trade-ticket-row">
      <div class="tt-field tt-field--readonly">
        <label>Risk / Share</label>
        <div id="tt-risk-per-share" class="tt-value">--</div>
      </div>
      <div class="tt-field tt-field--readonly">
        <label>Position Size</label>
        <div id="tt-qty" class="tt-value">--</div>
      </div>
      <div class="tt-field tt-field--readonly">
        <label>R : R (to T1)</label>
        <div id="tt-rr-multiple" class="tt-value">--</div>
      </div>
    </div>

    <div class="trade-ticket-row trade-ticket-row--targets">
      <div class="tt-target">
        <span class="tt-target-label">T1</span>
        <span class="tt-target-price" id="tt-t1">${t1.toFixed(2)}</span>
      </div>
      <div class="tt-target">
        <span class="tt-target-label">T2</span>
        <span class="tt-target-price" id="tt-t2">${t2.toFixed(2)}</span>
      </div>
      <div class="tt-target">
        <span class="tt-target-label">T3</span>
        <span class="tt-target-price" id="tt-t3">${t3.toFixed(2)}</span>
      </div>
    </div>
  </section>
`;
```

2. Below this, keep your existing sections (intelligence, pattern chips, AI forecast, chart, history, notes), preferably wrapped in `<details>` sections or separate `<section class="drawer-section">` blocks.

3. In `style.css`, add styling for the trade ticket:

```css
.trade-ticket {
  background: rgba(15, 23, 42, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 10px;
  padding: 0.75rem 0.9rem;
  margin: 0.75rem 0 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.trade-ticket-row {
  display: flex;
  gap: 0.75rem;
}

.trade-ticket-row--targets {
  justify-content: space-between;
}

.tt-field {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.tt-field label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}

.tt-field input {
  background: rgba(15, 23, 42, 0.9);
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.5);
  padding: 0.4rem 0.55rem;
  font-size: 0.82rem;
  color: var(--color-text-primary);
}

.tt-field--readonly .tt-value {
  min-height: 2rem;
  display: flex;
  align-items: center;
  padding: 0.4rem 0.55rem;
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.25);
  font-size: 0.82rem;
}

.tt-target {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  padding: 0.35rem 0.5rem;
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.7);
  border: 1px dashed rgba(148, 163, 184, 0.3);
}

.tt-target-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}

.tt-target-price {
  font-size: 0.86rem;
  font-weight: 600;
}

@media (max-width: 1000px) {
  .trade-ticket-row {
    flex-direction: column;
  }
}
```

### 2.2. Wire calculations to ticket fields

1. In `app.js`, add a helper that recomputes risk metrics whenever entry, stop, or risk amount change:

```js
function initTradeTicketInteractions(stock) {
  const entryInput = document.getElementById('tt-entry');
  const stopInput = document.getElementById('tt-stop');
  const riskAmountInput = document.getElementById('tt-risk-amount');

  const riskPerShareEl = document.getElementById('tt-risk-per-share');
  const qtyEl = document.getElementById('tt-qty');
  const rrEl = document.getElementById('tt-rr-multiple');

  function recalc() {
    const entry = parseFloat(entryInput.value) || 0;
    const stop = parseFloat(stopInput.value) || 0;
    const riskAmount = parseFloat(riskAmountInput.value) || 0;
    const riskPerShare = Math.max(entry - stop, 0);

    if (!riskPerShare || !riskAmount) {
      riskPerShareEl.textContent = '--';
      qtyEl.textContent = '--';
      rrEl.textContent = '--';
      return;
    }

    const qty = Math.floor(riskAmount / riskPerShare);
    const t1 = stock.target1_price || entry; // adjust as per existing data
    const rewardPerShare = Math.max(t1 - entry, 0);
    const rr = riskPerShare ? (rewardPerShare / riskPerShare) : 0;

    riskPerShareEl.textContent = riskPerShare.toFixed(2);
    qtyEl.textContent = qty.toLocaleString('en-IN');
    rrEl.textContent = rr ? rr.toFixed(2) + 'R' : '--';
  }

  [entryInput, stopInput, riskAmountInput].forEach(el => {
    if (!el) return;
    el.addEventListener('input', recalc);
  });

  recalc();
}
```

2. Call `initTradeTicketInteractions(stock)` at the end of `openTradeDrawer()` once the drawer has been injected into the DOM.

---

## 3. Collapse Non-Essential Sections in Trade Drawer by Default

**Goal:** Reduce vertical noise; make execution and risk the first thing a trader sees, while still keeping Kronos, pattern intelligence, and history reachable.

### 3.1. Wrap secondary sections in `<details>`

**Files:** `static/js/app.js`, `static/css/style.css`

1. In the drawer HTML template, wrap secondary sections:

```js
const drawerHtml = `
  ...
  ${tradeTicketHtml}

  <details class="drawer-section" open>
    <summary class="drawer-section-title">Market & Regime Context</summary>
    <!-- existing regime badges, MTF, breadth context -->
  </details>

  <details class="drawer-section">
    <summary class="drawer-section-title">AI Forecast (Kronos Ensemble)</summary>
    <!-- Kronos chart + ensemble verdict snippet for this stock -->
  </details>

  <details class="drawer-section">
    <summary class="drawer-section-title">Pattern Intelligence</summary>
    <!-- candlestick/price pattern chips, R:R setup tags -->
  </details>

  <details class="drawer-section">
    <summary class="drawer-section-title">History & Notes</summary>
    <!-- scan history rows, notes textarea, journal link -->
  </details>
`;
```

2. Add styling in `style.css`:

```css
.drawer-section {
  margin-bottom: 0.75rem;
}

.drawer-section > summary {
  list-style: none;
  cursor: pointer;
  padding: 0.5rem 0;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-muted);
  border-top: 1px solid rgba(148, 163, 184, 0.25);
}

.drawer-section[open] > summary {
  color: var(--color-text-primary);
}

.drawer-section > summary::-webkit-details-marker {
  display: none;
}

.drawer-section > summary::after {
  content: '▾';
  float: right;
  transform: translateY(1px);
  font-size: 0.7rem;
  opacity: 0.7;
}

.drawer-section[open] > summary::after {
  content: '▴';
}
```

> **Default state:**
> - Keep "Market & Regime Context" open by default.  
> - Start "AI Forecast", "Pattern Intelligence", and "History & Notes" collapsed.

---

## 4. Elevate "Save to Journal" + Risk Banner

**Goal:** Make saving trades to the journal the obvious end of the flow and lift high-risk conditions (no MTF alignment, earnings soon) into a visually strong banner.

### 4.1. Sticky drawer footer actions

**Files:** `static/js/app.js`, `static/css/style.css`

1. Wrap the existing drawer bottom buttons with a sticky container:

```html
<footer class="drawer-actions-sticky">
  <button id="btn-save-journal" class="btn btn-primary">Save to Journal</button>
  <button id="btn-open-tv" class="btn btn-ghost">Open in TradingView</button>
  <!-- any other secondary actions -->
</footer>
```

2. Style it in `style.css`:

```css
.drawer-actions-sticky {
  position: sticky;
  bottom: 0;
  padding: 0.6rem 1rem;
  margin: 0 -1rem -1rem;
  background: linear-gradient(to top, rgba(15, 23, 42, 0.98), rgba(15, 23, 42, 0.92));
  border-top: 1px solid rgba(148, 163, 184, 0.35);
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}

.drawer-actions-sticky .btn-primary {
  min-width: 150px;
}
```

### 4.2. Add risk banner under drawer header

1. In `openTradeDrawer`, after building the header and before `trade-ticket`, compute risk warnings based on existing data:

```js
function buildRiskBanner(stock) {
  const warnings = [];
  if (stock.mtf_score !== undefined && stock.mtf_score < 1) {
    warnings.push('No multi-timeframe trend alignment');
  }
  if (stock.days_to_earnings !== undefined && stock.days_to_earnings >= 0 && stock.days_to_earnings <= 5) {
    warnings.push(`Earnings in ${stock.days_to_earnings} days — consider reduced position size`);
  }
  if (!warnings.length) return '';

  return `
    <div class="drawer-risk-banner">
      ${warnings.map(w => `⚠️ ${w}`).join(' &nbsp;|&nbsp; ')}
    </div>`;
}
```

2. Inject it right after the header in the drawer HTML:

```js
const drawerHtml = `
  <div class="trade-drawer-header"> ... </div>
  ${buildRiskBanner(stock)}
  ${tradeTicketHtml}
  ...
`;
```

3. Add styling:

```css
.drawer-risk-banner {
  margin: 0.35rem 0 0.6rem;
  padding: 0.45rem 0.75rem;
  border-radius: 6px;
  border-left: 3px solid #f97316;
  background: rgba(245, 158, 11, 0.14);
  color: #fed7aa;
  font-size: 0.78rem;
  font-weight: 600;
}
```

---

## 5. Keyboard Navigation for Screener Table

**Goal:** Allow power users to triage lists quickly using `↑ / ↓ / Enter` and a single-key shortcut to add to watchlist.

### 5.1. Add key handler and row highlighting

**Files:** `static/js/app.js`, `static/css/style.css`

1. In `app.js`, near global state, add:

```js
let selectedRowIndex = -1;
```

2. After the screener table render (`renderTable` or equivalent), store a reference to the tbody:

```js
const screenerTableBody = document.querySelector('#screener-table tbody');
```

3. Add a document-level keydown handler (inside your main `DOMContentLoaded` init):

```js
document.addEventListener('keydown', (e) => {
  const activeView = document.querySelector('.workspace-view.active');
  if (!activeView || activeView.id !== 'view-screener') return;

  // Ignore when typing in inputs or textareas
  const tag = document.activeElement.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA') return;

  const rows = screenerTableBody?.querySelectorAll('tr[data-ticker]');
  if (!rows || !rows.length) return;

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    selectedRowIndex = Math.min((selectedRowIndex + 1), rows.length - 1);
    highlightSelectedRow(rows);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    selectedRowIndex = Math.max(selectedRowIndex - 1, 0);
    highlightSelectedRow(rows);
  } else if (e.key === 'Enter' && selectedRowIndex >= 0) {
    e.preventDefault();
    rows[selectedRowIndex].click();
  } else if ((e.key === 'w' || e.key === 'W') && selectedRowIndex >= 0) {
    e.preventDefault();
    const ticker = rows[selectedRowIndex].dataset.ticker;
    if (ticker) addToWatchlist(ticker);
  }
});

function highlightSelectedRow(rows) {
  rows.forEach(r => r.classList.remove('row-keyboard-selected'));
  const row = rows[selectedRowIndex];
  if (!row) return;
  row.classList.add('row-keyboard-selected');
  row.scrollIntoView({ block: 'nearest' });
}
```

4. Ensure each screener row has a `data-ticker` attribute in `renderTable`:

```js
rowHtml = `<tr data-ticker="${stock.clean_ticker}"> ... </tr>`;
```

5. Style the selected row:

```css
.row-keyboard-selected {
  outline: 2px solid var(--accent-teal, #14b8a6);
  outline-offset: -1px;
}
```

> **Keyboard mapping:**  
> `↑ / ↓` → move selection, `Enter` → open trade drawer, `W` → add selected ticker to watchlist.

---

## 6. Basic ARIA & Keyboard Support for Chips, Stat Cards & Sector Pills

**Goal:** Make core interactive elements (filter chips, stat cards, sector pills) accessible via keyboard and more readable for assistive tech, without a component rewrite.

### 6.1. Add a shared keyboard helper

**Files:** `static/js/app.js`

1. Add a small helper near the top of `app.js`:

```js
function makeKeyboardClickable(selector) {
  document.querySelectorAll(selector).forEach((el) => {
    if (!el.getAttribute('role')) {
      el.setAttribute('role', 'button');
    }
    if (!el.getAttribute('tabindex')) {
      el.setAttribute('tabindex', '0');
    }
    if (!el.dataset.keybound) {
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          el.click();
        }
      });
      el.dataset.keybound = '1';
    }
  });
}
```

2. After each render where you create chips, stat cards, or clickable sector pills, call:

```js
makeKeyboardClickable('.filter-chip');
makeKeyboardClickable('.stat-card');
makeKeyboardClickable('.bm-sector-row');
makeKeyboardClickable('.sector-chip');
```

3. For elements that are semantically buttons (e.g., filter chips), prefer migrating them to `<button>` over time, but this helper provides an immediate win.

---

## 7. Typography Floor & Small Contrast Fixes

**Goal:** Reduce eye strain and bring small text closer to best practices for a cockpit used daily.

### 7.1. Raise base font size and tighten minimums

**Files:** `static/css/style.css`

1. In the `body` rule, set base font size to 1rem and use CSS variables for scaling:

```css
:root {
  --text-xs: 0.75rem;   /* 12px */
  --text-sm: 0.8rem;    /* 12.8px */
  --text-base: 0.9rem;  /* 14.4px */
  --text-md: 1rem;      /* 16px */
}

body {
  font-family: 'Geist', system-ui, -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  font-size: var(--text-base);
}
```

2. Replace very small font sizes (e.g., `font-size: 0.65rem` or `0.7rem`) with `var(--text-xs)` and avoid going below that except for rare badges.

3. For low-contrast badges (e.g., grey text on grey glass), slightly increase opacity or border contrast:

```css
.badge {
  border-color: rgba(148, 163, 184, 0.6);
}

.conviction-badge.conviction-loading {
  color: #cbd5f5;
}
```

> **Guideline:** 14–16px for most body content, 12px only for secondary metadata or compact badges.

---

## Checklist Summary

**Tier 1 items covered in this doc:**

1. Split Screener header into primary and secondary bands, emphasising Scan Now and filters.  
2. Introduce a compact "Trade Ticket" section at the top of the trade drawer with live risk/R:R calculations.  
3. Collapse non-essential drawer sections (AI, patterns, history) into `<details>` blocks by default.  
4. Add a sticky drawer footer for "Save to Journal" and a risk banner for MTF misalignment and near-term earnings.  
5. Add `↑ / ↓ / Enter / W` keyboard navigation support for the Screener table.  
6. Harden chips, stat cards and sector pills with ARIA roles + keyboard activation helper.  
7. Raise typography floor and clean up the smallest, low-contrast text.

These changes should be implementable in small, reviewable chunks and will materially reduce cognitive load compared to the current workspace, bringing the experience closer to TradingView / Finviz / Screener.in / Tickertape in terms of daily usability.
