# Smart Alert Engine — Feature Spec

> **Feature ID:** `FEAT-003`  
> **Branch:** `feature/workspace-ui`  
> **Status:** 📋 Planned  
> **Priority:** High  
> **Component:** Screener Engine + Watchlist Center + Browser Notifications

---

## 1. Overview

A rule-based background alert system that continuously evaluates a set of predefined conditions after every scan cycle and fires **browser push notifications** when a meaningful signal is detected.

The engine targets four alert categories:

1. **Regime Score Delta** — a stock's regime score jumps ≥ 15 points in a single session.
2. **Swing Score Flip** — a stock transitions from a swing score `< 6` to `≥ 8` (weak → strong/elite).
3. **Kronos Forecast Spike** — Kronos predicts `> 5%` return in the next 5 days.
4. **Bulk/Block Deal Detection** — a deal appears for a stock that exists in any watchlist section.

Notifications are non-intrusive, actionable, and respect the browser's `Notification` permission model already in use.

---

## 2. Goals

- Zero-config alert firing — alerts are active by default for all watchlist stocks; users can opt-out per category.
- Leverage the **existing scan loop** (`runScan()`) as the trigger — no separate polling timer needed.
- Reuse `computeScanDelta()` infrastructure for swing/regime comparisons.
- Reuse `loadedDeals` (NSE Block/Bulk Deals) already fetched in the Watchlist Center for deal detection.
- Surface all fired alerts in a **persistent in-session Alert Log** panel so nothing is missed if the browser tab is not in focus.

---

## 3. Alert Rules

### 3.1 Regime Score Delta Alert

| Property | Value |
|---|---|
| Trigger | `regimeScore` (current session) − `regimeScore` (previous session snapshot) `≥ 15` |
| Data source | `marketBreadth.regimeScore` (current) vs `breadthHistory[1].regimeScore` (previous snapshot from `/api/breadth-history`) |
| Fires once per | Session (not re-fired until score drops and recovers) |
| Notification body | `"Market Regime jumped ▲{delta} → {newBand} ({newScore}/100)"` |

**Deduplication key:** `regime_delta_{date}_{score}` stored in `sessionStorage`.

---

### 3.2 Swing Score Flip Alert

| Property | Value |
|---|---|
| Trigger | Previous `swingscore < 6` **AND** new `swingscore ≥ 8` for the same ticker |
| Data source | `previousScanMap[ticker].swingscore` vs `stocksData[ticker].swingscore` |
| Fires for | Watchlist stocks only (checked against `watchlistStocks`) |
| Notification body | `"{ticker} Swing Score flipped → {newScore}/10 ({newBand})"` |

**Deduplication key:** `swing_flip_{ticker}_{date}` stored in `sessionStorage`.

---

### 3.3 Kronos Forecast Spike Alert

| Property | Value |
|---|---|
| Trigger | `predicted_return_pct > 5.0` from the Kronos ranking response for a watchlist stock |
| Data source | `watchlistKronosRankings[ticker].predicted_return_pct` (populated by `btn-kronos-batch-sort`) |
| Fires for | Watchlist stocks only |
| Notification body | `"{ticker} Kronos forecast: +{pct}% in 5d ({bias})"` |

**Deduplication key:** `kronos_spike_{ticker}_{date}` stored in `sessionStorage`.

> **Note:** This alert fires after a **Kronos Batch Sort** completes, not on every scan — Kronos inference is not part of the real-time scan loop.

---

### 3.4 Bulk/Block Deal Alert

| Property | Value |
|---|---|
| Trigger | A new entry appears in `loadedDeals` whose `symbol` matches a stock in any `watchlistSections` |
| Data source | `loadedDeals` array (fetched via `/api/nse-deals`) + `watchlistStocks` flat array |
| Fires for | Watchlist stocks only |
| Notification body | `"Deal alert: {dealType} in {ticker} — {qty} shares @ ₹{price} by {client}"` |

**Deduplication key:** `deal_{ticker}_{tradeDate}_{client}` stored in `sessionStorage`.

---

## 4. Backend Changes

### 4.1 No New Endpoints Required

All four alert types are evaluated **client-side** using data already available:

| Alert | Data Already Available |
|---|---|
| Regime Delta | `marketBreadth` (live) + `/api/breadth-history` (already called by `renderBreadthTrendSparkline`) |
| Swing Flip | `previousScanMap` + `stocksData` (populated every `runScan()`) |
| Kronos Spike | `watchlistKronosRankings` (populated by batch sort) |
| Deal | `loadedDeals` (populated by `renderDeals()` in the Watchlist Center) |

### 4.2 Optional: Alert Persistence Endpoint

To persist fired alerts across page refreshes, a lightweight endpoint can be added:

```
POST /api/alerts/log
GET  /api/alerts/log?limit=50
```

**Request body (`POST`):**
```json
{
  "type": "swing_flip",
  "ticker": "RELIANCE",
  "message": "RELIANCE Swing Score flipped → 8/10 (Strong)",
  "fired_at": "2026-05-30T14:35:00"
}
```

