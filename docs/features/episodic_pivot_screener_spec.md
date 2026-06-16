# Episodic Pivot (EP) Screener — Technical Specification for Indian Markets (NSE/BSE)

## Overview

This document is a complete technical specification for building an Episodic Pivot screener tailored to the Indian equity market (NSE/BSE). The strategy, originally defined by Pradeep Bonde, targets neglected stocks that receive a major catalyst and undergo rapid repricing — gaining 50–300% in as short as 10–20 trading days. This spec covers database schema, scoring formulas, pipeline architecture, Flask API endpoints, frontend screener views, and backtesting design.

---

## 1. Strategy Recap — What the Screener Must Detect

Every valid EP candidate must exhibit three core signals:

| Signal | Definition |
|---|---|
| **Neglect** | Stock has done little for 3–6 months; low volume, no trending narrative, stuck in a range |
| **Catalyst** | Earnings surprise, turnaround evidence, management change, order win, theme, or abnormal volume |
| **Rapid Repricing** | Gap or strong expansion bar with volume many multiples of normal; closes near high |

EP types to label on every candidate:

| Type | Trigger | Trade Style |
|---|---|---|
| Growth EP | 100%+ sales/profit acceleration on neglected stock | Day-1 MOO entry, tight stop under Day-1 low |
| Turnaround EP | Prolonged decline → sharp profitability reversal | Day-1 entry or first pullback; loose trailing stop |
| Story/Thematic EP | Hot narrative (defence, EV, AI, capex, PLI, etc.) | Day 1–3 entry; exit quickly on volume fade |
| Volume EP (9M equiv.) | Single-day volume >> 5–10× normal; float-adjusted | Intraday or next-day entry on trend confirmation |
| Delayed Reaction EP | Messy Day 1; secondary red-to-green or range breakout | Tighter entry, larger size; up to 20 sessions window |
| Short EP | Negative catalyst (guidance cut, fraud, weak results) | Wait for bounce, enter on failed rally / lower high |
| Sugar Babies (Habitual Runners) | Historical EP runners; recurring 30–50% bursts | Track separately; breakout or pullback entries |

---

## 2. Database Schema

### 2.1 `daily_bars`

```sql
CREATE TABLE daily_bars (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL,          -- NSE symbol e.g. RELIANCE
    exchange        VARCHAR(5)  NOT NULL,           -- NSE / BSE
    trade_date      DATE        NOT NULL,
    open            NUMERIC(12,2),
    high            NUMERIC(12,2),
    low             NUMERIC(12,2),
    close           NUMERIC(12,2),
    volume          BIGINT,
    delivery_qty    BIGINT,                         -- from NSE bhav copy
    delivery_pct    NUMERIC(5,2),                   -- delivery % of total volume
    turnover        NUMERIC(18,2),
    prev_close      NUMERIC(12,2),
    gap_pct         NUMERIC(7,3),                   -- (open - prev_close) / prev_close * 100
    close_loc       NUMERIC(5,3),                   -- (close - low) / (high - low); 1 = closed at high
    atr_14          NUMERIC(10,4),
    rel_volume_20   NUMERIC(8,3),                   -- volume / 20-day avg volume
    rel_volume_50   NUMERIC(8,3),
    price_change_pct NUMERIC(7,3),
    intraday_range_pct NUMERIC(7,3),               -- (high - low) / prev_close * 100
    UNIQUE (symbol, exchange, trade_date)
);

CREATE INDEX idx_daily_bars_symbol_date ON daily_bars (symbol, trade_date DESC);
CREATE INDEX idx_daily_bars_date ON daily_bars (trade_date DESC);
```

### 2.2 `fundamentals`

