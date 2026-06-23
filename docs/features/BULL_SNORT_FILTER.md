# Bull Snort Filter — Design & Implementation Guide

The **Bull Snort** is an institutional accumulation signal that fires when three conditions align:
1. The 200 DMA slope is curling upward (smoothing out)
2. Price breaks out above a key level with conviction
3. Volume is significantly above its 20-day average

---

## Table of Contents
- [Signal Definition](#signal-definition)
- [Codebase Structure](#codebase-structure)
- [bull_snort_service.py](#bull_snort_servicepy)
- [API Endpoint](#api-endpoint-bull_snortpy)
- [Scheduler Integration](#scheduler-integration)
- [UI Plan](#ui-plan)
- [Scoring Model](#scoring-model)

---

## Signal Definition

### 1. 200 DMA Smoothing Out
The slope of the 200 DMA must be turning positive. Normalised to price so it works across all price ranges.

```
normalised_slope = (DMA_200[today] - DMA_200[10 days ago]) / (DMA_200[today] * 10) * 100
smoothing_out = normalised_slope > 0.02   # 0.02% per day minimum
```

### 2. Price Breakout
Two supported modes (configurable):
- `dma200`: Close > 200 DMA (reclaim of long-term average)
- `n_day_high`: Close > highest close in last N days AND 200 DMA slope is positive

### 3. Volume Surge
```
vol_ratio = today_volume / avg_volume_20d
heavy_volume = vol_ratio > 1.5   # 50% above 20-day average
```

---

## Codebase Structure

```
app/
├── services/
│   └── bull_snort_service.py       ← Core screening logic
├── api/v1/
│   └── bull_snort.py               ← REST API endpoint
├── tasks/
│   └── scheduler.py                ← Add refresh job here
templates/
└── index.html                      ← Add Bull Snort tab
static/js/
└── app.js                          ← Add UI handler
```

---

## `bull_snort_service.py`

Create at `app/services/bull_snort_service.py`:

```python
import logging
import pandas as pd
import numpy as np
from app.utils.technical import fetch_historical_prices

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — tune these per your backtesting
# ---------------------------------------------------------------------------
DEFAULT_SLOPE_THRESHOLD = 0.02      # normalised % per day
DEFAULT_VOL_RATIO_MIN   = 1.5       # 1.5x the 20-day average volume
DEFAULT_SLOPE_LOOKBACK  = 10        # days to measure DMA slope over
DEFAULT_BREAKOUT_DAYS   = 20        # N-day high lookback
MAX_SIGNAL_AGE_DAYS     = 10        # ignore signals older than this


def compute_bull_snort_score(
    symbol: str,
    slope_threshold: float = DEFAULT_SLOPE_THRESHOLD,
    vol_ratio_min: float = DEFAULT_VOL_RATIO_MIN,
    breakout_type: str = 'dma200',
    breakout_days: int = DEFAULT_BREAKOUT_DAYS,
    slope_lookback: int = DEFAULT_SLOPE_LOOKBACK,
) -> dict | None:
    """
    Compute Bull Snort score for a single symbol.

    Returns a dict with score and component breakdown, or None if
    insufficient data or signal conditions are not met.

    Parameters
    ----------
    symbol        : NSE ticker e.g. 'RELIANCE.NS'
    slope_threshold : minimum normalised DMA slope (% per day)
    vol_ratio_min : minimum volume ratio vs 20-day avg
    breakout_type : 'dma200' or 'n_day_high'
    breakout_days : lookback for n_day_high mode
    slope_lookback: days over which to measure DMA slope
    """
    try:
        # ----------------------------------------------------------------
        # 1. Fetch historical data (need 220+ days for a clean 200 DMA)
        # ----------------------------------------------------------------
        df = fetch_historical_prices(symbol, period='1y')
        if df is None or len(df) < 210:
            logger.warning(f"{symbol}: insufficient data ({len(df) if df is not None else 0} rows)")
            return None

        df = df.sort_index()
        close  = df['Close']
        volume = df['Volume']

        # ----------------------------------------------------------------
        # 2. Compute 200 DMA
        # ----------------------------------------------------------------
        dma200 = close.rolling(200).mean()
        if dma200.iloc[-1] is None or np.isnan(dma200.iloc[-1]):
            return None

        # ----------------------------------------------------------------
        # 3. Compute normalised DMA slope
        # ----------------------------------------------------------------
        dma_today     = dma200.iloc[-1]
        dma_n_ago     = dma200.iloc[-(slope_lookback + 1)]
        raw_slope     = (dma_today - dma_n_ago) / slope_lookback
        norm_slope    = (raw_slope / dma_today) * 100   # % per day
        is_smoothing  = norm_slope > slope_threshold

        # ----------------------------------------------------------------
        # 4. Compute breakout condition
        # ----------------------------------------------------------------
        today_close = close.iloc[-1]

        if breakout_type == 'dma200':
            is_breakout = today_close > dma_today
            breakout_ref = dma_today
        else:  # n_day_high
            n_day_high   = close.iloc[-(breakout_days + 1):-1].max()
            is_breakout  = today_close > n_day_high
            breakout_ref = n_day_high

        # ----------------------------------------------------------------
        # 5. Compute volume surge
        # ----------------------------------------------------------------
        avg_vol_20d  = volume.iloc[-21:-1].mean()   # exclude today
        today_vol    = volume.iloc[-1]
        vol_ratio    = today_vol / avg_vol_20d if avg_vol_20d > 0 else 0
        is_heavy_vol = vol_ratio >= vol_ratio_min

        # ----------------------------------------------------------------
        # 6. All three conditions must be true for a valid signal
        # ----------------------------------------------------------------
        if not (is_smoothing and is_breakout and is_heavy_vol):
            return None

        # ----------------------------------------------------------------
        # 7. Compute signal age (how many consecutive days conditions hold)
        # ----------------------------------------------------------------
        signal_age = _compute_signal_age(
            close, dma200, volume, avg_vol_20d,
            slope_threshold, vol_ratio_min, breakout_type,
            breakout_ref, slope_lookback
        )
        if signal_age > MAX_SIGNAL_AGE_DAYS:
            return None   # signal is too old / extended

        # ----------------------------------------------------------------
        # 8. Score each component and blend into final 0-100 score
        # ----------------------------------------------------------------
        slope_score  = min(norm_slope / (slope_threshold * 5), 1.0) * 100
        vol_score    = min((vol_ratio - 1) / 2.0, 1.0) * 100   # caps at 3x
        price_dist   = abs(today_close - breakout_ref) / breakout_ref * 100
        fresh_score  = max(0, 100 - (price_dist * 10))          # fresher = less distance
        age_score    = max(0, 100 - (signal_age - 1) * 12)      # 1 day=100, 9 days~4

        bull_snort_score = (
            slope_score * 0.35 +
            vol_score   * 0.35 +
            fresh_score * 0.20 +
            age_score   * 0.10
        )

        return {
            'symbol'          : symbol,
            'cmp'             : round(today_close, 2),
            'dma200'          : round(dma_today, 2),
            'norm_slope_pct'  : round(norm_slope, 4),
            'vol_ratio'       : round(vol_ratio, 2),
            'breakout_type'   : breakout_type,
            'breakout_ref'    : round(breakout_ref, 2),
            'signal_age_days' : signal_age,
            'score'           : round(bull_snort_score, 1),
            'slope_score'     : round(slope_score, 1),
            'vol_score'       : round(vol_score, 1),
            'fresh_score'     : round(fresh_score, 1),
            'age_score'       : round(age_score, 1),
            'signal_label'    : _signal_label(signal_age),
        }

    except Exception as e:
        logger.error(f"bull_snort: error processing {symbol}: {e}")
        return None


def screen_bull_snort(
    symbols: list[str],
    slope_threshold: float = DEFAULT_SLOPE_THRESHOLD,
    vol_ratio_min: float   = DEFAULT_VOL_RATIO_MIN,
    breakout_type: str     = 'dma200',
    breakout_days: int     = DEFAULT_BREAKOUT_DAYS,
) -> list[dict]:
    """
    Run Bull Snort screen across a list of symbols.
    Returns list of qualifying stocks sorted by score descending.
    """
    results = []
    for symbol in symbols:
        result = compute_bull_snort_score(
            symbol,
            slope_threshold=slope_threshold,
            vol_ratio_min=vol_ratio_min,
            breakout_type=breakout_type,
            breakout_days=breakout_days,
        )
        if result:
            results.append(result)

    results.sort(key=lambda x: x['score'], reverse=True)
    logger.info(f"Bull Snort screen: {len(results)} signals from {len(symbols)} symbols")
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_signal_age(
    close, dma200, volume, avg_vol_20d,
    slope_threshold, vol_ratio_min,
    breakout_type, breakout_ref, slope_lookback
) -> int:
    """
    Walk backwards from today to find how many consecutive days
    the bull snort conditions have been satisfied.
    """
    age = 0
    for i in range(1, 11):   # check up to 10 days back
        idx = -(i)
        try:
            c      = close.iloc[idx]
            dma    = dma200.iloc[idx]
            dma_lb = dma200.iloc[idx - slope_lookback]
            slope  = ((dma - dma_lb) / slope_lookback / dma) * 100
            vol    = volume.iloc[idx] / avg_vol_20d

            if breakout_type == 'dma200':
                bo = c > dma
            else:
                bo = c > breakout_ref

            if slope > slope_threshold and bo and vol >= vol_ratio_min:
                age += 1
            else:
                break
        except Exception:
            break
    return age


def _signal_label(age: int) -> str:
    if age <= 3:
        return 'Fresh'
    elif age <= 7:
        return 'Active'
    else:
        return 'Extended'
```

---

## API Endpoint `bull_snort.py`

Create at `app/api/v1/bull_snort.py`:

```python
from flask import Blueprint, jsonify, request, current_app
from app.services.bull_snort_service import screen_bull_snort
from app.database import get_nse_symbols   # or however you load your symbol list

bull_snort_bp = Blueprint('bull_snort', __name__)


@bull_snort_bp.route('/bull-snort/screen', methods=['GET'])
def bull_snort_screen():
    """
    GET /api/bull-snort/screen

    Query params:
      breakout_type  : 'dma200' or 'n_day_high' (default: dma200)
      breakout_days  : int (default: 20, used for n_day_high only)
      slope_threshold: float (default: 0.02)
      vol_ratio_min  : float (default: 1.5)
    """
    try:
        breakout_type   = request.args.get('breakout_type', 'dma200')
        breakout_days   = int(request.args.get('breakout_days', 20))
        slope_threshold = float(request.args.get('slope_threshold', 0.02))
        vol_ratio_min   = float(request.args.get('vol_ratio_min', 1.5))

        symbols = get_nse_symbols()   # your existing symbol list function

        results = screen_bull_snort(
            symbols,
            slope_threshold=slope_threshold,
            vol_ratio_min=vol_ratio_min,
            breakout_type=breakout_type,
            breakout_days=breakout_days,
        )

        return jsonify({
            'status' : 'ok',
            'count'  : len(results),
            'data'   : results
        })

    except Exception as e:
        current_app.logger.error(f"bull_snort_screen error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bull_snort_bp.route('/bull-snort/single', methods=['GET'])
def bull_snort_single():
    """
    GET /api/bull-snort/single?symbol=RELIANCE.NS
    Score a single symbol.
    """
    from app.services.bull_snort_service import compute_bull_snort_score
    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify({'status': 'error', 'message': 'symbol param required'}), 400

    result = compute_bull_snort_score(symbol)
    if result is None:
        return jsonify({'status': 'ok', 'signal': False, 'symbol': symbol})
    return jsonify({'status': 'ok', 'signal': True, 'data': result})
```

### Register the blueprint in `app/__init__.py`

Add inside `create_app()` after the existing blueprint registrations:
```python
from .api.v1.bull_snort import bull_snort_bp
app.register_blueprint(bull_snort_bp, url_prefix='/api')
```

---

## Scheduler Integration

In `app/tasks/scheduler.py`, add a refresh job alongside your existing EP screener job:

```python
from app.services.bull_snort_service import screen_bull_snort

def refresh_bull_snort(app):
    """Scheduled job — refresh Bull Snort signals."""
    with app.app_context():
        try:
            from app.database import get_nse_symbols
            symbols = get_nse_symbols()
            results = screen_bull_snort(symbols)
            # Cache results in app config or a simple module-level dict
            app.config['BULL_SNORT_CACHE'] = {
                'data'      : results,
                'count'     : len(results),
                'refreshed' : pd.Timestamp.now().isoformat()
            }
            logger.info(f"Bull Snort refresh complete: {len(results)} signals")
        except Exception as e:
            logger.error(f"Bull Snort scheduler error: {e}")

# Add to your scheduler init — runs once after market close
scheduler.add_job(
    func=refresh_bull_snort,
    args=[app],
    trigger='cron',
    hour=16,
    minute=15,
    id='bull_snort_refresh',
    replace_existing=True
)
```

---

## UI Plan

### New Tab in `index.html`
```html
<!-- Add alongside existing tabs -->
<button class="tab-btn" data-view="bull-snort">🐂 Bull Snort</button>

<!-- View container -->
<div id="view-bull-snort" class="view-section" style="display:none;">
  <div class="filter-bar">
    <label>Breakout Type:
      <select id="bs-breakout-type">
        <option value="dma200">200 DMA Reclaim</option>
        <option value="n_day_high">N-Day High</option>
      </select>
    </label>
    <label>Min Volume Ratio:
      <input type="number" id="bs-vol-ratio" value="1.5" step="0.1" min="1.0">
    </label>
    <button id="btn-run-bull-snort">Run Screen</button>
  </div>

  <div id="bs-results-count"></div>

  <table id="bull-snort-table">
    <thead>
      <tr>
        <th>Symbol</th>
        <th>CMP</th>
        <th>200 DMA</th>
        <th>DMA Slope %</th>
        <th>Vol Ratio</th>
        <th>Signal Age</th>
        <th>Status</th>
        <th>Score</th>
      </tr>
    </thead>
    <tbody id="bull-snort-tbody"></tbody>
  </table>
</div>
```

### JavaScript in `app.js`
```javascript
document.getElementById('btn-run-bull-snort').addEventListener('click', async () => {
  const breakoutType = document.getElementById('bs-breakout-type').value;
  const volRatio     = document.getElementById('bs-vol-ratio').value;

  const res  = await fetch(`/api/bull-snort/screen?breakout_type=${breakoutType}&vol_ratio_min=${volRatio}`);
  const json = await res.json();

  document.getElementById('bs-results-count').textContent = `${json.count} signals found`;

  const tbody = document.getElementById('bull-snort-tbody');
  tbody.innerHTML = '';

  json.data.forEach(row => {
    const labelColor = row.signal_label === 'Fresh' ? 'green'
                     : row.signal_label === 'Active' ? 'orange' : 'red';
    tbody.innerHTML += `
      <tr>
        <td>${row.symbol}</td>
        <td>${row.cmp}</td>
        <td>${row.dma200}</td>
        <td>${row.norm_slope_pct}%</td>
        <td>${row.vol_ratio}x</td>
        <td>${row.signal_age_days}d</td>
        <td style="color:${labelColor}">${row.signal_label}</td>
        <td><strong>${row.score}</strong></td>
      </tr>`;
  });
});
```

---

## Scoring Model

| Component | Weight | Logic |
|---|---|---|
| DMA Slope strength | 35% | Higher normalised slope = higher score, capped at 5x threshold |
| Volume surge | 35% | Scaled from 1x to 3x avg volume, capped at 3x |
| Price freshness | 20% | Less distance from breakout level = fresher = higher |
| Signal age | 10% | Day 1 = 100pts, decays by 12pts/day, zero at day 9 |

**Score bands:**
- 75–100 → Strong Bull Snort ✅
- 50–74  → Moderate signal ⚠️
- Below 50 → Weak / extended ❌

---

## Suggested Build Order

1. `bull_snort_service.py` — write and test standalone with 5 tickers
2. `bull_snort.py` API endpoint — test via curl/Postman
3. Register blueprint in `app/__init__.py`
4. Add scheduler job in `scheduler.py`
5. Add UI tab + JS last
6. Write unit tests in `tests/test_bull_snort.py`

---

## Test Cases to Write

```python
# tests/test_bull_snort.py

def test_score_returns_none_for_insufficient_data():
    # mock fetch_historical_prices to return < 210 rows
    ...

def test_score_returns_none_if_volume_flat():
    # vol_ratio < 1.5 should return None
    ...

def test_score_returns_none_if_slope_negative():
    # downward sloping 200 DMA should return None
    ...

def test_fresh_signal_scores_higher_than_extended():
    # signal_age=1 should score higher than signal_age=8
    ...

def test_screen_returns_sorted_by_score():
    # results[0].score >= results[1].score
    ...
```