This is **optional for v1** — `sessionStorage` is sufficient for within-session deduplication.

---

## 5. Frontend Changes

### 5.1 `AlertEngine` Module (`static/js/alerts.js`)

Create a new file `static/js/alerts.js` with the following structure:

```js
const AlertEngine = (() => {
  const DEDUP_PREFIX = 'alert_fired_';
  const today = () => new Date().toISOString().slice(0, 10);

  function _canFire(key) {
    const dedupKey = DEDUP_PREFIX + key;
    if (sessionStorage.getItem(dedupKey)) return false;
    sessionStorage.setItem(dedupKey, '1');
    return true;
  }

  function _fire(title, body, type = 'info') {
    // 1. Browser push notification
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(title, { body, icon: '/static/favicon.ico' });
    }
    // 2. Append to in-session alert log
    appendToAlertLog({ title, body, type, firedAt: new Date().toISOString() });
  }

  function checkRegimeDelta(currentScore, historyArr) {
    if (!historyArr || historyArr.length < 2) return;
    const prevScore = historyArr[1]?.regimeScore ?? currentScore;
    const delta = currentScore - prevScore;
    if (delta >= 15) {
      const key = `regime_delta_${today()}_${currentScore}`;
      if (_canFire(key)) {
        _fire(
          'Market Regime Surge',
          `Regime jumped ▲${delta} → ${marketBreadth.regimeBand} (${currentScore}/100)`,
          'bullish'
        );
      }
    }
  }

  function checkSwingFlips(prevMap, currentStocks, watchlistSymbols) {
    currentStocks.forEach(stock => {
      if (!watchlistSymbols.has(stock.clean_ticker)) return;
      const prev = prevMap[stock.clean_ticker];
      if (!prev) return;
      if (prev.swingscore < 6 && stock.swingscore >= 8) {
        const key = `swing_flip_${stock.clean_ticker}_${today()}`;
        if (_canFire(key)) {
          _fire(
            `Swing Flip: ${stock.clean_ticker}`,
            `${stock.clean_ticker} Swing Score flipped → ${stock.swingscore}/10 (${stock.swingband})`,
            'swing'
          );
        }
      }
    });
  }

  function checkKronosSpikes(rankings, watchlistSymbols) {
    Object.entries(rankings).forEach(([ticker, data]) => {
      if (!watchlistSymbols.has(ticker)) return;
      if ((data.predicted_return_pct ?? 0) > 5.0) {
        const key = `kronos_spike_${ticker}_${today()}`;
        if (_canFire(key)) {
          _fire(
            `Kronos Spike: ${ticker}`,
            `${ticker} Kronos forecast: +${data.predicted_return_pct.toFixed(2)}% in 5d (${data.ai_forecast_bias})`,
            'kronos'
          );
        }
      }
    });
  }

  function checkDeals(deals, watchlistSymbols) {
    deals.forEach(deal => {
      const sym = (deal.symbol || '').replace(/[^A-Z0-9]/gi, '').toUpperCase();
      if (!watchlistSymbols.has(sym)) return;
      const key = `deal_${sym}_${deal.trade_date}_${deal.client_name}`;
      if (_canFire(key)) {
        _fire(
          `Deal Alert: ${sym}`,
          `${deal.deal_type} — ${deal.quantity?.toLocaleString('en-IN')} shares @ ₹${deal.trade_price} by ${deal.client_name}`,
          'deal'
        );
      }
    });
  }

  return { checkRegimeDelta, checkSwingFlips, checkKronosSpikes, checkDeals };
})();
```

---

### 5.2 Integration Points

| Where | What to Call |
|---|---|
| End of `runScan()` — after `stocksData` and `marketBreadth` are updated | `AlertEngine.checkSwingFlips(previousScanMap, stocksData, watchlistSymbolsSet)` |
| End of `renderBreadthTrendSparkline()` — after `history` is fetched | `AlertEngine.checkRegimeDelta(marketBreadth.regimeScore, history)` |
| End of Kronos batch sort `try` block — after `watchlistKronosRankings` is populated | `AlertEngine.checkKronosSpikes(watchlistKronosRankings, watchlistSymbolsSet)` |
| End of `renderDeals()` — after `loadedDeals` is populated | `AlertEngine.checkDeals(loadedDeals, watchlistSymbolsSet)` |

**`watchlistSymbolsSet`** — derive once using:
```js
const watchlistSymbolsSet = new Set(watchlistStocks.map(s => s.ticker));
```

---

### 5.3 Alert Log Panel

Add a collapsible **Alert Log** panel in the Dashboard workspace sidebar (below the Regime Banner):

```html
<div id="alert-log-panel" class="glass-panel">
  <div class="alert-log-header">
    <span>🔔 Alert Log</span>
    <span id="alert-log-count" class="badge">0</span>
    <button id="btn-clear-alerts" class="btn-ghost btn-xs">Clear</button>
  </div>
  <div id="alert-log-body">
    <!-- Populated by appendToAlertLog() -->
  </div>
</div>
```

