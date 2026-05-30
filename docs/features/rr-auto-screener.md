# Trade Setup Auto-Screener with R:R Pre-filter — Feature Spec

> **Feature ID:** `FEAT-005`  
> **Branch:** `feature/workspace-ui`  
> **Status:** 📋 Planned  
> **Priority:** High  
> **Component:** Screener Engine + Risk Calculator + Trade Drawer

---

## 1. Overview

The Risk Calculator drawer is currently **manual** — a trader opens it per stock, sets an entry, stop, and target, and reads the resulting R:R. This feature inverts that workflow: you set a **minimum R:R threshold once**, and the system automatically evaluates every stock in the scan universe (~800+), computing ATR-based stop placement and structure-derived targets for each, then surfaces only the **10–15 stocks that meet or exceed the minimum R:R** as a ranked shortlist of actionable daily setups.

The result is a dedicated **R:R Screener** panel — a focused, pre-filtered trade idea list that respects your risk tolerance before you see a single ticker.

---

## 2. Goals

- Auto-compute `entry`, `stop`, and `target` for every stock using deterministic, ATR-based rules — no manual input required.
- Filter the full scan universe to only stocks where `(target − entry) / (entry − stop) ≥ min_rr`.
- Surface results as a ranked, compact shortlist in a dedicated screener sub-tab or inline panel.
- Allow the user to override entry/stop/target per stock in the existing Risk Calculator drawer without leaving the flow.
- Persist `min_rr` and method preferences across sessions via `localStorage`.
- Compute entirely **client-side** using data already returned by `runScan()` — no new backend endpoint required for v1.

---

## 3. R:R Computation Logic

### 3.1 Entry Price

```
entry = close
```

The entry price is the current close. For breakout setups, the entry is the **52-week high + 0.5%** (just above the breakout level):

```
entry = price_52_week_high * 1.005   if setupLabel ∈ ['Breakout Ready', 'Sector Leader']
entry = close                         otherwise
```

---

### 3.2 ATR-Based Stop Placement

Stop is placed at the **nearest structural support**, approximated as:

```
stop = entry − (atr_multiplier × atr_abs)
```

where:

| Variable | Source | Default |
|---|---|---|
| `atr_abs` | `close × (atr_pct / 100)` — derived from `atr_pct` already in scan data | — |
| `atr_multiplier` | User-configurable (1.0 to 3.0) | `1.5` |

**Structural refinement (optional v2):** Cross-check against `day_low` (intraday low) and `price_52_week_low`. If `entry − day_low < atr_abs`, use `day_low − (0.1% buffer)` as stop instead — this tightens the stop to the real structure.

```python
# Python equivalent — used in backend v2
atr_abs = close * (atr_pct / 100)
structural_stop = entry - (day_low * 0.001 if (entry - day_low) < atr_abs else atr_multiplier * atr_abs)
stop = max(structural_stop, entry * 0.85)   # floor: never risk more than 15%
```

---

### 3.3 Target Derivation

Target is derived from the **breakout target** (next resistance), approximated as:

```
target = price_52_week_high * (1 + target_extension_pct / 100)
```

where `target_extension_pct` defaults to `10` (10% above the 52-week high — typical breakout extension for large-cap NSE setups).

For non-breakout setups, use the **ATR projection**:

```
target = entry + (reward_multiplier × (entry − stop))
```

This ensures at least `reward_multiplier × 1 R` of reward even when the 52W high isn't a valid target. `reward_multiplier` defaults to `min_rr` so the target is set exactly at the threshold — the user can raise it.

---

### 3.4 R:R Ratio

```
risk   = entry − stop
reward = target − entry
rr     = reward / risk        (if risk > 0, else null)
```

A stock passes the filter if:

```
rr >= min_rr  AND  risk > 0  AND  reward > 0
```

Additional quality gates (all configurable):

| Gate | Default | Description |
|---|---|---|
| `min_rr` | `2.5` | Minimum reward-to-risk ratio |
| `max_risk_pct` | `7.0` | Maximum stop distance as % of entry — avoids wide, noisy stops |
| `min_atr_pct` | `1.0` | Minimum ATR% — filters illiquid, non-volatile stocks |
| `min_swing_score` | `5` | Minimum swing score — ensures setup quality |
| `min_rvol` | `0.8` | Minimum relative volume — ensures liquidity |