```sql
CREATE TABLE fundamentals (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL,
    exchange        VARCHAR(5)  NOT NULL,
    result_date     DATE        NOT NULL,           -- date results were announced
    quarter         VARCHAR(10),                    -- Q1FY26, Q4FY25 etc.
    revenue         NUMERIC(18,2),
    revenue_yoy_pct NUMERIC(8,2),
    revenue_qoq_pct NUMERIC(8,2),
    net_profit      NUMERIC(18,2),
    net_profit_yoy_pct NUMERIC(8,2),
    ebitda          NUMERIC(18,2),
    ebitda_margin   NUMERIC(6,2),
    eps             NUMERIC(10,4),
    eps_yoy_pct     NUMERIC(8,2),
    guidance_text   TEXT,
    surprise_type   VARCHAR(20),                    -- BLOWOUT / BEAT / MISS / TURNAROUND
    consecutive_quarters_growth INTEGER,
    source          VARCHAR(50),                    -- screener.in / NSE / BSE XML
    UNIQUE (symbol, exchange, quarter)
);
```

### 2.3 `corporate_events`

```sql
CREATE TABLE corporate_events (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL,
    exchange        VARCHAR(5)  NOT NULL,
    event_date      DATE        NOT NULL,
    event_type      VARCHAR(40),                    -- EARNINGS / ORDER_WIN / MGMT_CHANGE /
                                                    -- CAPEX / RIGHTS / BUYBACK / THEME_CATALYST
                                                    -- / FRAUD / GUIDANCE_CUT / REGULATORY
    headline        TEXT,
    sentiment       SMALLINT,                       -- +1 (positive) / -1 (negative) / 0 (neutral)
    catalyst_score  NUMERIC(4,2),                   -- 0.0 – 1.0, manually or ML-assigned
    source          VARCHAR(80),                    -- NSE announcements / BSEIndia / moneycontrol
    raw_url         TEXT
);

CREATE INDEX idx_corp_events_symbol_date ON corporate_events (symbol, event_date DESC);
```

### 2.4 `ep_features`

Computed nightly from daily_bars + fundamentals + corporate_events.

```sql
CREATE TABLE ep_features (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL,
    exchange        VARCHAR(5)  NOT NULL,
    feature_date    DATE        NOT NULL,           -- the candidate EP day

    -- Neglect scores
    perf_3m         NUMERIC(7,3),                   -- 3-month price return
    perf_6m         NUMERIC(7,3),
    range_60d_pct   NUMERIC(7,3),                   -- (max - min) / avg_close over 60 days
    avg_vol_rank    NUMERIC(5,3),                   -- percentile of avg vol vs sector (0–1)
    neglect_score   NUMERIC(4,2),                   -- composite 0.0 – 1.0

    -- Catalyst scores
    has_result      BOOLEAN DEFAULT FALSE,
    revenue_growth  NUMERIC(8,2),
    profit_growth   NUMERIC(8,2),
    has_corp_event  BOOLEAN DEFAULT FALSE,
    event_type      VARCHAR(40),
    catalyst_score  NUMERIC(4,2),                   -- composite 0.0 – 1.0

    -- Repricing scores
    gap_pct         NUMERIC(7,3),
    rel_volume      NUMERIC(8,3),
    close_loc       NUMERIC(5,3),
    repricing_score NUMERIC(4,2),                   -- composite 0.0 – 1.0

    -- Final EP score
    ep_score        NUMERIC(4,2),                   -- weighted composite 0.0 – 1.0
    ep_type         VARCHAR(30),                    -- Growth / Turnaround / Story / Volume / Delayed / Short
    confidence      VARCHAR(10),                    -- HIGH / MEDIUM / LOW

    -- Liquidity
    market_cap_cr   NUMERIC(14,2),                  -- crores
    avg_turnover_cr NUMERIC(10,2),                  -- 20-day avg daily turnover in crores
    float_days      NUMERIC(6,2),                   -- days to trade the float at current volume

    UNIQUE (symbol, exchange, feature_date)
);

CREATE INDEX idx_ep_features_date ON ep_features (feature_date DESC);
CREATE INDEX idx_ep_features_score ON ep_features (feature_date DESC, ep_score DESC);
```

### 2.5 `ep_watchlist`

Tracks active candidates across the 20-session window.

