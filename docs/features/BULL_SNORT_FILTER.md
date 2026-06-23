# Bull Snort Filter — Design & Implementation Guide

The **Bull Snort** is a 4-phase institutional accumulation + breakout signal.
It identifies stocks that have been in a long downtrend, formed a base with
hidden volume accumulation, and are now attempting a breakout toward the 200 DMA
with a high-conviction candle.

---

## The 4-Phase Signal Structure

```
PHASE 1 — Prolonged Downtrend
  ├─ Price was significantly below 200 DMA (gap > 10%) at some point in last 6 months
  └─ 200 DMA slope is still negative (still declining)

PHASE 2 — Base Formation
  ├─ Price has NOT made a new 20-day low in the last 10 sessions (stopped falling)
  └─ Price is now within 5% of the 200 DMA (gap has closed significantly)

PHASE 3 — Base Volume Accumulation Score (0–100 bonus)
  ├─ Count of Volume Pivots during the base period (last 6 months below DMA)
  └─ Count of Volume Surges during the base period
  └─ Higher score = more institutional accumulation during base

PHASE 4 — Bull Snort Candle (Trigger)
  ├─ Volume ≥ 3× 20-day average
  ├─ Close > previous day's close
  └─ Close in top 35% of the day's candle range

ALL of Phase 1, 2, 4 must pass. Phase 3 adds to the score.
```

> The 200 DMA does **not** need to be curling up. It is typically still declining.
> What matters is that **price** closes the gap from below with a conviction candle.

---

## Full Signal Math

### Phase 1 — Prolonged Downtrend

```python
# Max gap in the last 6 months: was price ever 10%+ below 200 DMA?
gap_series      = (dma200 - close) / close * 100        # positive = price below DMA
max_gap_6mo     = gap_series.iloc[-126:].max()           # 126 trading days ≈ 6 months
was_deep_below  = max_gap_6mo >= 10.0                    # at least 10% below at some point

# 200 DMA is still declining
dma_slope_20d   = (dma200.iloc[-1] - dma200.iloc[-21]) / 20
norm_dma_slope  = (dma_slope_20d / dma200.iloc[-1]) * 100
dma_still_down  = norm_dma_slope < 0.0                   # still negative slope
```

### Phase 2 — Base Formation

```python
# Price has stopped making new lows (base forming)
recent_low_10d  = close.iloc[-11:-1].min()               # lowest close in last 10 sessions
current_low     = close.iloc[-1]
is_not_new_low  = current_low >= recent_low_10d          # not making new 20-day lows

# Price has closed the gap — now within 5% of 200 DMA
current_gap_pct = (dma200.iloc[-1] - close.iloc[-1]) / close.iloc[-1] * 100
is_near_dma     = 0.0 <= current_gap_pct <= 5.0          # within 5% below (or touching)
```

### Phase 3 — Base Volume Accumulation Score

Look back through the **base period** (last 6 months while price was below 200 DMA)
and count Volume Pivots and Volume Surges. More = higher institutional conviction.

```python
# --- Volume Pivot: local volume peak (higher than 2 neighbours on each side) ---
def detect_volume_pivots(volume_series, lookback=2):
    pivots = []
    for i in range(lookback, len(volume_series) - lookback):
        window = volume_series.iloc[i - lookback: i + lookback + 1]
        if volume_series.iloc[i] == window.max():
            pivots.append(i)
    return pivots

# --- Volume Surge: volume >= 2x its own 20-day rolling average ---
def detect_volume_surges(volume_series, avg_period=20, surge_multiplier=2.0):
    avg_vol = volume_series.rolling(avg_period).mean()
    surges  = (volume_series >= avg_vol * surge_multiplier)
    return surges[surges].index.tolist()

# --- Score the base period ---
base_window     = 126    # last 6 months
base_volume     = df['Volume'].iloc[-base_window:]
base_close      = close.iloc[-base_window:]
base_dma        = dma200.iloc[-base_window:]

# Only count pivots/surges while price was BELOW the 200 DMA
below_dma_mask  = base_close < base_dma
base_vol_masked = base_volume[below_dma_mask]

n_pivots        = len(detect_volume_pivots(base_vol_masked))
n_surges        = len(detect_volume_surges(base_vol_masked))

# Accumulation score: 0–100
# 5+ pivots = max pivot score, 3+ surges = max surge score
pivot_score     = min(n_pivots / 5.0, 1.0) * 100
surge_score     = min(n_surges / 3.0, 1.0) * 100
accumulation_score = (pivot_score * 0.5) + (surge_score * 0.5)
```