---

## 4. Backend Changes

### 4.1 No New Endpoint Required (v1)

All R:R computation is done **client-side** in JavaScript using fields already present in `stocksData`:

| Field Needed | Already in Scan? |
|---|---|
| `close` | ✅ |
| `atr_pct` | ✅ |
| `price_52_week_high` | ✅ |
| `day_low` | ✅ (as part of `day_range`) |
| `swingscore` | ✅ |
| `relative_volume` | ✅ |
| `setupLabel` | ✅ |

### 4.2 Optional Backend Pre-filter Endpoint (v2)

For faster rendering on large universes, add a dedicated endpoint:

```
POST /api/rr-screen
```

**Request body:**
```json
{
  "min_rr": 2.5,
  "atr_multiplier": 1.5,
  "target_extension_pct": 10.0,
  "max_risk_pct": 7.0,
  "min_swing_score": 5,
  "min_rvol": 0.8
}
```

**Response:**
```json
{
  "generated_at": "2026-05-30T09:30:00",
  "count": 14,
  "setups": [
    {
      "ticker": "CUMMINSIND",
      "entry": 3612.50,
      "stop": 3421.00,
      "target": 4100.00,
      "risk": 191.50,
      "reward": 487.50,
      "rr": 2.55,
      "risk_pct": 5.30,
      "atr_pct": 2.1,
      "swingscore": 8,
      "setupLabel": "Breakout Ready",
      "method": "52w_high_breakout"
    }
  ]
}
```

The handler iterates `universe_data` (already in memory from the last scan) and applies the same formulae as the JS client.

---

## 5. Frontend Changes

### 5.1 New Sub-tab: `R:R Setups`

Add a new tab button in `#screener-tabs`:

```html
<button class="tab-btn" data-tab="rr-setups">
  ⚖️ R:R Setups
  <span id="rr-setups-count" class="badge badge-sm" style="display:none;">0</span>
</button>
```

When active, show a dedicated container `#rr-setups-container` (replacing `#main-table-container`).

---

### 5.2 R:R Filter Control Bar

```html
<div id="rr-control-bar" class="rr-control-bar glass-panel">

  <div class="rr-control-group">
    <label class="rr-label">Min R:R</label>
    <input id="rr-min-input" type="number" min="1" max="10" step="0.5" value="2.5" class="rr-input" />
  </div>

  <div class="rr-control-group">
    <label class="rr-label">ATR Multiplier (Stop)</label>
    <input id="rr-atr-mult" type="number" min="0.5" max="3.0" step="0.25" value="1.5" class="rr-input" />
  </div>

  <div class="rr-control-group">
    <label class="rr-label">Target Extension (%)</label>
    <input id="rr-target-ext" type="number" min="3" max="30" step="1" value="10" class="rr-input" />
  </div>

  <div class="rr-control-group">
    <label class="rr-label">Max Risk (%)</label>
    <input id="rr-max-risk" type="number" min="2" max="15" step="0.5" value="7.0" class="rr-input" />
  </div>

  <div class="rr-control-group">
    <label class="rr-label">Min Swing Score</label>
    <input id="rr-min-swing" type="number" min="0" max="10" step="1" value="5" class="rr-input" />
  </div>

  <button id="btn-run-rr-screen" class="btn-primary">
    ⚡ Run R:R Screen
  </button>

  <span id="rr-result-summary" class="rr-result-summary"></span>

</div>
```

Persist all control values to `localStorage` key `rr_screen_prefs` on every change.

---

### 5.3 R:R Computation Module (`computeRRSetups`)