```sql
CREATE TABLE ep_watchlist (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL,
    exchange        VARCHAR(5)  NOT NULL,
    catalyst_date   DATE        NOT NULL,           -- original Day-1 EP date
    ep_type         VARCHAR(30) NOT NULL,
    status          VARCHAR(20) DEFAULT 'ACTIVE',   -- ACTIVE / TRIGGERED / EXPIRED / STOPPED
    trigger_type    VARCHAR(30),                    -- DAY1 / RED_TO_GREEN / RANGE_BREAKOUT / RECLAIM
    entry_price     NUMERIC(12,2),
    stop_price      NUMERIC(12,2),
    target_price    NUMERIC(12,2),
    entry_date      DATE,
    days_on_watch   INTEGER DEFAULT 0,
    notes           TEXT,
    ep_score        NUMERIC(4,2),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.6 `sugar_babies`

```sql
CREATE TABLE sugar_babies (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20) UNIQUE NOT NULL,
    exchange        VARCHAR(5)  NOT NULL,
    added_date      DATE,
    avg_burst_pct   NUMERIC(6,2),                   -- historical average burst %
    avg_burst_days  NUMERIC(5,1),
    episode_count   INTEGER,                        -- number of past EP-like bursts
    notes           TEXT,
    is_active       BOOLEAN DEFAULT TRUE
);
```

---

## 3. Scoring Formulas

### 3.1 Neglect Score (25% of EP Score)

The neglect score is highest when a stock has been flat or down for months, has thin volume participation, and is still base-building rather than trending.

```python
def compute_neglect_score(perf_3m, perf_6m, range_60d_pct, avg_vol_rank):
    """
    All inputs normalised 0–1 before weighting.
    Higher neglect → stock has done less recently.
    """
    # Invert returns: more negative 3m return = higher neglect
    n_perf_3m = max(0, min(1, (0 - perf_3m) / 40 + 0.5))   # -40% → 1.0,  +40% → 0.0
    n_perf_6m = max(0, min(1, (0 - perf_6m) / 60 + 0.5))

    # Tighter 60-day range = more neglected
    n_range = max(0, min(1, 1 - (range_60d_pct / 40)))      # 0% range → 1.0, 40% range → 0.0

    # Lower average volume rank = less interest
    n_vol_rank = 1 - avg_vol_rank                            # already 0–1

    neglect = (0.35 * n_perf_3m +
               0.25 * n_perf_6m +
               0.20 * n_range +
               0.20 * n_vol_rank)
    return round(neglect, 3)
```

### 3.2 Catalyst Score (35% of EP Score)

Catalyst quality is the most important signal. A blowout earnings result with triple-digit growth on a neglected small/mid-cap is the highest-scoring catalyst.

```python
CATALYST_BASE = {
    "BLOWOUT_EARNINGS":  0.90,   # Revenue + profit both 100%+ YoY
    "STRONG_BEAT":       0.70,   # Revenue 40–100% YoY
    "TURNAROUND":        0.80,   # Profit swings from loss to strong profit
    "ORDER_WIN":         0.65,   # Major order announcement (>30% of mktcap)
    "MGMT_CHANGE":       0.55,   # New CEO / promoter buyback
    "THEME_CATALYST":    0.50,   # Government policy, PLI, sector tailwind
    "CAPEX_EXPANSION":   0.45,
    "ABNORMAL_VOLUME":   0.60,   # Volume EP / 9M equivalent (no news yet)
    "BEAT":              0.50,
    "MISS":             -0.30,
    "GUIDANCE_CUT":     -0.80,   # Negative catalyst (Short EP)
    "FRAUD_CONCERN":    -0.90,
    "UNKNOWN":           0.20,
}