### Phase 4 — Bull Snort Candle

```python
# Volume Surge: >= 3x 20-day avg (excluding today)
avg_vol_20d     = volume.iloc[-21:-1].mean()
vol_ratio       = volume.iloc[-1] / avg_vol_20d
is_vol_surge    = vol_ratio >= 3.0

# Positive close
today_close     = close.iloc[-1]
prev_close      = close.iloc[-2]
is_positive     = today_close > prev_close
pct_change      = (today_close - prev_close) / prev_close * 100

# Strong close: top 35% of candle range
candle_range    = df['High'].iloc[-1] - df['Low'].iloc[-1]
close_position  = (today_close - df['Low'].iloc[-1]) / candle_range
is_strong_close = close_position >= 0.65

bull_snort_candle = is_vol_surge and is_positive and is_strong_close
```

---

## Codebase Structure

```
app/
├── services/
│   └── bull_snort_service.py       ← All 4 phases + scoring
├── api/v1/
│   └── bull_snort.py               ← REST endpoints
├── tasks/
│   └── scheduler.py                ← Daily refresh job
templates/
└── index.html                      ← Bull Snort tab
static/js/
└── app.js                          ← UI handler
```

---

## `bull_snort_service.py`

Create at `app/services/bull_snort_service.py`:

```python
import logging
import numpy as np
from app.utils.technical import fetch_historical_prices

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds — tune via backtesting
# ---------------------------------------------------------------------------
DEFAULT_VOL_AVG_PERIOD       = 20     # rolling avg period for Bull Snort candle volume
DEFAULT_VOL_SURGE_MIN         = 3.0   # Bull Snort candle: min vol ratio
DEFAULT_CLOSE_POSITION_MIN    = 0.65  # Bull Snort candle: min close position (top 35%)
DEFAULT_MIN_GAP_HISTORY       = 10.0  # Phase 1: price must have been 10%+ below DMA
DEFAULT_MAX_CURRENT_GAP       = 5.0   # Phase 2: price must be within 5% of DMA now
BASE_LOOKBACK_DAYS             = 126   # 6 months of trading days
BASE_NO_NEW_LOW_WINDOW         = 10    # Phase 2: no new low in last N sessions


def compute_bull_snort(
    symbol: str,
    vol_avg_period: int        = DEFAULT_VOL_AVG_PERIOD,
    vol_surge_min: float       = DEFAULT_VOL_SURGE_MIN,
    close_position_min: float  = DEFAULT_CLOSE_POSITION_MIN,
    min_gap_history: float     = DEFAULT_MIN_GAP_HISTORY,
    max_current_gap: float     = DEFAULT_MAX_CURRENT_GAP,
) -> dict | None:
    """
    Full 4-phase Bull Snort evaluation for a single symbol.

    Phase 1: Prolonged downtrend (was deeply below 200 DMA, DMA still declining)
    Phase 2: Base formed (not making new lows, price approaching 200 DMA)
    Phase 3: Volume accumulation during base (scoring bonus)
    Phase 4: Bull Snort candle fires today

    Returns result dict or None if any required phase fails.
    """
    try:
        # ----------------------------------------------------------------
        # Fetch data — need 220+ days for 200 DMA + 6-month base lookback
        # ----------------------------------------------------------------
        df = fetch_historical_prices(symbol, period='2y')
        if df is None or len(df) < 230:
            logger.warning(f"{symbol}: insufficient data")
            return None

        df     = df.sort_index()
        close  = df['Close']
        volume = df['Volume']
        high   = df['High']
        low    = df['Low']

        dma200 = close.rolling(200).mean()
        if np.isnan(dma200.iloc[-1]):
            return None

        # ============================================================
        # PHASE 1 — Prolonged Downtrend
        # ============================================================

        # Was price ever 10%+ below DMA in last 6 months?
        gap_series   = (dma200 - close) / close * 100   # positive = below DMA
        max_gap_6mo  = gap_series.iloc[-BASE_LOOKBACK_DAYS:].max()
        was_deep     = max_gap_6mo >= min_gap_history

        if not was_deep:
            return None

        # Is 200 DMA still declining?
        dma_slope    = (dma200.iloc[-1] - dma200.iloc[-21]) / 20
        norm_slope   = (dma_slope / dma200.iloc[-1]) * 100
        dma_declining = norm_slope < 0.0

        if not dma_declining:
            return None

        # ============================================================
        # PHASE 2 — Base Formation
        # ============================================================

        # Price not making new lows (base is forming)
        recent_lows    = close.iloc[-(BASE_NO_NEW_LOW_WINDOW + 1):-1]
        is_not_new_low = close.iloc[-1] >= recent_lows.min()

        if not is_not_new_low:
            return None

        # Price now within max_current_gap% of 200 DMA (gap closing)
        current_gap    = (dma200.iloc[-1] - close.iloc[-1]) / close.iloc[-1] * 100
        is_near_dma    = 0.0 <= current_gap <= max_current_gap

        if not is_near_dma:
            return None

        # ============================================================
        # PHASE 3 — Base Volume Accumulation Score
        # ============================================================
        accum_result = _score_base_accumulation(
            close, volume, dma200, BASE_LOOKBACK_DAYS
        )

        # ============================================================
        # PHASE 4 — Bull Snort Candle
        # ============================================================
        today_close = close.iloc[-1]
        prev_close  = close.iloc[-2]
        today_high  = high.iloc[-1]
        today_low   = low.iloc[-1]
        today_open  = df['Open'].iloc[-1]
        today_vol   = volume.iloc[-1]

        avg_vol     = volume.iloc[-(vol_avg_period + 1):-1].mean()
        vol_ratio   = today_vol / avg_vol if avg_vol > 0 else 0

        is_vol_surge    = vol_ratio >= vol_surge_min
        is_positive     = today_close > prev_close
        pct_change      = (today_close - prev_close) / prev_close * 100

        candle_range    = today_high - today_low
        if candle_range == 0:
            return None
        close_position  = (today_close - today_low) / candle_range
        is_strong_close = close_position >= close_position_min

        if not (is_vol_surge and is_positive and is_strong_close):
            return None

        # ============================================================
        # Final Score
        # ============================================================
        final_score = _compute_final_score(
            vol_ratio      = vol_ratio,
            vol_surge_min  = vol_surge_min,
            pct_change     = pct_change,
            close_position = close_position,
            accum_score    = accum_result['accumulation_score'],
            current_gap    = current_gap,
            max_gap_6mo    = max_gap_6mo,
        )

        return {
            'symbol'              : symbol,
            'date'                : str(df.index[-1].date()),
            # Candle
            'open'                : round(today_open, 2),
            'high'                : round(today_high, 2),
            'low'                 : round(today_low, 2),
            'close'               : round(today_close, 2),
            'prev_close'          : round(prev_close, 2),
            'pct_change'          : round(pct_change, 2),
            # Volume
            'volume'              : int(today_vol),
            'avg_volume'          : int(avg_vol),
            'vol_ratio'           : round(vol_ratio, 2),
            # Candle strength
            'close_position'      : round(close_position, 3),
            'candle_range'        : round(candle_range, 2),
            # DMA context
            'dma200'              : round(dma200.iloc[-1], 2),
            'current_gap_pct'     : round(current_gap, 2),
            'max_gap_6mo_pct'     : round(max_gap_6mo, 2),
            'dma_slope_norm'      : round(norm_slope, 4),
            # Base accumulation
            'n_vol_pivots'        : accum_result['n_pivots'],
            'n_vol_surges'        : accum_result['n_surges'],
            'accumulation_score'  : round(accum_result['accumulation_score'], 1),
            # Final score
            'score'               : round(final_score, 1),
        }

    except Exception as e:
        logger.error(f"compute_bull_snort error [{symbol}]: {e}")
        return None


def screen_bull_snort(
    symbols: list[str],
    vol_avg_period: int       = DEFAULT_VOL_AVG_PERIOD,
    vol_surge_min: float      = DEFAULT_VOL_SURGE_MIN,
    close_position_min: float = DEFAULT_CLOSE_POSITION_MIN,
    min_gap_history: float    = DEFAULT_MIN_GAP_HISTORY,
    max_current_gap: float    = DEFAULT_MAX_CURRENT_GAP,
) -> list[dict]:
    """
    Screen all symbols for Bull Snort signal.
    Returns list sorted by final score descending.
    """
    results = []
    for symbol in symbols:
        result = compute_bull_snort(
            symbol,
            vol_avg_period     = vol_avg_period,
            vol_surge_min      = vol_surge_min,
            close_position_min = close_position_min,
            min_gap_history    = min_gap_history,
            max_current_gap    = max_current_gap,
        )
        if result:
            results.append(result)

    results.sort(key=lambda x: x['score'], reverse=True)
    logger.info(f"Bull Snort screen: {len(results)} signals from {len(symbols)} symbols")
    return results


# ---------------------------------------------------------------------------
# Phase 3: Base Volume Accumulation
# ---------------------------------------------------------------------------

def _detect_volume_pivots(volume_series, neighbours=2) -> int:
    """
    Count local volume peaks: higher than 'neighbours' bars on each side.
    These represent discrete institutional buying bursts during the base.
    """
    count = 0
    vals  = volume_series.values
    for i in range(neighbours, len(vals) - neighbours):
        window = vals[i - neighbours: i + neighbours + 1]
        if vals[i] == window.max() and vals[i] > window.mean() * 1.5:
            count += 1
    return count


def _detect_volume_surges(volume_series, avg_period=20, multiplier=2.0) -> int:
    """
    Count days where volume >= multiplier * its rolling average.
    These are institutional accumulation days during the base.
    """
    avg = volume_series.rolling(avg_period, min_periods=5).mean()
    return int((volume_series >= avg * multiplier).sum())


def _score_base_accumulation(close, volume, dma200, lookback) -> dict:
    """
    Score institutional volume accumulation during the base period.
    Only counts volume events while price was BELOW the 200 DMA.
    """
    base_close  = close.iloc[-lookback:]
    base_vol    = volume.iloc[-lookback:]
    base_dma    = dma200.iloc[-lookback:]

    # Only look at days where price was below 200 DMA
    below_mask  = base_close < base_dma
    vol_below   = base_vol[below_mask]

    if len(vol_below) < 10:
        return {'n_pivots': 0, 'n_surges': 0, 'accumulation_score': 0}

    n_pivots = _detect_volume_pivots(vol_below)
    n_surges = _detect_volume_surges(vol_below)

    # 5+ pivots OR 3+ surges = full score on each component
    pivot_score = min(n_pivots / 5.0, 1.0) * 100
    surge_score = min(n_surges / 3.0, 1.0) * 100
    accum_score = (pivot_score * 0.5) + (surge_score * 0.5)

    return {
        'n_pivots'           : n_pivots,
        'n_surges'           : n_surges,
        'pivot_score'        : round(pivot_score, 1),
        'surge_score'        : round(surge_score, 1),
        'accumulation_score' : round(accum_score, 1),
    }


# ---------------------------------------------------------------------------
# Final Scoring
# ---------------------------------------------------------------------------

def _compute_final_score(
    vol_ratio: float,
    vol_surge_min: float,
    pct_change: float,
    close_position: float,
    accum_score: float,
    current_gap: float,
    max_gap_6mo: float,
) -> float:
    """
    Blend 5 components into a final 0–100 Bull Snort score.

    Weights:
      Accumulation score (Phase 3)  : 30%  — institutional base building
      Volume surge (Phase 4)        : 25%  — conviction of the breakout candle
      Close position (Phase 4)      : 20%  — buying held into close
      Depth of recovery             : 15%  — how far price climbed from the base
      Price change % today          : 10%  — magnitude of the move
    """
    # Accumulation: already 0–100
    accum_component = accum_score

    # Volume surge: 3x = 0pts baseline, 6x = 100pts
    vol_component   = min((vol_ratio - vol_surge_min) / vol_surge_min, 1.0) * 100
    vol_component   = max(vol_component, 0)

    # Close position: 0.65 = 0pts, 1.0 = 100pts
    close_component = min((close_position - 0.65) / 0.35, 1.0) * 100
    close_component = max(close_component, 0)

    # Depth of recovery: was 10%+ below, now within 5%
    # Score how much of the gap has been closed: (max_gap - current_gap) / max_gap
    gap_closed      = max_gap_6mo - current_gap
    depth_component = min(gap_closed / max_gap_6mo, 1.0) * 100
    depth_component = max(depth_component, 0)

    # Price change: 0% = 0pts, 3%+ = 100pts
    price_component = min(pct_change / 3.0, 1.0) * 100
    price_component = max(price_component, 0)

    return (
        accum_component * 0.30 +
        vol_component   * 0.25 +
        close_component * 0.20 +
        depth_component * 0.15 +
        price_component * 0.10
    )
```