```js
/**
 * Evaluates every stock in the scan universe against the R:R filter.
 * Returns only passing stocks, sorted by R:R descending.
 *
 * @param {Object[]} stocks       - stocksData array from runScan()
 * @param {Object}   params       - filter parameters
 * @returns {Object[]}            - passing setups with computed fields
 */
function computeRRSetups(stocks, params) {
  const {
    minRR       = 2.5,
    atrMult     = 1.5,
    targetExt   = 10.0,
    maxRiskPct  = 7.0,
    minSwing    = 5,
    minRvol     = 0.8,
  } = params;

  const results = [];

  for (const s of stocks) {
    const close     = parseFloat(s.close);
    const atrPct    = parseFloat(s.atr_pct);
    const high52w   = parseFloat(s.price_52_week_high);
    const swingscore = parseFloat(s.swingscore) || 0;
    const rvol      = parseFloat(s.relative_volume) || 0;

    // Quality gates
    if (!close || !atrPct || !high52w) continue;
    if (swingscore < minSwing)         continue;
    if (rvol < minRvol)                continue;

    const atrAbs = close * (atrPct / 100);
    const isBreakout = ['Breakout Ready', 'Sector Leader'].includes(s.setupLabel);

    // Entry
    const entry = isBreakout ? high52w * 1.005 : close;

    // Stop — ATR-based with day_low structural refinement
    const dayLow = parseFloat(s.day_low) || (entry - atrAbs * atrMult);
    const atrStop = entry - (atrMult * atrAbs);
    const structStop = (entry - dayLow) < atrAbs ? dayLow * 0.999 : atrStop;
    const stop = Math.max(structStop, entry * 0.85); // 15% floor

    const risk = entry - stop;
    if (risk <= 0) continue;

    const riskPct = (risk / entry) * 100;
    if (riskPct > maxRiskPct) continue;

    // Target
    const breakoutTarget = high52w * (1 + targetExt / 100);
    const atrTarget      = entry + (minRR * risk);  // fallback: exactly at min_rr
    const target = isBreakout
      ? Math.max(breakoutTarget, atrTarget)
      : atrTarget;

    const reward = target - entry;
    if (reward <= 0) continue;

    const rr = reward / risk;
    if (rr < minRR) continue;

    results.push({
      ...s,
      rr_entry:   parseFloat(entry.toFixed(2)),
      rr_stop:    parseFloat(stop.toFixed(2)),
      rr_target:  parseFloat(target.toFixed(2)),
      rr_risk:    parseFloat(risk.toFixed(2)),
      rr_reward:  parseFloat(reward.toFixed(2)),
      rr_ratio:   parseFloat(rr.toFixed(2)),
      rr_risk_pct: parseFloat(riskPct.toFixed(2)),
      rr_method:  isBreakout ? '52w_breakout' : 'atr_projection',
    });
  }

  // Sort by R:R descending, cap at 20 results
  results.sort((a, b) => b.rr_ratio - a.rr_ratio);
  return results.slice(0, 20);
}
```

---

### 5.4 R:R Setups Table

Render results in `#rr-setups-container`:

```html
<div id="rr-setups-container" style="display:none;">
  <div id="rr-control-bar"><!-- see 5.2 --></div>

  <div id="rr-setups-empty" class="rr-empty-state" style="display:none;">
    <span>No setups meet the current R:R criteria. Try lowering Min R:R or relaxing the quality gates.</span>
  </div>

  <table id="rr-table" class="main-table" style="display:none;">
    <thead id="rr-table-head"></thead>
    <tbody id="rr-table-body"></tbody>
  </table>
</div>
```

**Columns:**

| Column | Value | Notes |
|---|---|---|
| Ticker | `clean_ticker` | Clickable → opens Trade Drawer pre-loaded with computed R:R values |
| Setup | `setupLabel` | Pill badge |
| Entry (₹) | `rr_entry` | Green if breakout entry, grey if at-close |
| Stop (₹) | `rr_stop` | Red, with risk% in parentheses |
| Target (₹) | `rr_target` | Green |
| Risk (₹) | `rr_risk` | |
| Reward (₹) | `rr_reward` | |
| **R:R** | `rr_ratio` | Bold; highlighted gold if ≥ 3.0, green if ≥ 2.5 |
| Method | `rr_method` | `52w_breakout` or `atr_projection` pill |
| Swing | `swingscore` | Existing badge |
| RVOL | `relative_volume` | |
| Action | Open Drawer | Button: `📐 Analyse` |