def compute_catalyst_score(event_type, revenue_growth, profit_growth,
                            consecutive_quarters, market_cap_cr):
    base = CATALYST_BASE.get(event_type, 0.20)
    if base < 0:                        # Short EP — return negative value for separation
        return round(base, 3)

    bonus = 0.0
    # Triple-digit revenue growth
    if revenue_growth and revenue_growth >= 100:
        bonus += 0.10
    elif revenue_growth and revenue_growth >= 50:
        bonus += 0.05

    # Profit growth acceleration
    if profit_growth and profit_growth >= 200:
        bonus += 0.10
    elif profit_growth and profit_growth >= 100:
        bonus += 0.05

    # Multi-quarter confirmation
    if consecutive_quarters and consecutive_quarters >= 2:
        bonus += 0.05

    # Small/mid cap gets higher re-rating potential
    if market_cap_cr and market_cap_cr < 5000:
        bonus += 0.05

    return round(min(1.0, base + bonus), 3)
```

### 3.3 Repricing Score (30% of EP Score)

The repricing score confirms the market is acting on the catalyst right now.

```python
def compute_repricing_score(gap_pct, rel_volume, close_loc, price_change_pct,
                             intraday_range_pct):
    """
    gap_pct         : % gap from prev close (0–40+)
    rel_volume      : today's vol / 20-day avg (1x = normal)
    close_loc       : 0 = closed at low, 1 = closed at high
    price_change_pct: day's price change %
    intraday_range_pct: (H-L)/prev_close * 100
    """
    # Gap component: 5% gap → 0.5; 20% gap → 1.0
    n_gap = max(0, min(1, gap_pct / 20))

    # Volume confirmation: 3x normal → 0.5; 10x → 1.0
    n_vol = max(0, min(1, (rel_volume - 1) / 9))

    # Close location: closing near high is a bull signal
    n_close = close_loc                  # already 0–1

    # Overall day strength: blend of close-to-close change (70%) and intraday range (30%)
    n_strength = max(0, min(1, (price_change_pct * 0.7 + intraday_range_pct * 0.3) / 15))

    repricing = (0.30 * n_gap +
                 0.35 * n_vol +
                 0.20 * n_close +
                 0.15 * n_strength)
    return round(repricing, 3)
```

### 3.4 Final EP Score

```python
def compute_ep_score(neglect_score, catalyst_score, repricing_score,
                     liquidity_ok: bool, has_fundamentals: bool = True):
    """
    Weighted composite. Catalyst_score can be negative for Short EPs.
    """
    raw = (0.25 * neglect_score +
           0.35 * abs(catalyst_score) +
           0.30 * repricing_score +
           0.10 * (1.0 if has_fundamentals else 0.0))

    # Small liquidity penalty if stock is too illiquid
    liquidity_adj = 0.0 if liquidity_ok else -0.10

    ep_score = round(max(0.0, min(1.0, raw + liquidity_adj)), 3)
    return ep_score


def assign_ep_type(catalyst_score, event_type, rel_volume, gap_pct,
                   revenue_growth=0, profit_growth=0, day1_messy: bool = False,
                   is_negative_catalyst: bool = False):
    if is_negative_catalyst or catalyst_score < 0:
        return "Short EP"
    if event_type in ("ABNORMAL_VOLUME", "UNKNOWN"):
        return "Volume EP"
    if day1_messy:
        return "Delayed EP"
    if event_type in ("BLOWOUT_EARNINGS", "STRONG_BEAT", "BEAT") and revenue_growth >= 100:
        return "Growth EP"
    if event_type == "TURNAROUND":
        return "Turnaround EP"
    if event_type in ("THEME_CATALYST", "ORDER_WIN", "MGMT_CHANGE", "CAPEX_EXPANSION"):
        return "Story EP"
    if event_type in ("BLOWOUT_EARNINGS", "STRONG_BEAT", "BEAT", "MISS"):
        return "Growth EP"
    return "Growth EP"


def assign_confidence(ep_score, neglect_score, catalyst_score, repricing_score):
    if ep_score >= 0.72 and catalyst_score >= 0.70 and repricing_score >= 0.60:
        return "HIGH"
    if ep_score >= 0.55:
        return "MEDIUM"
    return "LOW"