---

## API Endpoint `bull_snort.py`

Create at `app/api/v1/bull_snort.py`:

```python
from flask import Blueprint, jsonify, request, current_app
from app.services.bull_snort_service import screen_bull_snort, compute_bull_snort
from app.database import get_nse_symbols

bull_snort_bp = Blueprint('bull_snort', __name__)


@bull_snort_bp.route('/bull-snort/screen', methods=['GET'])
def bull_snort_screen():
    """
    GET /api/bull-snort/screen

    Query params (all optional):
      vol_avg_period     : int   (default: 20)
      vol_surge_min      : float (default: 3.0)
      close_position_min : float (default: 0.65)
      min_gap_history    : float (default: 10.0  — must have been 10% below DMA)
      max_current_gap    : float (default: 5.0   — now within 5% of DMA)
    """
    try:
        params = {
            'vol_avg_period'     : int(request.args.get('vol_avg_period', 20)),
            'vol_surge_min'      : float(request.args.get('vol_surge_min', 3.0)),
            'close_position_min' : float(request.args.get('close_position_min', 0.65)),
            'min_gap_history'    : float(request.args.get('min_gap_history', 10.0)),
            'max_current_gap'    : float(request.args.get('max_current_gap', 5.0)),
        }
        symbols = get_nse_symbols()
        results = screen_bull_snort(symbols, **params)
        return jsonify({'status': 'ok', 'count': len(results), 'data': results})

    except Exception as e:
        current_app.logger.error(f"bull_snort_screen error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bull_snort_bp.route('/bull-snort/single', methods=['GET'])
def bull_snort_single():
    """
    GET /api/bull-snort/single?symbol=RELIANCE.NS
    """
    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify({'status': 'error', 'message': 'symbol param required'}), 400
    result = compute_bull_snort(symbol)
    if result is None:
        return jsonify({'status': 'ok', 'signal': False, 'symbol': symbol})
    return jsonify({'status': 'ok', 'signal': True, 'data': result})
```