---

### 5.5 Trade Drawer Pre-population

When a stock row is opened from the R:R Setups table, pre-populate the Risk Calculator drawer with the computed values:

```js
function openTradeDrawerFromRR(stock) {
  // Open the drawer as normal
  openTradeDrawer(stock.clean_ticker);

  // After drawer renders, pre-fill the Risk Calculator fields
  setTimeout(() => {
    const entryEl  = document.getElementById('risk-entry');
    const stopEl   = document.getElementById('risk-stop');
    const targetEl = document.getElementById('risk-target');

    if (entryEl)  entryEl.value  = stock.rr_entry;
    if (stopEl)   stopEl.value   = stock.rr_stop;
    if (targetEl) targetEl.value = stock.rr_target;

    // Trigger recalculation
    const calcEvent = new Event('input', { bubbles: true });
    if (entryEl) entryEl.dispatchEvent(calcEvent);
  }, 300);
}
```

The drawer's existing R:R calculator then shows the pre-computed setup — the user can adjust any value and see the R:R update live.

---

### 5.6 Auto-Run on Scan Completion

After every `runScan()` completes and `stocksData` is updated, if the R:R Setups tab is active, automatically re-run the screen:

```js
// Inside runScan(), after stocksData is populated — append:
if (currentTab === 'rr-setups') {
  runRRScreen();
}
```

Also expose a manual re-run via the `⚡ Run R:R Screen` button.

---

### 5.7 `runRRScreen()` Orchestrator

```js
function runRRScreen() {
  const params = {
    minRR:      parseFloat(document.getElementById('rr-min-input')?.value)  || 2.5,
    atrMult:    parseFloat(document.getElementById('rr-atr-mult')?.value)   || 1.5,
    targetExt:  parseFloat(document.getElementById('rr-target-ext')?.value) || 10.0,
    maxRiskPct: parseFloat(document.getElementById('rr-max-risk')?.value)   || 7.0,
    minSwing:   parseFloat(document.getElementById('rr-min-swing')?.value)  || 5,
    minRvol:    0.8,
  };

  // Persist prefs
  localStorage.setItem('rr_screen_prefs', JSON.stringify(params));

  const setups = computeRRSetups(stocksData, params);

  // Update badge count on tab button
  const countBadge = document.getElementById('rr-setups-count');
  if (countBadge) {
    countBadge.textContent = setups.length;
    countBadge.style.display = setups.length > 0 ? 'inline-flex' : 'none';
  }

  // Summary line
  const summary = document.getElementById('rr-result-summary');
  if (summary) {
    summary.textContent = setups.length > 0
      ? `${setups.length} setup${setups.length > 1 ? 's' : ''} pass ≥${params.minRR}:1 R:R from ${stocksData.length} scanned`
      : `No setups pass ≥${params.minRR}:1 R:R`;
    summary.style.color = setups.length > 0 ? 'var(--color-success)' : 'var(--color-text-muted)';
  }

  renderRRTable(setups);
}
```

---

### 5.8 Preference Restore on Load

```js
// In DOMContentLoaded, after tab init:
const savedRRPrefs = JSON.parse(localStorage.getItem('rr_screen_prefs') || '{}');
if (savedRRPrefs.minRR)     document.getElementById('rr-min-input').value  = savedRRPrefs.minRR;
if (savedRRPrefs.atrMult)   document.getElementById('rr-atr-mult').value   = savedRRPrefs.atrMult;
if (savedRRPrefs.targetExt) document.getElementById('rr-target-ext').value = savedRRPrefs.targetExt;
if (savedRRPrefs.maxRiskPct)document.getElementById('rr-max-risk').value   = savedRRPrefs.maxRiskPct;
if (savedRRPrefs.minSwing)  document.getElementById('rr-min-swing').value  = savedRRPrefs.minSwing;
```

---

## 6. R:R Formula Reference

For a stock to appear in the shortlist, all three conditions must hold simultaneously:

\[
\text{R:R} = \frac{\text{Target} - \text{Entry}}{\text{Entry} - \text{Stop}} \geq \text{min\_rr}
\]

\[
\text{Risk\%} = \frac{\text{Entry} - \text{Stop}}{\text{Entry}} \times 100 \leq \text{max\_risk\_pct}
\]

\[
\text{Stop} \geq \text{Entry} \times 0.85 \quad \text{(15\% floor — prevents runaway stops)}
\]

---

## 7. Entry / Stop / Target Method Summary

| Setup Type | Entry | Stop | Target |
|---|---|---|---|
| Breakout Ready / Sector Leader | `52W_high × 1.005` | `entry − (ATR × mult)` or `day_low − 0.1%`, whichever is tighter | `52W_high × (1 + target_ext%)` |
| All other setups | `close` | `close − (ATR × mult)` | `entry + (min_rr × risk)` |
| Floor constraint | — | `max(stop, entry × 0.85)` | — |

---

## 8. Error Handling

| Scenario | Behaviour |
|---|---|
| `atr_pct` is null or 0 | Skip stock silently |
| `price_52_week_high` is null | Fall back to ATR projection method |
| `risk ≤ 0` after stop calculation | Skip stock silently |
| `stocksData` is empty when screen runs | Show `"Run a scan first"` message in the empty state |
| All 800+ stocks fail the filter | Show empty state with suggestion to lower `min_rr` or `min_swing` |

---

## 9. Acceptance Criteria

- [ ] R:R Setups tab appears in `#screener-tabs` and switches view correctly.
- [ ] `computeRRSetups()` correctly computes entry, stop, target, and R:R for all stocks in `stocksData`.
- [ ] Only stocks with `rr_ratio ≥ min_rr`, `risk_pct ≤ max_risk_pct`, `swingscore ≥ min_swing`, and `rvol ≥ 0.8` appear in results.
- [ ] Results are sorted by `rr_ratio` descending and capped at 20.
- [ ] Breakout setups use `52W_high × 1.005` as entry; all others use `close`.
- [ ] Opening a row from the R:R table pre-populates the Risk Calculator drawer with computed values.
- [ ] `⚡ Run R:R Screen` button re-computes results immediately.
- [ ] Screen auto-re-runs when `runScan()` completes and the R:R tab is active.
- [ ] All control values persist across page reloads via `localStorage`.
- [ ] Tab badge updates to show passing setup count after each run.
- [ ] Empty state shows helpful message when zero setups pass.

---

## 10. Implementation Order

1. **Tab scaffolding:** Add `rr-setups` tab button and `#rr-setups-container` HTML to `templates/index.html`. Wire tab switching in `app.js`.
2. **Control bar:** Add `#rr-control-bar` HTML with all five inputs and the Run button.
3. **`computeRRSetups()`:** Implement in `app.js` (or `static/js/rr-screen.js`). Unit-test with 3–4 manual stocks.
4. **`renderRRTable()`:** Implement table render with all columns.
5. **`runRRScreen()` orchestrator:** Wire button click and auto-run after scan.
6. **Drawer pre-population:** Implement `openTradeDrawerFromRR()` and wire to table row action button.
7. **Preference persistence:** Add `localStorage` save/restore for all five controls.
8. **CSS:** Add `.rr-control-bar`, `.rr-input`, `.rr-result-summary`, `.rr-empty-state` styles.
9. **Optional v2 — backend endpoint:** Implement `POST /api/rr-screen` if client-side performance becomes an issue at 1000+ stocks.

---

## 11. Related Files

| File | Change |
|---|---|
| `app.js` | `computeRRSetups()`, `renderRRTable()`, `runRRScreen()`, `openTradeDrawerFromRR()`, tab wiring, preference restore |
| `templates/index.html` | `rr-setups` tab button, `#rr-setups-container`, `#rr-control-bar`, `#rr-table` |
| `static/css/style.css` | R:R control bar, table column styles, R:R badge colouring, empty state |
| `app.py` | Optional: `POST /api/rr-screen` for server-side pre-filtering (v2) |

---

_Last updated: 2026-05-30_