Each log entry:
```html
<div class="alert-log-entry alert-log-entry--{type}">
  <span class="alert-log-time">{HH:MM:SS}</span>
  <span class="alert-log-title">{title}</span>
  <span class="alert-log-body">{body}</span>
</div>
```

Alert type → CSS class mapping:

| Type | Class modifier | Accent |
|---|---|---|
| `bullish` | `--bullish` | `--color-success` (green) |
| `swing` | `--swing` | `--accent-teal` |
| `kronos` | `--kronos` | `--accent-amber` (gold) |
| `deal` | `--deal` | `--accent-orange` |
| `info` | `--info` | `--color-text-secondary` |

---

### 5.4 Alert Settings Toggle

Add an **Alert Settings** section under the ⚙️ settings panel (or a small gear icon next to "Alert Log"):

```
☑ Regime Score Delta alerts
☑ Swing Score Flip alerts  
☑ Kronos Forecast Spike alerts
☑ Bulk/Block Deal alerts
```

Persist preferences to `localStorage` under key `alert_settings`:
```json
{
  "regime": true,
  "swing": true,
  "kronos": true,
  "deals": true
}
```

Each `_canFire()` call should additionally check the relevant setting before firing.

---

## 6. Notification Permission Flow

The app already requests permission on `DOMContentLoaded`. No change needed. The alert engine should gracefully degrade if permission is `denied` — alerts are still appended to the Alert Log panel, just not delivered as OS-level push notifications.

```js
// Already in app.js — no change required
if ("Notification" in window && Notification.permission !== "granted" && Notification.permission !== "denied") {
    Notification.requestPermission();
}
```

---

## 7. Deduplication Strategy

All deduplication is handled via `sessionStorage` keyed by `alert_fired_{ruleKey}`. Keys expire automatically when the browser tab/session closes.

| Alert | Dedup Key Pattern | Fires Again When |
|---|---|---|
| Regime Delta | `regime_delta_{date}_{score}` | Score drops then hits a new ≥15 delta |
| Swing Flip | `swing_flip_{ticker}_{date}` | Next trading day |
| Kronos Spike | `kronos_spike_{ticker}_{date}` | Next trading day or after a fresh Kronos batch run |
| Deal | `deal_{ticker}_{tradeDate}_{client}` | New deal from a different client or on a different date |

---

## 8. Error Handling

| Scenario | Behaviour |
|---|---|
| `Notification.permission === 'denied'` | Log to Alert Log panel only; no OS notification |
| `breadth-history` returns `< 2` snapshots | Regime delta check skipped silently |
| `watchlistStocks` is empty | All watchlist-scoped checks short-circuit immediately |
| Kronos rankings not yet populated | `checkKronosSpikes` called with empty `{}` — no-op |
| Deal API unavailable | `loadedDeals` is `[]` — deal check is a no-op |

---

## 9. Acceptance Criteria

- [ ] Regime delta alert fires once per session when `regimeScore` delta `≥ 15` vs previous snapshot.
- [ ] Swing flip alert fires for a watchlist stock transitioning from `swingscore < 6` to `≥ 8`.
- [ ] Kronos spike alert fires after a batch sort for any watchlist stock with `predicted_return_pct > 5.0`.
- [ ] Deal alert fires when `loadedDeals` contains a match for any watchlist stock.
- [ ] No alert fires more than once per session per dedup key.
- [ ] All alerts appear in the Alert Log panel regardless of OS notification permission.
- [ ] Alert settings checkboxes correctly suppress individual alert categories.
- [ ] Alerts gracefully no-op when source data is unavailable (empty arrays, null scores).

---

## 10. Implementation Order

1. **Create `static/js/alerts.js`** with the `AlertEngine` module and `appendToAlertLog()` helper.
2. **Add Alert Log panel HTML** to `templates/index.html` in the Dashboard sidebar.
3. **Add CSS** for `.alert-log-entry` variants in `static/css/style.css`.
4. **Wire `checkSwingFlips`** into `runScan()` (already has access to `previousScanMap` and `stocksData`).
5. **Wire `checkRegimeDelta`** into `renderBreadthTrendSparkline()` after history fetch.
6. **Wire `checkKronosSpikes`** into the Kronos batch sort `try` block.
7. **Wire `checkDeals`** into `renderDeals()` after `loadedDeals` is populated.
8. **Add alert settings UI** and hook into `_canFire()`.
9. **Test all four alert types** in sequence using mock data overrides.

---

## 11. Related Files

| File | Change |
|---|---|
| `static/js/alerts.js` | New file — `AlertEngine` module |
| `static/js/app.js` | Wire alert checks into `runScan()`, `renderBreadthTrendSparkline()`, Kronos batch sort handler, `renderDeals()` |
| `templates/index.html` | Alert Log panel, alert settings toggles |
| `static/css/style.css` | `.alert-log-entry` variants, `.alert-log-panel` layout |
| `app.py` | Optional: `POST/GET /api/alerts/log` for cross-session persistence |

---

_Last updated: 2026-05-30_