```

---

## 4. Nightly Pipeline Architecture

```
[Nightly ETL — runs after NSE/BSE close (~5:00 PM IST)]
        │
        ├─ 1. OHLCV Ingest
        │      nse_bhav_copy.csv + bse_eq_d.csv
        │      → daily_bars (gap_pct, close_loc, rel_volume_20/50, ATR)
        │
        ├─ 2. Fundamentals Ingest
        │      NSE results XML / screener.in API / Ticker Tape
        │      → fundamentals (revenue_yoy_pct, surprise_type, consecutive_quarters)
        │
        ├─ 3. Corporate Events Ingest
        │      NSE corporate actions feed / BSE announcements feed / news headlines
        │      → corporate_events (event_type, sentiment, catalyst_score)
        │
        ├─ 4. Feature Computation
        │      For each symbol with an event today OR rel_volume > 3x:
        │        compute_neglect_score()
        │        compute_catalyst_score()
        │        compute_repricing_score()
        │        compute_ep_score()
        │        assign_ep_type()
        │        assign_confidence()
        │      → ep_features
        │
        ├─ 5. Watchlist Update
        │      Move ep_score >= 0.55 to ep_watchlist (status=ACTIVE)
        │      Increment days_on_watch for existing ACTIVE entries
        │      Expire entries where days_on_watch > 20
        │      Check trigger conditions for Delayed EP candidates
        │      → ep_watchlist
        │
        └─ 6. Alerts
               Send WhatsApp / Telegram / email for HIGH confidence new EPs
               Flag Delayed EP triggers (red-to-green, range breakout, reclaim)
```

### India-specific Data Sources

| Data Type | Source | Method |
|---|---|---|
| OHLCV daily | NSE Bhav Copy | Download `https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_<DDMMYYYY>.csv` |
| Delivery % | NSE Equity Delivery Data | `https://www.nseindia.com/report-detail/eq_ddNew` |
| Corporate events | NSE corporate actions | `https://www.nseindia.com/companies-listing/corporate-filings-announcements` |
| Quarterly results | Screener.in (unofficial) / Ticker Tape API | Parse JSON or scrape |
| Results calendar | NSE results notification | NSE API `/api/event-calendar` |
| Index constituents + sector | NSE indices | Nifty sector indices CSV |
| Float / shares outstanding | BSE corporate data | BSE API or screener.in |

---

## 5. Flask API Endpoints

### 5.1 Screener Views

```python
# routes/ep_screener.py

@bp.get('/api/ep/today')
def ep_today():
    """
    Returns today's EP candidates sorted by ep_score DESC.
    Query params:
        ep_type     : Growth / Turnaround / Story / Volume / Delayed / Short / all
        confidence  : HIGH / MEDIUM / LOW / all
        min_score   : float (default 0.55)
        min_mktcap  : int crores (default 0)
        max_mktcap  : int crores (default 999999)
        exchange    : NSE / BSE / all
    """


@bp.get('/api/ep/watchlist')
def ep_watchlist():
    """
    Returns ACTIVE watchlist entries (Delayed EP candidates still within 20-session window).
    Includes days_on_watch and trigger_type when triggered.
    """


@bp.get('/api/ep/sugar-babies')
def sugar_babies():
    """
    Returns active Sugar Baby list with current price, last EP date,
    breakout status, and pullback-to-support distance.
    """


@bp.get('/api/ep/<symbol>/detail')
def ep_detail(symbol):
    """
    Returns full EP feature breakdown for a symbol:
    - Neglect score breakdown (perf_3m, perf_6m, range_60d, vol_rank)
    - Catalyst score breakdown (event_type, revenue_growth, profit_growth)
    - Repricing score breakdown (gap_pct, rel_volume, close_loc)
    - 60-day OHLCV for chart
    - All corporate events in last 6 months
    - Watchlist status
    """


@bp.get('/api/ep/history')
def ep_history():
    """
    Historical EP candidates for backtesting reference.
    Query params: from_date, to_date, ep_type, min_score
    """
```

### 5.2 Sector / Theme Context

