# SEBI Insider Trade & Promoter Pledge Tracker — Feature Spec

> **Feature ID:** `FEAT-006`  
> **Branch:** `feature/workspace-ui`  
> **Status:** 📋 Planned  
> **Priority:** High  
> **Component:** Fundamental Signals Engine + Screener Table + Trade Drawer

---

## 1. Overview

Build a disclosure-tracking layer that ingests promoter and insider-related filings from NSE/BSE/SEBI disclosure feeds and converts them into two high-signal screener annotations:

- **🚨 Promoter Risk** — shown when recent disclosures indicate pledge creation/invocation, promoter shareholding reduction, or adverse SAST activity.
- **🟢 Insider Buying** — shown when recent insider/promoter purchase disclosures indicate meaningful accumulation.

The goal is to add a **fundamental catalyst overlay** to the existing technical screener so that trade candidates are not evaluated only on price and momentum, but also on promoter behavior and insider conviction.

---

## 2. Goals

- Track three disclosure families: **promoter pledge**, **promoter shareholding change**, and **SAST / insider trading disclosures**.
- Normalize raw NSE/BSE filing data into a unified, ticker-mapped event model.
- Tag every stock in the screener with the latest promoter/insider signal, if any.
- Add filter chips so users can instantly isolate `Promoter Risk`, `Insider Buying`, or `No Recent Signal` names.
- Surface full disclosure details in the **Trade Drawer** with date, filing type, quantity/percent change, and source link.
- Cache filings locally so scans stay fast and the scraper does not repeatedly hit exchange endpoints.

---

## 3. Signals and Rules

### 3.1 Promoter Risk Signal

A stock receives the **🚨 Promoter Risk** badge when **any** of the following occurs within the lookback window:

| Trigger | Rule | Severity |
|---|---|---|
| Pledge creation | New pledge created or pledged promoter shares % increases vs previous filing | High |
| Pledge invocation | Filing explicitly mentions invocation / encumbrance enforcement | High |
| Promoter holding reduction | Promoter holding decreases by `≥ 0.25%` absolute in a quarter or via market transaction | Medium |
| Adverse SAST event | Open-market/promoter exit style SAST filing with net seller classification | Medium |

**Default lookback:** `90 days`

**Notification text examples:**
- `"PROMOTER RISK: ABCL — promoter pledge increased to 12.4%"`
- `"PROMOTER RISK: XYZ — promoter holding fell by 0.42%"`

---

### 3.2 Insider Buying Signal

A stock receives the **🟢 Insider Buying** signal when the system detects net positive insider/promoter accumulation over the lookback window.

| Trigger | Rule | Strength |
|---|---|---|
| Promoter market purchase | Net promoter acquisition > 0 over lookback | Strong |
| Insider purchase | Director/KMP/promoter group buy transactions exceed sell transactions | Medium |
| SAST accumulation | Acquirer/promoter holding rises through disclosed acquisition | Strong |

**Minimum signal filters:**

| Field | Default |
|---|---|
| `min_trade_value` | ₹25 lakh |
| `min_holding_delta_pct` | `0.05%` |
| `lookback_days` | `90` |

**Notification text examples:**
- `"INSIDER BUYING: CUMMINSIND — promoter group bought ₹2.3 Cr in last 30d"`
- `"INSIDER BUYING: ABC — disclosed holding rose 0.18%"`

---

### 3.3 Neutral / No Signal

If no qualifying disclosure exists in the lookback period, the stock shows no badge by default. An optional muted badge can be shown in the drawer as:

- `No recent insider/promoter signal`

---

## 4. Data Sources

### 4.1 Source Categories

| Source | Type | Use |
|---|---|---|
| NSE corporate disclosures | Exchange filings | Pledge, promoter shareholding, insider trades |
| BSE corporate announcements | Exchange filings | Cross-check / fallback for disclosures missed by NSE |
| SEBI SAST / PIT disclosures | Regulatory filings | Acquisitions, disposals, insider trade reports |
| Quarterly shareholding pattern filings | Holdings snapshot | Promoter holding delta calculation |

### 4.2 File Types to Parse

The scraper should target documents/feeds whose metadata or title contains keywords such as:

- `pledge`
- `encumbrance`
- `promoter shareholding`
- `shareholding pattern`
- `regulation 7(2)`
- `PIT`
- `SAST`
- `regulation 29`
- `insider trading`
- `promoter group`

Because source titles are inconsistent, event classification must rely on both **document title keywords** and **parsed body content** where available.