### Register in `app/__init__.py`
```python
from .api.v1.bull_snort import bull_snort_bp
app.register_blueprint(bull_snort_bp, url_prefix='/api')
```

---

## Scheduler Integration

```python
def refresh_bull_snort(app):
    with app.app_context():
        try:
            from app.database import get_nse_symbols
            from app.services.bull_snort_service import screen_bull_snort
            import pandas as pd
            symbols = get_nse_symbols()
            results = screen_bull_snort(symbols)
            app.config['BULL_SNORT_CACHE'] = {
                'data': results, 'count': len(results),
                'refreshed': pd.Timestamp.now().isoformat()
            }
            logger.info(f"Bull Snort: {len(results)} signals")
        except Exception as e:
            logger.error(f"Bull Snort scheduler error: {e}")

scheduler.add_job(
    func=refresh_bull_snort, args=[app],
    trigger='cron', hour=16, minute=5,
    id='bull_snort_refresh', replace_existing=True
)
```

---

## Scoring Model

### Phase 3 — Base Accumulation Score (0–100)

| Component | Weight | 0 pts | 100 pts |
|---|---|---|---|
| Volume Pivots (below DMA) | 50% | 0 pivots | 5+ pivots |
| Volume Surges (below DMA) | 50% | 0 surges | 3+ surges |

