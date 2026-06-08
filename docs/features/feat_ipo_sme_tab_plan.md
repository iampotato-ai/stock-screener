# FEAT-IPO: IPO & SME Momentum Tab — Implementation Plan

**Feature:** Dedicated IPO / SME screener tab tracking post-listing momentum for recently listed NSE/BSE stocks  
**Target Repo:** `iampotato-ai/stock-screener`  
**Estimated Effort:** ~3–4 days (backend) + ~2 days (frontend)  
**Priority:** Medium-High (flagship differentiator — most Indian retail screeners lack real IPO tracking)

---

## Overview

Most screeners lump IPOs into the general universe and let them sink without trace. This tab surfaces **every stock listed in the last 12 months** (NSE + BSE mainboard + SME), computes post-listing momentum metrics specific to newly-listed equities, and provides a clean workflow for swing traders to identify the "momentum window" (typically days 3–60 post-listing) before an IPO stabilises into the regular universe.

---

## Phase 1 — Data Sourcing & Backend

### 1.1 IPO Universe Fetch

NSE and BSE publish listing data publicly. Two reliable free sources:

- **NSE `/api/marketStatus`** and **`/api/live-analysis-data`** — used for live price, but not historical IPO dates
- **BSE `/corporates/shaze/shaze_data.aspx`** — BSE IPO listing calendar (publicly accessible JSON endpoint)
- **Yahoo Finance `info` dict** — `ipoExpectedDate`, `firstTradeDateEpochUtc` fields available via `yfinance`
- **Fallback/primary:** Maintain a local DB table `ipo_listings` seeded by a weekly scrape of the [NSE IPO page](https://www.nseindia.com/market-data/all-upcoming-ipos) and [BSE IPO list](https://www.bseindia.com/markets/PublicIssues/IPONewListing.aspx)

**DB Schema — `ipo_listings` table:**

```sql
CREATE TABLE IF NOT EXISTS ipo_listings (
    ticker          TEXT PRIMARY KEY,          -- e.g. "ZOMATO.NS"
    company_name    TEXT NOT NULL,
    listing_date    TEXT NOT NULL,             -- ISO date "YYYY-MM-DD"
    issue_price     REAL,                      -- IPO offer price in ₹
    listing_open    REAL,                      -- Opening price on listing day
    listing_close   REAL,                      -- Close price on listing day
    exchange        TEXT DEFAULT 'NSE',        -- 'NSE', 'BSE', 'SME-NSE', 'SME-BSE'
    sector          TEXT,
    issue_size_cr   REAL,                      -- Issue size in ₹ crore
    lot_size        INTEGER,
    gmp_at_listing  REAL,                      -- Grey Market Premium on listing day (optional)
    added_at        TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ipo_listing_date ON ipo_listings(listing_date DESC);
CREATE INDEX IF NOT EXISTS idx_ipo_exchange ON ipo_listings(exchange);
```

### 1.2 Weekly Auto-Seeding Script

Add `seed_ipo_listings()` function in `app.py`:

```python
def seed_ipo_listings():
    """
    Scrapes BSE/NSE IPO listing pages weekly and inserts new listings into ipo_listings.
    Called on app startup and scheduled via APScheduler every Monday 09:00 IST.
    """
    # Step 1: Fetch BSE recent listings JSON
    # Step 2: For each listing, resolve ticker via yfinance search or NSE symbol lookup
    # Step 3: INSERT OR IGNORE into ipo_listings
    # Step 4: For listings without issue_price/listing_open, enrich via yfinance .history()
    pass
```

Schedule in `app.py` startup block:
```python
scheduler.add_job(seed_ipo_listings, 'cron', day_of_week='mon', hour=9, minute=15)
```

### 1.3 Post-Listing Momentum Metrics

Add `compute_ipo_metrics(ticker, listing_date, issue_price)` → returns a dict:

| Metric | Formula | Signal |
|---|---|---|
| `listing_gain_pct` | `(listing_close - issue_price) / issue_price * 100` | >20% = hot IPO |
| `current_vs_issue_pct` | `(current_price - issue_price) / issue_price * 100` | Absolute return since IPO |
| `current_vs_listing_pct` | `(current_price - listing_close) / listing_close * 100` | Post-listing drift |
| `days_since_listing` | `(today - listing_date).days` | Filter bucket |
| `rvol_ratio` | `current_volume / avg_volume_20d` | Momentum confirmation |
| `above_listing_high` | `current_price > max(prices_since_listing)` | Breakout to ATH |
| `drawdown_from_ath` | `(current_price - ath_since_listing) / ath_since_listing * 100` | Risk gauge |
| `swing_score` | Reuse existing `calculate_swing_score()` | Consistency with main table |
| `pattern_name` | Reuse `classify_technical_pattern()` | Pattern at current price |
| `momentum_phase` | Enum: `HOT / STABLE / FADING / BROKEN` | See Phase Classification below |

**Momentum Phase Classification:**

```python
def classify_momentum_phase(days_since, current_vs_issue, current_vs_listing, is_sme=False):
    hot_threshold    = 30 if is_sme else 15
    broken_threshold = -20 if is_sme else -10

    if days_since <= 10 and current_vs_issue > hot_threshold:
        return "HOT"           # Early window, strong listing gain intact
    elif days_since <= 60 and current_vs_listing > 5:
        return "STABLE"        # Holding listing gains post cool-off
    elif current_vs_listing < broken_threshold:
        return "BROKEN"        # Listing gains fully surrendered
    else:
        return "FADING"        # In between — watch for re-entry setup
```

### 1.4 New API Endpoints

```
GET  /api/ipo/listings?days=90&exchange=all&phase=all
     → Paginated list of IPO records with computed metrics

GET  /api/ipo/detail/<ticker>
     → Full metrics + historical OHLCV since listing + pattern detection

POST /api/ipo/refresh
     → Manually trigger seed_ipo_listings() + recompute all metrics
     → Rate-limited: 60s cooldown (reuse snapshot cooldown pattern from RRG)
```

**Response shape for `/api/ipo/listings`:**
```json
{
  "listings": [
    {
      "ticker": "ZOMATO.NS",
      "company_name": "Zomato Ltd",
      "listing_date": "2021-07-23",
      "exchange": "NSE",
      "sector": "Consumer Internet",
      "issue_price": 76.0,
      "listing_gain_pct": 52.63,
      "current_vs_issue_pct": 185.5,
      "current_vs_listing_pct": 87.2,
      "days_since_listing": 320,
      "rvol_ratio": 1.84,
      "above_listing_high": true,
      "drawdown_from_ath": -12.4,
      "swing_score": 7,
      "pattern_name": "Pullback to MA",
      "momentum_phase": "STABLE"
    }
  ],
  "total": 214,
  "page": 1,
  "per_page": 50
}
```

### 1.5 Caching Strategy

- Metrics are recomputed daily at EOD (APScheduler: Mon–Fri 16:00 IST) and cached in a new `ipo_metrics_cache` DB table
- Live price refresh via existing `_historical_prices_cache` (15-min TTL) — no new cache needed
- `/api/ipo/listings` response cached in-memory for 10 minutes (same pattern as `/api/rrg-history`)

---

## Phase 2 — Frontend: IPO Tab

### 2.1 Tab Registration

In `templates/index.html`, add the tab button in the existing screener tab bar:

```html
<!-- Insert after the "Intraday Pro" tab button -->
<button class="tab-btn" data-tab="ipo" id="tab-ipo">
    <span class="tab-icon">🚀</span> IPO / SME
    <span class="tab-badge" id="ipo-hot-count">0</span>
</button>
```

The `tab-badge` shows the count of `HOT` phase IPOs — a live attention signal.

### 2.2 Tab Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  IPO / SME Tab Header                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ 🔥 HOT  │ │ ✅ STABLE│ │ ⚠ FADING│ │ 💀 BROKEN       │  │
│  │   12    │ │    38    │ │    29   │ │     17           │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘  │
│                                                                  │
│  Filter Bar:  [All Exchanges ▼] [Last 30d / 90d / 180d / 1Y ▼] │
│               [Min Listing Gain ▼] [Sector ▼] [🔍 Search]      │
│                                                                  │
│  ┌──────────────────────────── IPO TABLE ──────────────────────┐│
│  │ # │ Ticker │ Name │ Listed │ Exch │ Issue₹ │ List Gain% │   ││
│  │   │        │      │        │      │        │ vs Issue%  │   ││
│  │   │        │      │        │      │        │ Phase      │   ││
│  │   │        │      │        │      │        │ Swing Score│   ││
│  │   │        │      │        │      │        │ Pattern    │   ││
│  └───────────────────────────────────────────────────────────  ┘│
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Phase Pill Component

Phase badges should be visually distinct and consistent with the existing design language:

```javascript
function getIpoPhasePill(phase) {
    const map = {
        HOT:    { label: '🔥 HOT',    cls: 'phase-hot'    },
        STABLE: { label: '✅ STABLE', cls: 'phase-stable' },
        FADING: { label: '⚠ FADING', cls: 'phase-fading' },
        BROKEN: { label: '💀 BROKEN', cls: 'phase-broken' }
    };
    const p = map[phase] || map['FADING'];
    return `<span class="phase-pill ${p.cls}">${p.label}</span>`;
}
```

CSS for phase pills:
```css
.phase-pill { padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; }
.phase-hot    { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.phase-stable { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
.phase-fading { background: rgba(234, 179, 8, 0.15);  color: #eab308; }
.phase-broken { background: rgba(107,114,128, 0.15);  color: #6b7280; }
```

### 2.4 IPO Table Columns

| Column | Source | Notes |
|---|---|---|
| `#` | Row index | Sort rank |
| Ticker + Name | `ipo_listings` | Clicking opens existing stock drawer |
| Listed | `listing_date` | Relative ("23d ago") + absolute on hover |
| Exchange | `exchange` | `NSE` / `BSE` / `SME` badge |
| Issue ₹ | `issue_price` | — |
| List Day | `listing_gain_pct` | Green/red colored, e.g. `+52.6%` |
| vs Issue | `current_vs_issue_pct` | Current standing vs. offer price |
| Phase | `momentum_phase` | Phase pill component |
| Swing | `swing_score` | Reuse existing `score-badge` CSS |
| Pattern | `pattern_name` | Reuse existing pattern label CSS |
| RVOL | `rvol_ratio` | Highlights > 1.5x |

### 2.5 Mini Post-Listing Chart

On row hover (or clicking a chart icon), render a **compact inline chart** using TradingView Lightweight Charts — same pattern as the existing trade drawer. The chart should:

- Show **OHLCV bars from listing date to today**
- Mark the **issue price** as a dashed horizontal line (reference level)
- Mark the **listing day close** as a dotted line
- Overlay SMA10 and SMA21
- Be rendered in a 300×160px panel that expands to full drawer on click (reuse existing `openTradeDrawer()` flow)

```javascript
function renderIpoMiniChart(container, ohlcv, issuePrice, listingClose) {
    const chart = LightweightCharts.createChart(container, { width: 300, height: 160 });
    const candleSeries = chart.addCandlestickSeries();
    candleSeries.setData(ohlcv);

    // Issue price reference line
    candleSeries.createPriceLine({
        price: issuePrice,
        color: '#f59e0b',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        title: `Issue ₹${issuePrice}`
    });

    // Listing close reference
    candleSeries.createPriceLine({
        price: listingClose,
        color: '#818cf8',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dotted,
        title: `List ₹${listingClose}`
    });
}
```

### 2.6 Watchlist Integration

Add an `Add to Watchlist` button (`+`) in each IPO row — reuse the existing `addToWatchlistSection()` function. When a user adds an IPO stock to their watchlist from this tab, it should carry across to the main watchlist with an `[IPO]` tag prefix for visual context.

---

## Phase 3 — SME-Specific Handling

SME IPOs (NSE Emerge / BSE SME) have different characteristics:

- **Lower liquidity** — volume data is often sparse; RVOL calculation should require a minimum of 5 trading days of history before showing the ratio
- **Higher volatility** — momentum phase thresholds should be adjusted:
  - `HOT`: `current_vs_issue > 30%` (SME IPOs routinely list at 60–100% premium)
  - `BROKEN`: `current_vs_listing < -20%` (SME can swing wider)
- **Circuit breaker flag** — NSE SME stocks frequently hit 5%/10% upper/lower circuits; add a `circuit_hit_today` boolean field fetched from the existing TradingView data pipeline

Add an `is_sme` boolean column to `ipo_listings` and conditionally apply adjusted thresholds in `classify_momentum_phase()` (already included in Phase 1.3 above).

---

## Phase 4 — Greymarket Premium (GMP) Tracking (Optional / Future)

GMP is widely tracked by Indian retail traders as a pre-listing signal. While real-time GMP has no official API, consider:

- Scraping [InvestorGain.com](https://www.investorgain.com/report/live-ipo-gmp/331/) or [IPO Watch India](https://ipowatch.in/ipo-grey-market-premium-today-live-ipo-gmp/) for upcoming IPO GMP
- Storing `gmp_at_listing` (snapshot at listing time) in `ipo_listings` for historical comparison
- Showing a `GMP vs Actual` column: did the stock list near GMP or diverge?

This is lower priority but a strong differentiator for the premium tier.

---

## Phase 5 — Kronos Integration

Once the IPO tab is stable, integrate Kronos forecasting:

- Add a **⚡ Kronos Sort** button on the IPO tab (same as watchlist) — rank HOT-phase IPOs by AI predicted 5-day return
- Add IPO stocks to the batch forecast endpoint by tagging them with an `ipo_flag=true` query param — this can adjust Kronos temperature upward (IPOs have higher realized volatility than established stocks)
- Surface a **"IPO Forecast vs Listing Trend"** panel: compare Kronos directional accuracy for IPOs specifically vs. the main universe (expected to be lower — surfaces model limitations honestly)

---

## Testing Plan

### Unit Tests (`tests/test_ipo.py`)

```python
# Test 1: Momentum phase classification — all 4 phases
def test_classify_momentum_phase_hot():
    assert classify_momentum_phase(5, 25, 20) == "HOT"

def test_classify_momentum_phase_broken():
    assert classify_momentum_phase(45, -5, -15) == "BROKEN"

def test_classify_momentum_phase_sme_hot():
    assert classify_momentum_phase(5, 35, 30, is_sme=True) == "HOT"
    assert classify_momentum_phase(5, 20, 18, is_sme=True) != "HOT"  # Below SME threshold

# Test 2: Metric computation edge cases
def test_compute_ipo_metrics_insufficient_history():
    # Should return empty metrics dict, not raise
    result = compute_ipo_metrics("FAKEXYZ.NS", "2026-06-01", 100.0)
    assert result.get("error") is not None

# Test 3: DB schema migration — ipo_listings created fresh
def test_ipo_listings_table_creation():
    # Assert all required columns present after init_db()
    pass
```

### Integration Tests

- `/api/ipo/listings` returns 200 with valid JSON even when `ipo_listings` table is empty (empty state, not 500)
- `/api/ipo/refresh` returns 429 if called within 60s cooldown window
- Phase counts in response header match actual phase distribution in listings array

---

## Implementation Order

| Step | Task | File(s) | Est. Time |
|---|---|---|---|
| 1 | Add `ipo_listings` + `ipo_metrics_cache` DB tables in `init_db()` | `app.py` | 1h |
| 2 | Implement `seed_ipo_listings()` with BSE/NSE scraping | `app.py` | 4h |
| 3 | Implement `compute_ipo_metrics()` and `classify_momentum_phase()` | `app.py` | 3h |
| 4 | Wire `/api/ipo/listings` and `/api/ipo/detail/<ticker>` endpoints | `app.py` | 2h |
| 5 | Add APScheduler jobs for daily recompute + weekly seed | `app.py` | 1h |
| 6 | Add `/api/ipo/refresh` with cooldown guard | `app.py` | 1h |
| 7 | Register IPO tab + phase summary cards in HTML | `templates/index.html` | 2h |
| 8 | Build `renderIpoTable()` with all columns + phase pills | `static/js/app.js` | 4h |
| 9 | Build `renderIpoMiniChart()` with issue/listing price lines | `static/js/app.js` | 2h |
| 10 | Watchlist integration (`Add +` button with `[IPO]` tag) | `static/js/app.js` | 1h |
| 11 | SME-specific threshold adjustments | `app.py` | 1h |
| 12 | Write `tests/test_ipo.py` unit + integration tests | `tests/` | 3h |

**Total estimated effort:** ~25 hours (~3.5 working days)

---

## Edge Cases & Known Risks

- **Ticker resolution ambiguity** — BSE and NSE may list the same company under different symbols (e.g., `ZOMATO` on NSE vs `543320` on BSE). Use NSE symbol as primary key, resolve BSE code as secondary.
- **Delisted IPOs** — some SME IPOs get suspended or delisted within months. `yfinance` will return empty DataFrames. Guard all `compute_ipo_metrics()` calls with a minimum history check (≥ 3 trading days) and mark these as `momentum_phase: "BROKEN"` automatically.
- **Issue price not always available** — some SME stocks don't have publicly accessible offer prices. Fall back to `listing_open` as the reference price and show a `~` indicator next to the metric (consistent with the existing simulated data convention in the codebase).
- **Scraping fragility** — BSE/NSE change HTML structures periodically. The seed function should be wrapped in broad `try/except` with detailed logging, and the scheduler should not abort the app on failure.

---

## Definition of Done

- [ ] `ipo_listings` table persists across app restarts with ≥ 30 real listings
- [ ] IPO tab renders correctly in both light and dark themes
- [ ] All 4 momentum phases display with correct pill styling
- [ ] Clicking a row opens the existing trade drawer for the IPO stock
- [ ] Mini post-listing chart renders with issue price + listing close reference lines
- [ ] `Add to Watchlist` carries the `[IPO]` tag prefix
- [ ] `/api/ipo/refresh` respects 60s cooldown (returns 429 on violation)
- [ ] Unit tests pass for all phase classification scenarios including SME thresholds
- [ ] Empty state (no listings in DB) shows a friendly message, not a 500
- [ ] `growth_data_source` pattern applied: `~` badge shown if issue price is estimated from listing open