---

## 5. Normalized Event Model

Create a normalized disclosure record so all downstream UI logic reads one consistent shape.

```json
{
  "ticker": "RELIANCE",
  "company_name": "Reliance Industries Ltd",
  "source": "NSE",
  "source_url": "https://...",
  "event_type": "pledge_change",
  "event_subtype": "pledge_increase",
  "signal": "promoter_risk",
  "signal_strength": "high",
  "filed_at": "2026-05-29T14:32:00",
  "effective_date": "2026-05-28",
  "actor_name": "Promoter Group",
  "actor_type": "promoter_group",
  "trade_action": "increase",
  "holding_before_pct": 49.12,
  "holding_after_pct": 48.70,
  "holding_delta_pct": -0.42,
  "pledged_before_pct": 8.10,
  "pledged_after_pct": 12.40,
  "pledged_delta_pct": 4.30,
  "trade_value_inr": 23000000,
  "quantity": 145000,
  "summary": "Promoter pledged shares increased from 8.1% to 12.4% of promoter holding.",
  "raw_title": "Disclosure under Regulation 31(4) of SEBI SAST Regulations",
  "raw_text_excerpt": "..."
}
```

---

## 6. Backend Changes

### 6.1 New SQLite Tables

```sql
CREATE TABLE IF NOT EXISTS insider_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    company_name TEXT,
    source TEXT NOT NULL,
    source_url TEXT,
    event_type TEXT NOT NULL,
    event_subtype TEXT,
    signal TEXT,
    signal_strength TEXT,
    filed_at TEXT NOT NULL,
    effective_date TEXT,
    actor_name TEXT,
    actor_type TEXT,
    trade_action TEXT,
    holding_before_pct REAL,
    holding_after_pct REAL,
    holding_delta_pct REAL,
    pledged_before_pct REAL,
    pledged_after_pct REAL,
    pledged_delta_pct REAL,
    trade_value_inr REAL,
    quantity REAL,
    summary TEXT,
    raw_title TEXT,
    raw_text_excerpt TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(ticker, source, source_url, event_type, filed_at)
);
```

```sql
CREATE TABLE IF NOT EXISTS insider_signal_cache (
    ticker TEXT PRIMARY KEY,
    signal TEXT,
    signal_strength TEXT,
    last_event_type TEXT,
    last_event_date TEXT,
    badge_text TEXT,
    summary TEXT,
    source_url TEXT,
    updated_at TEXT NOT NULL
);
```

`insider_events` stores the full event history. `insider_signal_cache` stores the latest resolved badge per ticker for fast screener rendering.

---

### 6.2 New Scraper Job

Add a background ingestion job:

```python
def refresh_insider_and_promoter_signals(days_back=90):
    """
    Pulls recent NSE/BSE/SEBI disclosure metadata, classifies events,
    stores normalized rows in insider_events, and refreshes insider_signal_cache.
    """
```

**Job stages:**

1. Fetch recent disclosure lists from NSE/BSE/SEBI endpoints.
2. Filter titles by relevant keywords.
3. Download linked PDF/HTML/text disclosures where needed.
4. Extract text using the existing parsing utility stack (PDF text extraction if available).
5. Map company name / symbol to screener ticker.
6. Classify into `pledge_change`, `promoter_holding_change`, `insider_buy`, `insider_sell`, `sast_accumulation`, etc.
7. Upsert into `insider_events`.
8. Resolve latest signal per ticker and upsert `insider_signal_cache`.

**Execution cadence:**
- On app startup: soft refresh once.
- During market hours: every `4 hours`.
- Manual admin refresh button for debugging.

---

### 6.3 Signal Resolver

```python
def resolve_latest_insider_signal(ticker, lookback_days=90):
    """
    Reads insider_events for a ticker and returns the highest-priority active signal.
    Priority:
      1. pledge invocation / pledge increase
      2. promoter holding reduction
      3. insider/promoter buying
      4. none
    """
```

**Priority rules:**

| Condition | Output badge |
|---|---|
| Any active high-severity promoter risk event | `🚨 Promoter Risk` |
| Else any qualifying insider/promoter buying event | `🟢 Insider Buying` |
| Else none | `null` |

If both buying and risk exist in the same window, **Promoter Risk wins** in the screener badge. The drawer still shows both events in the timeline.

---

### 6.4 Optional API Endpoints

#### Get latest badge data for the full universe

```
GET /api/insider-signals
```