```python
@bp.get('/api/ep/themes')
def ep_themes():
    """
    Groups today's Story EPs and Volume EPs by NSE sector / theme tag.
    Returns theme name, count of EPs, avg ep_score, list of symbols.
    Used to identify theme cluster breakouts (e.g. PSU defence burst).
    """


@bp.get('/api/ep/sector-rotation')
def sector_rotation():
    """
    Returns 5-day and 20-day RS rank per NSE sector.
    Overlays count of active EPs per sector.
    Helps identify when an EP sits inside a rotating sector leader.
    """
```

### 5.3 Backtesting

```python
@bp.post('/api/ep/backtest')
def ep_backtest():
    """
    Body: {
        "ep_type": "Growth",
        "from_date": "2022-01-01",
        "to_date": "2025-12-31",
        "min_ep_score": 0.60,
        "entry_rule": "DAY1_OPEN" | "DAY1_ORNG_BREAKOUT" | "DELAYED_RTG",
        "stop_rule": "DAY1_LOW" | "STRUCTURE_LOW" | "ATR_2X",
        "exit_rule": "SWING_LOW_TRAIL" | "20D_MA" | "FIXED_PCT",
        "position_size_pct": 5.0
    }
    Returns: win_rate, profit_factor, avg_win, avg_loss, expectancy,
             max_drawdown, total_trades, equity_curve (JSON array)
    """
```

---

## 6. Frontend Screener Views

### 6.1 Dashboard Layout

The EP Screener tab in your existing Flask app should have four panels:

```
┌─────────────────────────────────────────────────────────────────┐
│  EP SCREENER         [Date: 11-Jun-2026]    [Market: NSE/BSE]  │
├─────────────────────────────────────────────────────────────────┤
│  TABS: Today's EPs | Watchlist | Sugar Babies | Themes | History│
├──────────────┬──────────────────────────────────────────────────┤
│  FILTERS     │  EP CANDIDATE TABLE                              │
│  ─────────   │  ──────────────────────────────────────────────  │
│  Type        │  Symbol | Type | EP Score | Neglect | Catalyst  │
│  [All ▾]     │         | Repricing | Gap% | Vol× | MktCap(Cr)  │
│              │         | Confidence | Trigger                   │
│  Confidence  │                                                  │
│  [All ▾]     │  (rows sorted by EP Score DESC)                  │
│              │                                                  │
│  Min MktCap  │                                                  │
│  [0 Cr]      │                                                  │
│              │                                                  │
│  Max MktCap  │                                                  │
│  [999999 Cr] │                                                  │
│              │                                                  │
│  Min Score   │                                                  │
│  [0.55]      │                                                  │
│              │  [Click row → EP Detail panel slides in →]       │
└──────────────┴──────────────────────────────────────────────────┘
```

### 6.2 EP Candidate Row — Colour Coding

| Condition | Row colour |
|---|---|
| Confidence = HIGH + Type ∈ Growth/Turnaround | Green tint |
| Confidence = HIGH + Type = Volume EP | Blue tint |
| Confidence = MEDIUM | No tint |
| Type = Short EP | Red tint |
| days_on_watch > 0 (Delayed EP active) | Amber tint |

### 6.3 EP Detail Sidebar

When a row is clicked, a right-side panel opens showing:
- Mini OHLCV chart (60 days) with catalyst day marked, EP Day-1 range box, volume histogram
- Score breakdown gauges (neglect / catalyst / repricing)
- Latest results table (quarterly revenue and profit with YoY %)
- Corporate events timeline
- Watchlist controls: Add to Watchlist / Mark Triggered / Add to Sugar Babies

### 6.4 Watchlist View

Shows only `ep_watchlist` entries with `status = ACTIVE`. Each row includes:
- Days remaining (20 - days_on_watch)
- Trigger type hint: "Watch for red-to-green" / "Watch for range breakout" / "Watch for level reclaim"
- Mini 20-day chart since catalyst date

### 6.5 Sugar Babies View

