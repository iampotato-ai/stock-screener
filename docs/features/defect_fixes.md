# Defect Fixes — `app.js` Journal Rendering & Stats Computation

> Reviewed: `static/js/app.js`  
> Review Date: 2026-05-31  
> Branch: `feature/workspace-ui`

---

## Table of Contents

1. [P0 — `getJournalData()` undefined crashes Excel export](#1-p0--getjournaldata-undefined-crashes-excel-export)
2. [P0 — `renderJournal()` fires before backend fetch resolves (race condition)](#2-p0--renderjournal-fires-before-backend-fetch-resolves-race-condition)
3. [P0 — `null` PnL / rAchieved causes `₹NaN` in stats bar](#3-p0--null-pnl--rachieved-causes-nan-in-stats-bar)
4. [P1 — `updateJournalLivePrices` undefined causes silent button failure](#4-p1--updatejournallivePrices-undefined-causes-silent-button-failure)
5. [P1 — Live prices sourced from stale scan data, not real-time](#5-p1--live-prices-sourced-from-stale-scan-data-not-real-time)
6. [P2 — Win Rate denominator mismatch vs Total Trades (no label)](#6-p2--win-rate-denominator-mismatch-vs-total-trades-no-label)
7. [P2 — `Avg R` stat hides win/loss R distribution and expectancy](#7-p2--avg-r-stat-hides-winloss-r-distribution-and-expectancy)
8. [P3 — `renderJournal` undefined degrades silently with no error](#8-p3--renderjournal-undefined-degrades-silently-with-no-error)

---

## Observations (What's Working Well)

- **Migration path (localStorage → SQLite)** is clean and idempotent. `initWatchlist()` checks `tv_migration_complete` before calling `/api/migrate-local-data`, preventing double-migration on reload.
- **`showToast()`** is a proper non-blocking notification system with `fadeSlideIn`/`fadeOut` animations, auto-dismiss at 4s. Should be used consistently in journal functions instead of `alert()`.
- **`computeScanDelta()`** correctly detects IMS/swing upgrades, setup changes, and breakout zone crossings between scans, fires browser Notifications for watchlisted stocks, and renders `change-ribbon` badges inline — solid UX for momentum traders.

---

## Defect Details & Fixes

---

### 1. P0 — `getJournalData()` undefined crashes Excel export

**File:** `app.js` → `exportToExcel()`

**Symptom:**  
Clicking the Export button throws:
```
ReferenceError: getJournalData is not defined
```
The Trade Journal sheet is silently skipped or the export crashes entirely.

**Root Cause:**  
`exportToExcel()` calls `getJournalData()` which is never defined anywhere in `app.js` or any linked script. The global `journalData` array already holds the data.

**Broken Code:**
```javascript
// In exportToExcel():
const journalData = getJournalData();   // ❌ function doesn't exist
```

**Fix — Steps:**
1. Open `app.js`, locate the `exportToExcel()` function.
2. Find the line `const journalData = getJournalData();`.
3. Replace it with a direct reference to the global array and add a null-safe guard:

```javascript
// ✅ FIXED — reference global journalData directly
const tradeData = (typeof journalData !== 'undefined' && Array.isArray(journalData))
    ? journalData
    : [];

if (tradeData.length > 0) {
    const jHeaders = [
        'Date', 'Ticker', 'Setup', 'Swing Band',
        'Entry', 'Stop', 'T1', 'T2', 'T3',
        'Qty', 'Risk (₹)', 'Status', 'Exit Price',
        'Exit Date', 'PnL (₹)', 'R-Achieved', 'Notes'
    ];
    const jSheetData = [jHeaders];

    tradeData.forEach(t => {
        jSheetData.push([
            t.date, t.ticker, t.setupLabel, t.swingband,
            t.entry, t.stop, t.target1, t.target2, t.target3,
            t.qty, t.riskAmount, t.status,
            t.exitPrice  ?? '',
            t.exitDate   ?? '',
            t.pnl        ?? '',
            t.rAchieved  ?? '',
            t.notes      ?? ''
        ]);
    });

    const jws = XLSX.utils.aoa_to_sheet(jSheetData);
    XLSX.utils.book_append_sheet(wb, jws, 'Trade Journal');
}
```

---

### 2. P0 — `renderJournal()` fires before backend fetch resolves (race condition)

**File:** `app.js` → `initWatchlist()`, `switchWorkspace()`

**Symptom:**  
On fast connections (localhost), switching to the Watchlist/Journal workspace immediately renders "No trades logged yet" — then data appears a moment later when the fetch resolves. On slow connections, the journal always shows empty until the user manually re-clicks the tab.

**Root Cause:**  
`fetchJournalFromBackend()` is async and called without `await`. `switchWorkspace('watchlist')` fires `renderJournal()` synchronously before the fetch promise resolves, so `journalData = []` at render time.

**Broken Code:**
```javascript
// In initWatchlist():
fetchWatchlistFromBackend();
fetchJournalFromBackend();  // ❌ fire-and-forget — no await, no loading state

// In switchWorkspace():
if (viewName === 'watchlist') {
    if (typeof renderJournal === 'function') renderJournal();  // ❌ runs immediately with empty journalData
}
```

**Fix — Steps:**
1. Add a skeleton loader to `fetchJournalFromBackend()` so the UI shows a loading state immediately.
2. Only call `renderJournal()` after the fetch resolves.
3. In `switchWorkspace()`, skip the `renderJournal()` call if a fetch is already in-flight (use a flag).

```javascript
// ✅ FIXED

let isJournalLoading = false;

async function fetchJournalFromBackend() {
    if (isJournalLoading) return;
    isJournalLoading = true;

    // Show skeleton immediately
    const tbody = document.getElementById('journal-table-body');
    if (tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="14" style="text-align:center; padding:2rem; color:var(--color-text-muted);">
                    <span style="font-size:0.9rem;">⏳ Loading journal...</span>
                </td>
            </tr>`;
    }

    try {
        const res = await fetch('/api/journal');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (Array.isArray(data)) {
            journalData = data;
        }
    } catch (err) {
        console.error('[Journal] Fetch error:', err);
        showToast('Failed to load trade journal.', 'error');
    } finally {
        isJournalLoading = false;
        if (typeof renderJournal === 'function') renderJournal();
    }
}

// In switchWorkspace(), replace the renderJournal() call:
if (viewName === 'watchlist') {
    const jc = document.getElementById('journal-container');
    if (jc) jc.style.display = 'flex';
    // ✅ Only render if data is loaded, else fetch (which renders on completion)
    if (journalData.length > 0) {
        if (typeof renderJournal === 'function') renderJournal();
    } else {
        fetchJournalFromBackend();
    }
}
```

---

### 3. P0 — `null` PnL / rAchieved causes `₹NaN` in stats bar

**File:** `app.js` → journal stats computation block (inside `renderJournal()`)

**Symptom:**  
Stats bar shows `₹NaN`, `NaN%`, or `NaN R` when any trade in `journalData` has `pnl: null` or `rAchieved: null` (which is always the case for open trades).

**Root Cause:**  
`Array.reduce()` over `pnl` or `rAchieved` without null-guarding propagates `NaN` as soon as one `null` value is encountered. The result poisons all downstream computations.

**Broken Code:**
```javascript
// ❌ null-unsafe reduce
const totalPnl = journalData.reduce((sum, t) => sum + t.pnl, 0);
const avgR     = journalData.reduce((sum, t) => sum + t.rAchieved, 0) / journalData.length;
const wins     = journalData.filter(t => t.pnl > 0);  // null > 0 is false but doesn't throw — silently wrong
```

**Fix — Steps:**
1. Locate the stats computation block in `renderJournal()`.
2. Replace all `reduce()` and `filter()` calls on `pnl` / `rAchieved` with null-safe versions.
3. Compute stats only over `closedTrades` (status !== `'open'` AND `pnl != null`).

```javascript
// ✅ FIXED — null-safe stats computation

function computeJournalStats(trades) {
    const closedTrades = trades.filter(t =>
        t.status !== 'open' && t.pnl != null && !isNaN(parseFloat(t.pnl))
    );

    const wins   = closedTrades.filter(t => parseFloat(t.pnl) > 0);
    const losses = closedTrades.filter(t => parseFloat(t.pnl) <= 0);

    const winRate  = closedTrades.length > 0
        ? ((wins.length / closedTrades.length) * 100).toFixed(1)
        : '0.0';

    const totalPnl = closedTrades.reduce(
        (sum, t) => sum + (parseFloat(t.pnl) || 0), 0
    );

    const closedWithR = closedTrades.filter(t => t.rAchieved != null && !isNaN(parseFloat(t.rAchieved)));
    const avgR = closedWithR.length > 0
        ? (closedWithR.reduce((sum, t) => sum + parseFloat(t.rAchieved), 0) / closedWithR.length).toFixed(2)
        : '0.00';

    return {
        total:        trades.length,
        openCount:    trades.filter(t => t.status === 'open').length,
        closedCount:  closedTrades.length,
        winRate,
        totalPnl:     totalPnl.toFixed(2),
        avgR,
    };
}

// Usage inside renderJournal():
const stats = computeJournalStats(journalData);

document.getElementById('journal-total-trades')?.textContent = stats.total;
document.getElementById('journal-win-rate')?.textContent     = stats.winRate + '%';
document.getElementById('journal-total-pnl')?.textContent    = '₹' + parseFloat(stats.totalPnl).toLocaleString('en-IN', { minimumFractionDigits: 2 });
document.getElementById('journal-avg-r')?.textContent        = stats.avgR + 'R';
```

---

### 4. P1 — `updateJournalLivePrices` undefined causes silent button failure

**File:** `app.js` (and/or the journal partial script)

**Symptom:**  
Clicking the "Refresh Prices" button in the journal does nothing. No error, no toast, no loading spinner.

**Root Cause:**  
The button HTML uses `onclick="window.updateJournalLivePrices(event)"` but `updateJournalLivePrices` is never defined in `app.js`. The `typeof` check is absent on the `onclick` attribute, so if the function is undefined the call silently fails in some browsers, or throws `TypeError` in strict environments.

**Fix — Steps:**
1. Add a safe fallback shim early in `app.js` (before DOMContentLoaded) so the function always exists.
2. Define the actual implementation in the journal script (or move it to `app.js`).

```javascript
// ✅ Add near the top of app.js, after the global state declarations:

// Safe fallback — prevents silent failure if journal script hasn't loaded
window.updateJournalLivePrices = window.updateJournalLivePrices || async function(e) {
    console.warn('[Journal] updateJournalLivePrices not yet loaded — retrying after 500ms');
    setTimeout(() => {
        if (typeof window.updateJournalLivePrices === 'function') {
            window.updateJournalLivePrices(e);
        } else {
            showToast('Live price refresh unavailable — check script load order.', 'error');
        }
    }, 500);
};
```

```javascript
// ✅ Full implementation (place in journal.js or at bottom of app.js):

window.updateJournalLivePrices = async function() {
    const openTrades = journalData.filter(t => t.status === 'open');
    if (openTrades.length === 0) {
        showToast('No open trades to update.', 'info');
        return;
    }

    const tickers = [...new Set(openTrades.map(t => t.ticker))].join(',');
    showToast('Refreshing live prices...', 'info');

    try {
        const res = await fetch(`/api/watchlist/prices?tickers=${encodeURIComponent(tickers)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const prices = await res.json();   // { TICKER: { close, change }, ... }

        journalData.forEach(trade => {
            if (trade.status === 'open' && prices[trade.ticker]) {
                trade._livePrice  = prices[trade.ticker].close;
                trade._liveChange = prices[trade.ticker].change;
            }
        });

        renderJournal();
        showToast('Live prices updated.', 'success');
    } catch (err) {
        console.error('[Journal] Live price refresh error:', err);
        showToast('Failed to refresh prices.', 'error');
    }
};
```

---

### 5. P1 — Live prices sourced from stale scan data, not real-time

**File:** `app.js` → journal open trade price display

**Symptom:**  
Open trades show the price from the last scan. If a stock drops off the screener (no longer passes scan criteria), its current price in the journal is blank or stale. The user makes risk decisions on incorrect data.

**Root Cause:**  
The journal resolves current prices by looking up `stocksData` (populated only by the last screener scan). Stocks that don't appear in the scan result have no price entry.

**Fix — Steps:**
1. Do **not** rely on `stocksData` for journal price display.
2. Use the dedicated `/api/watchlist/prices` endpoint (already built for the watchlist panel) which accepts any ticker list independent of scan criteria.
3. Call `updateJournalLivePrices()` automatically on initial journal render for open trades.

```javascript
// ✅ In renderJournal(), after the main table renders:

const openTrades = journalData.filter(t => t.status === 'open');
if (openTrades.length > 0) {
    // Check if we have a fresh price (fetched within last 2 mins)
    const lastPriceRefresh = parseInt(localStorage.getItem('journal_price_refresh_ts') || '0');
    const now = Date.now();
    const TWO_MINUTES = 2 * 60 * 1000;

    if ((now - lastPriceRefresh) > TWO_MINUTES) {
        window.updateJournalLivePrices();
        localStorage.setItem('journal_price_refresh_ts', now.toString());
    }
}
```

---

### 6. P2 — Win Rate denominator mismatch vs Total Trades (no label)

**File:** `app.js` / journal stats bar HTML

**Symptom:**  
Stats bar shows `Total: 25 | Win Rate: 60%`. The user assumes 60% of 25 trades — but win rate is actually 3 of 5 *closed* trades. Open trades inflate the total count but are excluded from win rate silently.

**Fix — Steps:**
1. Add a sub-label under the win rate badge showing closed trade sample size.
2. Add a sub-label under total showing open vs closed breakdown.

**HTML Change (journal stats bar):**
```html
<!-- Win Rate card -->
<div class="journal-stat-card">
    <div class="stat-label">Win Rate</div>
    <div id="journal-win-rate" class="stat-value">0%</div>
    <div id="journal-win-rate-sub" class="stat-sub" style="font-size:0.7rem; color:var(--color-text-muted);">0 closed trades</div>
</div>

<!-- Total Trades card -->
<div class="journal-stat-card">
    <div class="stat-label">Total Trades</div>
    <div id="journal-total-trades" class="stat-value">0</div>
    <div id="journal-trades-sub" class="stat-sub" style="font-size:0.7rem; color:var(--color-text-muted);">0 open · 0 closed</div>
</div>
```

**JS Change (inside `computeJournalStats` → `renderJournal`):**
```javascript
// ✅ Update sub-labels after computing stats
document.getElementById('journal-win-rate-sub')?.textContent =
    `${stats.closedCount} closed trade${stats.closedCount !== 1 ? 's' : ''}`;

document.getElementById('journal-trades-sub')?.textContent =
    `${stats.openCount} open · ${stats.closedCount} closed`;
```

---

### 7. P2 — `Avg R` stat hides win/loss R distribution and expectancy

**File:** `app.js` → `computeJournalStats()`

**Symptom:**  
`Avg R: +0.8R` could mean "+2R winners, -0.4R losers at 50% WR" or "+1.2R winners, -0.4R losers at 80% WR" — very different systems with the same Avg R number. There's no way to evaluate system quality from this stat alone.

**Fix — Steps:**
1. Extend `computeJournalStats()` to compute `avgWinR`, `avgLossR`, and `expectancy`.
2. Display `expectancy` as the primary metric and show Win/Loss R in a tooltip.

```javascript
// ✅ Extended computeJournalStats():

function computeJournalStats(trades) {
    const closedTrades = trades.filter(t =>
        t.status !== 'open' && t.pnl != null && !isNaN(parseFloat(t.pnl))
    );

    const wins   = closedTrades.filter(t => parseFloat(t.pnl) > 0);
    const losses = closedTrades.filter(t => parseFloat(t.pnl) <= 0);

    const winRate = closedTrades.length > 0
        ? wins.length / closedTrades.length
        : 0;

    const totalPnl = closedTrades.reduce((sum, t) => sum + (parseFloat(t.pnl) || 0), 0);

    // R-multiple distributions
    const winsWithR   = wins.filter(t => t.rAchieved != null && !isNaN(parseFloat(t.rAchieved)));
    const lossesWithR = losses.filter(t => t.rAchieved != null && !isNaN(parseFloat(t.rAchieved)));

    const avgWinR  = winsWithR.length > 0
        ? (winsWithR.reduce((s, t) => s + parseFloat(t.rAchieved), 0) / winsWithR.length)
        : 0;

    const avgLossR = lossesWithR.length > 0
        ? (lossesWithR.reduce((s, t) => s + parseFloat(t.rAchieved), 0) / lossesWithR.length)
        : -1;  // default to -1R if no data

    // Expectancy = (WinRate × AvgWinR) + ((1 - WinRate) × AvgLossR)
    const expectancy = (winRate * avgWinR) + ((1 - winRate) * avgLossR);

    return {
        total:        trades.length,
        openCount:    trades.filter(t => t.status === 'open').length,
        closedCount:  closedTrades.length,
        winRate:      (winRate * 100).toFixed(1),
        totalPnl:     totalPnl.toFixed(2),
        avgWinR:      avgWinR.toFixed(2),
        avgLossR:     avgLossR.toFixed(2),
        expectancy:   expectancy.toFixed(2),
    };
}
```

**HTML Change:**
```html
<!-- Replace Avg R card with Expectancy card -->
<div class="journal-stat-card" title="Expectancy = (Win% × Avg Win R) + (Loss% × Avg Loss R)">
    <div class="stat-label">Expectancy</div>
    <div id="journal-expectancy" class="stat-value">0.00R</div>
    <div id="journal-expectancy-sub" class="stat-sub" style="font-size:0.7rem; color:var(--color-text-muted);">
        Win: +0.00R · Loss: -0.00R
    </div>
</div>
```

**JS Update:**
```javascript
document.getElementById('journal-expectancy')?.textContent =
    (parseFloat(stats.expectancy) >= 0 ? '+' : '') + stats.expectancy + 'R';

document.getElementById('journal-expectancy-sub')?.textContent =
    `Win: +${stats.avgWinR}R · Loss: ${stats.avgLossR}R`;
```

---

### 8. P3 — `renderJournal` undefined degrades silently with no error

**File:** `app.js` → `switchWorkspace()`, tab switch handler

**Symptom:**  
If `renderJournal` (defined in a separate script) hasn't loaded when the user switches to the journal tab — due to script load order or a deferred bundle — the journal simply never renders. No error, no feedback to the user, no console warning.

**Root Cause:**  
All call sites use `if (typeof renderJournal === 'function') renderJournal()` which silently no-ops when the function is missing.

**Fix — Steps:**
1. Replace the silent guard with a version that logs a console error and shows a fallback error state in the DOM.

```javascript
// ✅ Helper to safely call renderJournal with fallback error state

function safeRenderJournal() {
    if (typeof renderJournal === 'function') {
        renderJournal();
    } else {
        console.error('[Journal] renderJournal is not defined — verify script load order.');
        const tbody = document.getElementById('journal-table-body');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="14" style="text-align:center; padding:2rem; color:var(--accent-red);">
                        ⚠️ Journal failed to initialise. Please refresh the page.
                    </td>
                </tr>`;
        }
        showToast('Journal module failed to load.', 'error');
    }
}

// Replace all instances of:
//   if (typeof renderJournal === 'function') renderJournal();
// with:
//   safeRenderJournal();
```

---

## Fix Implementation Checklist

| # | Priority | Issue | File | Status |
|---|----------|-------|------|--------|
| 1 | 🔴 P0 | `getJournalData()` undefined — crashes Excel export | `app.js` → `exportToExcel()` | ☐ Open |
| 2 | 🔴 P0 | `renderJournal()` race condition — empty state flash | `app.js` → `initWatchlist()`, `switchWorkspace()` | ☐ Open |
| 3 | 🔴 P0 | Null PnL/rAchieved → `₹NaN` in stats bar | `app.js` → journal stats block | ☐ Open |
| 4 | 🟡 P1 | `updateJournalLivePrices` undefined — silent button failure | `app.js` + journal script | ☐ Open |
| 5 | 🟡 P1 | Live prices from stale `stocksData` scan | `app.js` → journal price display | ☐ Open |
| 6 | 🟠 P2 | Win Rate denominator mismatch — no label | `app.js` + journal stats HTML | ☐ Open |
| 7 | 🟠 P2 | `Avg R` hides win/loss distribution & expectancy | `app.js` → `computeJournalStats()` | ☐ Open |
| 8 | 🔵 P3 | `renderJournal` undefined fails silently | `app.js` → all `switchWorkspace` call sites | ☐ Open |

---

*Generated by code review — `app.js` journal rendering and stats computation pass.*