**Response:**
```json
{
  "generated_at": "2026-05-30T14:00:00",
  "signals": {
    "RELIANCE": {
      "signal": "promoter_risk",
      "signal_strength": "high",
      "badge_text": "🚨 Promoter Risk",
      "summary": "Promoter pledged shares increased to 12.4%",
      "last_event_date": "2026-05-29",
      "source_url": "https://..."
    },
    "CUMMINSIND": {
      "signal": "insider_buying",
      "signal_strength": "strong",
      "badge_text": "🟢 Insider Buying",
      "summary": "Promoter group acquired ₹2.3 Cr shares",
      "last_event_date": "2026-05-27",
      "source_url": "https://..."
    }
  }
}
```

#### Get detailed history for one ticker

```
GET /api/insider-signals/<ticker>?days=180
```

Returns the cached latest badge plus a chronological event list for the drawer.

---

## 7. Frontend Changes

### 7.1 Screener Table Badge Column

Add a new optional column to `masterColumnsConfig.overview`:

```js
{ 
  id: 'insider_signal',
  name: 'Promoter / Insider',
  sortField: 'insider_signal_strength_rank',
  isVisible: true,
  align: 'center',
  canToggle: true,
  tooltip: 'Recent promoter pledge, shareholding, or insider trade signal derived from NSE/BSE/SEBI disclosures.'
}
```

**Display rules:**

| Signal | Badge |
|---|---|
| `promoter_risk` | `<span class="badge badge-risk">🚨 Promoter Risk</span>` |
| `insider_buying` | `<span class="badge badge-insider-buy">🟢 Insider Buying</span>` |
| none | `—` |

Each row should also expose a tooltip with the short summary and event date.

---

### 7.2 Filter Chips

Add disclosure-aware filter chips near the existing setup filters:

```html
<div id="insider-filter-chips" class="filter-chip-group">
  <button class="filter-chip active" data-value="all">All Signals</button>
  <button class="filter-chip" data-value="promoter_risk">🚨 Promoter Risk</button>
  <button class="filter-chip" data-value="insider_buying">🟢 Insider Buying</button>
  <button class="filter-chip" data-value="none">No Signal</button>
</div>
```

Hook this into `filterAndRender()`:

```js
if (currentInsiderFilter === 'promoter_risk') {
  rows = rows.filter(s => s.insider_signal === 'promoter_risk');
} else if (currentInsiderFilter === 'insider_buying') {
  rows = rows.filter(s => s.insider_signal === 'insider_buying');
} else if (currentInsiderFilter === 'none') {
  rows = rows.filter(s => !s.insider_signal);
}
```

---

### 7.3 Trade Drawer Section

Add a new disclosure panel in the trade drawer:

```html
<div id="drawer-insider-section" class="drawer-section" style="display:none;">
  <div class="drawer-section-header">
    <span>🏛️ Promoter / Insider Activity</span>
    <a id="drawer-insider-source-link" href="#" target="_blank" rel="noopener">Open Filing</a>
  </div>

  <div id="drawer-insider-badge-row"></div>
  <div id="drawer-insider-summary" class="drawer-muted-text"></div>

  <div id="drawer-insider-timeline"></div>
</div>
```

Each timeline item:

```html
<div class="insider-event-row insider-event-row--risk">
  <div class="insider-event-date">2026-05-29</div>
  <div class="insider-event-body">
    <div class="insider-event-title">Pledge Increase</div>
    <div class="insider-event-summary">Promoter pledged shares rose from 8.1% to 12.4%</div>
  </div>
</div>
```

The drawer shows the **latest badge on top** and up to the last `5` events below it.

---

### 7.4 App State Additions

```js
let insiderSignalsMap = {};          // latest badge per ticker
let insiderSignalHistoryCache = {};  // drawer history cache per ticker
let currentInsiderFilter = 'all';
```

Load latest signals after scan completion:

```js
async function loadInsiderSignals() {
  try {
    const res = await fetch('/api/insider-signals');
    const data = await res.json();
    insiderSignalsMap = data.signals || {};

    stocksData = stocksData.map(s => {
      const sig = insiderSignalsMap[s.clean_ticker] || null;
      return {
        ...s,
        insider_signal: sig?.signal || null,
        insider_signal_strength: sig?.signal_strength || null,
        insider_signal_badge: sig?.badge_text || null,
        insider_signal_summary: sig?.summary || null,
        insider_signal_date: sig?.last_event_date || null,
        insider_signal_source_url: sig?.source_url || null,
        insider_signal_strength_rank: sig?.signal === 'promoter_risk' ? 2 : sig?.signal === 'insider_buying' ? 1 : 0,
      };
    });

    filterAndRender();
  } catch (err) {
    console.error('Failed to load insider signals:', err);
  }
}
```