Static curated list showing current price, distance from nearest historical breakout level, RSI, and a "primed" flag when volume starts expanding above 2× normal again.

---

## 7. Indian Market Adaptations

The EP strategy was designed for US markets. Several parameters need tuning for NSE/BSE:

| Parameter | US (original) | India (adapted) |
|---|---|---|
| Volume threshold (9M equiv.) | 9 million shares | Use delivery-adjusted turnover >5× 20-day avg, OR volume >10× avg; absolute threshold ₹50 Cr turnover in one day |
| Gap threshold | 20–40% is common | 8–25% gap on NSE mid/small caps; 3–10% gap for large caps signals significant catalyst |
| Neglect window | 3–6 months | Same; cross-check against Nifty 500 relative strength rank |
| Float consideration | Float shares outstanding | Use public shareholding × shares outstanding; exclude promoter + locked-in FII |
| Result season | Quarterly (US fiscal) | NSE result seasons: April–May (Q4FY), July–Aug (Q1FY), Oct–Nov (Q2FY), Jan–Feb (Q3FY) |
| Short EP suitability | High (US shorting easy) | Use only for high-liquidity F&O stocks; avoid shorting illiquid NSE stocks |
| Story/Thematic tailwinds | AI, crypto, GLP-1 | India-specific: PLI schemes, Make in India, Defence export, Data centre buildout, EV ecosystem, Green hydrogen, Capex-linked (railways, ports, NTPC) |
| Minimum price filter | $3 (US) | ₹30 for NSE; ₹20 for BSE (to avoid penny stocks) |
| Market cap floor | ~$50M | ₹200 Cr (small cap floor) for Growth/Turnaround EP; ₹50 Cr minimum for Volume EP |
| Turnaround identification | Profit swing + new CEO | Also watch for: debt reduction, promoter stake increase, fresh capex announcements, government order wins after dry spell |

---

## 8. Delayed EP — Trigger Conditions (Code)

```python
def check_delayed_ep_triggers(watchlist_entry, daily_bar_today):
    """
    Called nightly for each ACTIVE watchlist entry.
    Returns trigger_type string if a secondary entry signal is detected.
    """
    symbol = watchlist_entry['symbol']
    catalyst_date = watchlist_entry['catalyst_date']
    ep_type = watchlist_entry['ep_type']

    today = daily_bar_today
    if today is None:
        return None

    # 1. Red-to-Green (RTG): opened below prev close, closed above it
    rtg = (today['open'] < today['prev_close'] and
           today['close'] > today['prev_close'] and
           today['rel_volume_20'] >= 1.5)

    # 2. Tight Range Breakout: stock formed a base (range < 8% over 5 days),
    #    today closes above the 5-day high with volume > 2×
    five_day_high = get_5day_high(symbol, today['trade_date'])
    five_day_range = get_5day_range_pct(symbol, today['trade_date'])
    tight_breakout = (five_day_range < 8.0 and
                      today['close'] > five_day_high and
                      today['rel_volume_20'] >= 2.0)

    # 3. Level Reclaim: closes above catalyst-day close (key psychological level)
    catalyst_close = get_close_on_date(symbol, catalyst_date)
    reclaim = (today['prev_close'] < catalyst_close and
               today['close'] >= catalyst_close * 0.995 and
               today['rel_volume_20'] >= 1.5)

    if rtg:
        return "RED_TO_GREEN"
    if tight_breakout:
        return "RANGE_BREAKOUT"
    if reclaim:
        return "RECLAIM"
    return None
```

---

## 9. Backtesting Design

### 9.1 Test Matrix — Run Each EP Type Separately

The article explicitly states that EP types have different trade management behaviour. Never aggregate all EP types into a single backtest.