### Final Score (0–100)

| Component | Weight | 0 pts | 100 pts |
|---|---|---|---|
| **Base Accumulation** (Phase 3) | 30% | No vol events | 5 pivots + 3 surges |
| **Bull Snort Vol Ratio** (Phase 4) | 25% | 3x (minimum) | 6x avg |
| **Close Position** (Phase 4) | 20% | 0.65 (top 35%) | 1.0 (at the high) |
| **Gap Recovery Depth** | 15% | No gap closed | Full gap closed |
| **Price Change %** | 10% | 0% | 3%+ |

**Score bands:**
- 75–100 → 🟢 **High Conviction** — strong base + explosive breakout candle
- 50–74  → 🟡 **Moderate** — valid signal, lower institutional conviction
- Below 50 → 🔴 **Weak** — barely qualifies, needs additional confirmation

---

## UI Plan

### New Tab in `index.html`
```html
<button class="tab-btn" data-view="bull-snort">🐂 Bull Snort</button>

<div id="view-bull-snort" class="view-section" style="display:none;">
  <div class="filter-bar">
    <label>Vol Avg Period:
      <select id="bs-vol-period">
        <option value="10">10-day</option>
        <option value="20" selected>20-day</option>
        <option value="50">50-day</option>
      </select>
    </label>
    <label>Min Vol Surge: <input type="number" id="bs-vol-surge" value="3" step="0.5" min="1.5"></label>
    <label>Min Gap History %: <input type="number" id="bs-min-gap" value="10" step="1" min="5"></label>
    <label>Max Current Gap %: <input type="number" id="bs-max-gap" value="5" step="1" min="0"></label>
    <button id="btn-run-bull-snort">🔍 Run Screen</button>
  </div>

  <div id="bs-results-count" style="margin:8px 0; font-weight:bold;"></div>

  <table id="bull-snort-table">
    <thead>
      <tr>
        <th>Symbol</th>
        <th>Close</th>
        <th>Change %</th>
        <th>Vol Ratio</th>
        <th>Close Pos</th>
        <th>200 DMA</th>
        <th>Gap Now</th>
        <th>Max Gap 6mo</th>
        <th>Vol Pivots</th>
        <th>Vol Surges</th>
        <th>Accum Score</th>
        <th>Final Score</th>
      </tr>
    </thead>
    <tbody id="bull-snort-tbody"></tbody>
  </table>
</div>
```