Call `loadInsiderSignals()` at the end of `runScan()`.

---

## 8. Classification Rules

### 8.1 Rule Table

| Parsed event | Condition | Output signal |
|---|---|---|
| `pledge_change` | `pledged_delta_pct > 0` | `promoter_risk` |
| `pledge_invocation` | always | `promoter_risk` |
| `promoter_holding_change` | `holding_delta_pct <= -0.25` | `promoter_risk` |
| `insider_trade` | `trade_action = buy` and `trade_value_inr >= 25L` | `insider_buying` |
| `sast_accumulation` | `holding_delta_pct > 0.05` | `insider_buying` |
| `insider_trade` | sell only | no badge by default (history only) |

### 8.2 Signal Strength

| Signal | Strength Rule |
|---|---|
| `promoter_risk` | `high` for pledge invocation or pledge increase > 2%; `medium` otherwise |
| `insider_buying` | `strong` for promoter buys or > ₹1 Cr; `medium` otherwise |

---

## 9. Caching Strategy

| Layer | TTL | Purpose |
|---|---|---|
| Raw disclosure fetch cache | 4 hours | Avoid repeated download of the same exchange pages/files |
| `insider_events` DB | Persistent | Historical record of all parsed events |
| `insider_signal_cache` DB | Refreshed every scrape | Fast screener badge lookup |
| Frontend `insiderSignalHistoryCache` | Session | Avoid repeated drawer fetches |

---

## 10. Error Handling

| Scenario | Behaviour |
|---|---|
| Source feed unreachable | Keep last cached signals; log warning |
| PDF parse fails | Store metadata-only event with `raw_title`; skip numeric extraction |
| Company name cannot map to ticker | Store raw event in staging log; do not display in screener |
| Both risk and buying signals exist | Screener shows `🚨 Promoter Risk`; drawer shows full mixed history |
| No recent filing | No badge shown |

---

## 11. Acceptance Criteria

- [ ] A scraper job ingests recent NSE/BSE/SEBI disclosure metadata and stores normalized rows in `insider_events`.
- [ ] Latest ticker-level badge state is materialized in `insider_signal_cache`.
- [ ] Screener table displays `🚨 Promoter Risk` and `🟢 Insider Buying` badges correctly.
- [ ] Filter chips isolate `Promoter Risk`, `Insider Buying`, and `No Signal` tickers.
- [ ] Trade Drawer shows latest badge, summary, source link, and recent event timeline.
- [ ] `Promoter Risk` overrides `Insider Buying` in the main screener when both are active.
- [ ] App continues functioning when source feeds fail, using cached DB values.
- [ ] Badge data loads fast enough to not materially slow `runScan()` rendering.

---

## 12. Implementation Order

1. **DB schema:** Add `insider_events` and `insider_signal_cache` tables in `init_db()`.
2. **Scraper skeleton:** Create `refresh_insider_and_promoter_signals()` in `app.py` or a dedicated `signals/insider.py` module.
3. **Source adapters:** Add fetchers for NSE, BSE, and SEBI disclosure lists.
4. **Parser/classifier:** Normalize titles/text into event rows and compute signal outputs.
5. **Cache resolver:** Implement `resolve_latest_insider_signal()` and materialize `insider_signal_cache`.
6. **API endpoints:** Add `GET /api/insider-signals` and `GET /api/insider-signals/<ticker>`.
7. **Frontend load:** Add `loadInsiderSignals()` and merge badge state into `stocksData`.
8. **Screener UI:** Add the new table column and filter chips.
9. **Trade Drawer UI:** Add the promoter/insider activity section with timeline rendering.
10. **Polish:** Tooltip summaries, badge colours, and stale-cache fallback messaging.

---

## 13. Related Files

| File | Change |
|---|---|
| `app.py` | DB schema, scraper scheduler hook, signal resolver, API endpoints |
| `signals/insider.py` _(new)_ | Exchange adapters, parsing, normalization, classification |
| `templates/index.html` | Screener badge column, insider filter chips, drawer section |
| `static/js/app.js` | `loadInsiderSignals()`, filter integration, drawer rendering |
| `static/css/style.css` | Badge colours, filter chip styles, drawer timeline styles |

---

_Last updated: 2026-05-30_