| EP Type | Entry Rule | Stop Rule | Exit Rule |
|---|---|---|---|
| Growth EP | MOO (market open) on Day 1 | Below Day-1 low | Trail under each day's swing low |
| Turnaround EP | Day 1 close OR first clean pullback low | Below nearest swing low | Loose trail; allow multi-quarter hold |
| Story EP | Day 1–3 breakout from consolidation | Below consolidation low | Exit on volume fade; 10-day max |
| Volume EP | Intraday trend confirm OR next-day open | Below breakout day low | Trail under swing lows |
| Delayed EP | RTG / range breakout / reclaim day close | Below trigger day low | Standard EP trail |
| Short EP | After bounce, on lower-high day close | Above bounce high | Cover on volume surge or 10% profit |

### 9.2 Key Metrics to Track

```
Per EP type:
- Win rate (%)
- Avg win % / Avg loss %
- Profit factor (gross wins / gross losses)
- Expectancy (win_rate × avg_win − loss_rate × avg_loss)
- Avg hold duration (trading days)
- Max consecutive losses
- Max drawdown on EP-only portfolio
```

### 9.3 Minimum Sample Size

Run each EP type backtest on at least 40–50 trades before drawing conclusions. EP events in India will concentrate during result seasons, so use a multi-year window (2019–2025) to capture at least 4–5 full result cycles.

---

## 10. Build Phases

### Phase 1 — MVP Rules-Based Screener (Weeks 1–3)

- [ ] OHLCV nightly ingestion pipeline (NSE Bhav Copy)
- [ ] Delivery % ingestion
- [ ] Compute gap_pct, close_loc, rel_volume_20, ATR in daily_bars
- [ ] Basic neglect score (perf_3m, range_60d)
- [ ] Volume EP detection only (no fundamental input needed)
- [ ] Flask API: `/api/ep/today` with Volume EP results
- [ ] Simple frontend table view

### Phase 2 — Fundamental Catalyst Layer (Weeks 4–6)

- [ ] Quarterly results ingestion (screener.in / NSE XML)
- [ ] Compute revenue_yoy_pct, profit_yoy_pct, surprise_type
- [ ] Full catalyst_score formula
- [ ] Full neglect_score formula
- [ ] Growth EP and Turnaround EP detection
- [ ] Corporate events ingestion (NSE announcement feed)
- [ ] Story EP classification by sector/theme tags
- [ ] EP Detail sidebar with score breakdown and quarterly chart
- [ ] Watchlist table with 20-session window

### Phase 3 — Delayed EP + Alerts (Weeks 7–9)

- [ ] Nightly delayed EP trigger checking (RTG, range breakout, reclaim)
- [ ] ep_watchlist auto-update and expiry
- [ ] Telegram / WhatsApp alert integration for HIGH confidence EPs
- [ ] Short EP detection (negative catalyst + bounce setup)
- [ ] Sugar Babies list management UI

### Phase 4 — Backtesting + Refinement (Weeks 10–12)

- [ ] Historical ep_features computation (2019–2025)
- [ ] Backtest engine: `/api/ep/backtest`
- [ ] Equity curve and per-type metrics dashboard
- [ ] Tune score thresholds based on backtest results
- [ ] Sector rotation overlay
- [ ] Theme clustering view

---

## 11. Integration Notes for Your Existing Screener

Since you already have a Flask backend with TA-Lib integration and NSE/BSE data pipelines:

- Add `ep_features`, `ep_watchlist`, `corporate_events`, `fundamentals`, and `sugar_babies` tables to your existing PostgreSQL instance.
- The nightly EP pipeline can run as a new Celery task after your existing OHLCV sync task.
- Reuse your existing `daily_bars` table if it already stores gap_pct, delivery_pct, and ATR; add the missing columns via `ALTER TABLE`.
- TA-Lib's `LINEARREG_SLOPE` can compute the 60-day trend slope for the neglect score in addition to the simple return approach.
- Your existing Kronos ensemble forecasting can optionally feed a `momentum_signal` bonus into the repricing score for Growth EPs.
- The EP screener tab should link into your existing trade journal so that EP entries auto-populate into your journal with catalyst date, EP type, stop level, and score.

---

*Specification version 1.0 — June 2026. Built for NSE/BSE Indian equity market. Based on the Episodic Pivot strategy by Pradeep Bonde.*