### JavaScript in `app.js`
```javascript
document.getElementById('btn-run-bull-snort').addEventListener('click', async () => {
  const params = new URLSearchParams({
    vol_avg_period  : document.getElementById('bs-vol-period').value,
    vol_surge_min   : document.getElementById('bs-vol-surge').value,
    min_gap_history : document.getElementById('bs-min-gap').value,
    max_current_gap : document.getElementById('bs-max-gap').value,
  });

  const res  = await fetch(`/api/bull-snort/screen?${params}`);
  const json = await res.json();

  document.getElementById('bs-results-count').textContent =
    `🐂 ${json.count} Bull Snort signals found`;

  const tbody = document.getElementById('bull-snort-tbody');
  tbody.innerHTML = '';

  json.data.forEach(row => {
    const scoreColor  = row.score >= 75 ? '#22c55e' : row.score >= 50 ? '#f59e0b' : '#ef4444';
    const accumColor  = row.accumulation_score >= 70 ? '#22c55e'
                      : row.accumulation_score >= 40 ? '#f59e0b' : '#94a3b8';
    const changeColor = row.pct_change >= 0 ? '#22c55e' : '#ef4444';

    tbody.innerHTML += `
      <tr>
        <td><strong>${row.symbol}</strong></td>
        <td>₹${row.close}</td>
        <td style="color:${changeColor}">${row.pct_change > 0 ? '+' : ''}${row.pct_change}%</td>
        <td>${row.vol_ratio}x</td>
        <td>${(row.close_position * 100).toFixed(1)}%</td>
        <td>${row.dma200}</td>
        <td>${row.current_gap_pct}%</td>
        <td>${row.max_gap_6mo_pct}%</td>
        <td>${row.n_vol_pivots}</td>
        <td>${row.n_vol_surges}</td>
        <td style="color:${accumColor}"><strong>${row.accumulation_score}</strong></td>
        <td style="color:${scoreColor}"><strong>${row.score}</strong></td>
      </tr>`;
  });
});
```

---

## Build Order

1. Write `bull_snort_service.py` — test with `compute_bull_snort('RELIANCE.NS')`
2. Test `_score_base_accumulation` standalone on a few known basing stocks
3. Add `bull_snort.py` endpoint — test via browser
4. Register blueprint in `app/__init__.py`
5. Add scheduler job
6. Add UI tab + JS
7. **Backtest**: replay the filter on past dates where you identified these patterns

---

## Test Cases

```python
# tests/test_bull_snort.py

def test_phase1_fails_if_never_deep_below_dma():
    # max_gap_6mo < 10% → None
    ...

def test_phase1_fails_if_dma_rising():
    # norm_dma_slope > 0 → None
    ...

def test_phase2_fails_if_making_new_lows():
    # today_close < recent_10d_min → None
    ...

def test_phase2_fails_if_still_far_from_dma():
    # current_gap > 5% → None
    ...

def test_phase3_accumulation_score_zero_with_no_vol_events():
    # flat volume base → accumulation_score == 0
    ...

def test_phase3_more_pivots_gives_higher_accumulation():
    # 5 pivots > 2 pivots in score
    ...

def test_phase4_fails_if_volume_below_3x():
    # vol_ratio = 2.5 → None
    ...

def test_phase4_fails_if_negative_close():
    # today_close < prev_close → None
    ...

def test_phase4_fails_if_close_in_lower_half():
    # close_position = 0.4 → None
    ...

def test_higher_accumulation_scores_higher_overall():
    # same candle, more vol pivots during base → higher final score
    ...

def test_screen_returns_sorted_descending():
    # results[0].score >= results[-1].score
    ...
```
