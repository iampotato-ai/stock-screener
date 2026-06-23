# Bull Snort Filter — Design & Implementation Guide

The **Bull Snort** is a single-day institutional accumulation signal. It fires when **all three** of the following conditions are true on the same trading day:

| # | Condition | Rule |
|---|---|---|
| 1 | **Volume Surge** | Volume ≥ 3× the 10, 20, or 50-day average volume |
| 2 | **Positive Price Move** | Close > previous day's close |
| 3 | **Strong Close** | Close is in the top 35% of the day's candle range |

> No 200 DMA slope required — this is a pure single-candle momentum + volume signal.

---

## Table of Contents
- [Signal Math](#signal-math)
- [Codebase Structure](#codebase-structure)
- [bull_snort_service.py](#bull_snort_servicepy)
- [API Endpoint](#api-endpoint-bull_snortpy)
- [Scheduler Integration](#scheduler-integration)
- [Scoring Model](#scoring-model)
- [UI Plan](#ui-plan)
- [Build Order & Test Cases](#build-order--test-cases)

---

## Signal Math

### Condition 1 — Volume Surge
```
vol_ratio = today_volume / avg_volume_N
is_volume_surge = vol_ratio >= 3.0
```
Where `avg_volume_N` is the rolling mean of the last N days (configurable: 10, 20, or 50). Exclude today from the average.

### Condition 2 — Positive Price Move
```
is_positive_close = today_close > prev_close
```
Simple — today must close above yesterday's close.

### Condition 3 — Strong Close (Top 35% of Range)
```
candle_range   = today_high - today_low
close_position = (today_close - today_low) / candle_range   # 0.0 = bottom, 1.0 = top
is_strong_close = close_position >= 0.65   # top 35% means position >= 65th percentile
```

### All Three Must Be True
```
bull_snort = is_volume_surge AND is_positive_close AND is_strong_close
```

---

## Codebase Structure

```
app/
├── services/
│   └── bull_snort_service.py       ← Core screening + scoring logic
├── api/v1/
│   └── bull_snort.py               ← REST API endpoints
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
import numpy as np
from app.utils.technical import fetch_historical_prices

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — tune per backtesting
# ---------------------------------------------------------------------------
DEFAULT_VOL_AVG_PERIOD  = 20      # rolling average period: 10, 20, or 50
DEFAULT_VOL_SURGE_MIN   = 3.0     # 3x the average volume
DEFAULT_CLOSE_POSITION  = 0.65    # close must be in top 35% of candle range
MAX_SIGNAL_AGE_DAYS     = 5       # only show signals from last 5 trading days


def compute_bull_snort(
    symbol: str,
    vol_avg_period: int   = DEFAULT_VOL_AVG_PERIOD,
    vol_surge_min: float  = DEFAULT_VOL_SURGE_MIN,
    close_position_min: float = DEFAULT_CLOSE_POSITION,
) -> dict | None:
    """
    Evaluate Bull Snort signal for a single symbol.

    Returns a result dict if all 3 conditions pass on today's candle,
    or None if signal is absent or data is insufficient.

    Parameters
    ----------
    symbol            : NSE ticker e.g. 'RELIANCE.NS'
    vol_avg_period    : rolling period for average volume (10, 20, or 50)
    vol_surge_min     : minimum volume ratio to qualify (default 3.0x)
    close_position_min: minimum close position in candle range (default 0.65)
    """
    try:
        # ----------------------------------------------------------------
        # 1. Fetch OHLCV data — need vol_avg_period + buffer days
        # ----------------------------------------------------------------
        df = fetch_historical_prices(symbol, period='3mo')
        if df is None or len(df) < vol_avg_period + 5:
            logger.warning(f"{symbol}: insufficient data")
            return None

        df = df.sort_index()

        today     = df.iloc[-1]
        prev      = df.iloc[-2]

        today_open  = today['Open']
        today_high  = today['High']
        today_low   = today['Low']
        today_close = today['Close']
        today_vol   = today['Volume']
        prev_close  = prev['Close']

        # ----------------------------------------------------------------
        # 2. Condition 1 — Volume Surge (>= 3x rolling avg, excl. today)
        # ----------------------------------------------------------------
        avg_vol    = df['Volume'].iloc[-(vol_avg_period + 1):-1].mean()
        vol_ratio  = today_vol / avg_vol if avg_vol > 0 else 0
        is_vol_surge = vol_ratio >= vol_surge_min

        # ----------------------------------------------------------------
        # 3. Condition 2 — Positive Price Move
        # ----------------------------------------------------------------
        is_positive = today_close > prev_close
        pct_change  = ((today_close - prev_close) / prev_close) * 100

        # ----------------------------------------------------------------
        # 4. Condition 3 — Strong Close (top 35% of candle range)
        # ----------------------------------------------------------------
        candle_range   = today_high - today_low
        if candle_range == 0:
            return None   # doji with no range — skip
        close_position = (today_close - today_low) / candle_range
        is_strong_close = close_position >= close_position_min

        # ----------------------------------------------------------------
        # 5. All three must pass
        # ----------------------------------------------------------------
        if not (is_vol_surge and is_positive and is_strong_close):
            return None

        # ----------------------------------------------------------------
        # 6. Score 0–100
        # ----------------------------------------------------------------
        score = _compute_score(vol_ratio, vol_surge_min, pct_change, close_position)

        return {
            'symbol'          : symbol,
            'date'            : str(df.index[-1].date()),
            'open'            : round(today_open, 2),
            'high'            : round(today_high, 2),
            'low'             : round(today_low, 2),
            'close'           : round(today_close, 2),
            'prev_close'      : round(prev_close, 2),
            'pct_change'      : round(pct_change, 2),
            'volume'          : int(today_vol),
            'avg_volume'      : int(avg_vol),
            'vol_ratio'       : round(vol_ratio, 2),
            'candle_range'    : round(candle_range, 2),
            'close_position'  : round(close_position, 3),  # 0.0–1.0
            'score'           : round(score, 1),
            'vol_avg_period'  : vol_avg_period,
        }

    except Exception as e:
        logger.error(f"compute_bull_snort error for {symbol}: {e}")
        return None


def screen_bull_snort(
    symbols: list[str],
    vol_avg_period: int       = DEFAULT_VOL_AVG_PERIOD,
    vol_surge_min: float      = DEFAULT_VOL_SURGE_MIN,
    close_position_min: float = DEFAULT_CLOSE_POSITION,
) -> list[dict]:
    """
    Run Bull Snort screen across all symbols.
    Returns qualifying stocks sorted by score descending.
    """
    results = []
    for symbol in symbols:
        result = compute_bull_snort(
            symbol,
            vol_avg_period=vol_avg_period,
            vol_surge_min=vol_surge_min,
            close_position_min=close_position_min,
        )
        if result:
            results.append(result)

    results.sort(key=lambda x: x['score'], reverse=True)
    logger.info(f"Bull Snort: {len(results)} signals from {len(symbols)} symbols")
    return results


# ---------------------------------------------------------------------------
# Internal: Scoring
# ---------------------------------------------------------------------------

def _compute_score(
    vol_ratio: float,
    vol_surge_min: float,
    pct_change: float,
    close_position: float,
) -> float:
    """
    Blend three component scores into a final 0–100 Bull Snort score.

    Weights:
      Volume surge   : 45%  — most important, signals institutional buying
      Close position : 35%  — conviction of buyers holding into close
      Price change   : 20%  — magnitude of the positive move
    """
    # Volume score — 3x = 0pts baseline, scales up, capped at 6x
    vol_score   = min((vol_ratio - vol_surge_min) / (vol_surge_min), 1.0) * 100

    # Close position score — 0.65 = 0pts baseline, 1.0 = 100pts
    close_score = min((close_position - 0.65) / 0.35, 1.0) * 100
    close_score = max(close_score, 0)

    # Price change score — 1% = ~33pts, 3%+ = 100pts
    price_score = min(pct_change / 3.0, 1.0) * 100
    price_score = max(price_score, 0)

    return (vol_score * 0.45) + (close_score * 0.35) + (price_score * 0.20)
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

    Query params:
      vol_avg_period     : int   — rolling avg period (default: 20)
      vol_surge_min      : float — minimum vol ratio (default: 3.0)
      close_position_min : float — min close position 0–1 (default: 0.65)
    """
    try:
        vol_avg_period     = int(request.args.get('vol_avg_period', 20))
        vol_surge_min      = float(request.args.get('vol_surge_min', 3.0))
        close_position_min = float(request.args.get('close_position_min', 0.65))

        symbols = get_nse_symbols()
        results = screen_bull_snort(
            symbols,
            vol_avg_period=vol_avg_period,
            vol_surge_min=vol_surge_min,
            close_position_min=close_position_min,
        )

        return jsonify({'status': 'ok', 'count': len(results), 'data': results})

    except Exception as e:
        current_app.logger.error(f"bull_snort_screen error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bull_snort_bp.route('/bull-snort/single', methods=['GET'])
def bull_snort_single():
    """
    GET /api/bull-snort/single?symbol=RELIANCE.NS
    Check Bull Snort signal for a single symbol.
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

Add inside `create_app()` after the existing blueprint registrations:
```python
from .api.v1.bull_snort import bull_snort_bp
app.register_blueprint(bull_snort_bp, url_prefix='/api')
```

---

## Scheduler Integration

In `app/tasks/scheduler.py`:

```python
def refresh_bull_snort(app):
    """Scheduled job — refresh Bull Snort signals after market close."""
    with app.app_context():
        try:
            from app.database import get_nse_symbols
            from app.services.bull_snort_service import screen_bull_snort
            import pandas as pd

            symbols = get_nse_symbols()
            results = screen_bull_snort(symbols)
            app.config['BULL_SNORT_CACHE'] = {
                'data'      : results,
                'count'     : len(results),
                'refreshed' : pd.Timestamp.now().isoformat()
            }
            logger.info(f"Bull Snort refresh: {len(results)} signals")
        except Exception as e:
            logger.error(f"Bull Snort scheduler error: {e}")

# Runs daily at 4:05 PM (after NSE close at 3:30 PM)
scheduler.add_job(
    func=refresh_bull_snort,
    args=[app],
    trigger='cron',
    hour=16,
    minute=5,
    id='bull_snort_refresh',
    replace_existing=True
)
```

---

## Scoring Model

All three conditions must pass before scoring. Score is 0–100.

| Component | Weight | Baseline (0 pts) | Max (100 pts) |
|---|---|---|---|
| **Volume surge** | 45% | 3x avg (minimum) | 6x avg |
| **Close position** | 35% | 0.65 (top 35%) | 1.0 (at high) |
| **Price change %** | 20% | 0% | 3%+ |

**Score bands:**
- 75–100 → 🟢 Strong Bull Snort — high conviction institutional day
- 50–74  → 🟡 Moderate — valid signal, lower conviction
- Below 50 → 🔴 Weak — barely qualifies, use with caution

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
    <label>Min Vol Surge:
      <input type="number" id="bs-vol-surge" value="3" step="0.5" min="1.5">
    </label>
    <label>Min Close Position:
      <input type="number" id="bs-close-pos" value="0.65" step="0.05" min="0.5" max="1.0">
    </label>
    <button id="btn-run-bull-snort">🔍 Run Screen</button>
  </div>

  <div id="bs-results-count" style="margin:8px 0;"></div>

  <table id="bull-snort-table">
    <thead>
      <tr>
        <th>Symbol</th>
        <th>Close</th>
        <th>Change %</th>
        <th>Vol Ratio</th>
        <th>Close Position</th>
        <th>High</th>
        <th>Low</th>
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
  const volPeriod  = document.getElementById('bs-vol-period').value;
  const volSurge   = document.getElementById('bs-vol-surge').value;
  const closePos   = document.getElementById('bs-close-pos').value;

  const url  = `/api/bull-snort/screen?vol_avg_period=${volPeriod}&vol_surge_min=${volSurge}&close_position_min=${closePos}`;
  const res  = await fetch(url);
  const json = await res.json();

  document.getElementById('bs-results-count').textContent = `${json.count} Bull Snort signals found`;

  const tbody = document.getElementById('bull-snort-tbody');
  tbody.innerHTML = '';

  json.data.forEach(row => {
    const scoreColor = row.score >= 75 ? '#22c55e'
                     : row.score >= 50 ? '#f59e0b' : '#ef4444';
    const changeColor = row.pct_change >= 0 ? '#22c55e' : '#ef4444';

    tbody.innerHTML += `
      <tr>
        <td><strong>${row.symbol}</strong></td>
        <td>${row.close}</td>
        <td style="color:${changeColor}">${row.pct_change > 0 ? '+' : ''}${row.pct_change}%</td>
        <td>${row.vol_ratio}x</td>
        <td>${(row.close_position * 100).toFixed(1)}%</td>
        <td>${row.high}</td>
        <td>${row.low}</td>
        <td><strong style="color:${scoreColor}">${row.score}</strong></td>
      </tr>`;
  });
});
```

---

## Build Order & Test Cases

### Suggested Build Order
1. Write `bull_snort_service.py` — test standalone on 5 tickers
2. Add `bull_snort.py` endpoint — test with curl
3. Register blueprint in `app/__init__.py`
4. Add scheduler job in `scheduler.py`
5. Add UI tab + JS
6. Write tests

### Test Cases

```python
# tests/test_bull_snort.py

def test_no_signal_when_volume_low():
    # vol_ratio = 2.5x (below 3x threshold) → should return None
    ...

def test_no_signal_when_close_is_negative():
    # today_close < prev_close → should return None
    ...

def test_no_signal_when_close_in_lower_half():
    # close_position = 0.4 (below 0.65 threshold) → should return None
    ...

def test_signal_fires_when_all_three_pass():
    # vol=4x, positive close, close_position=0.85 → should return dict with score
    ...

def test_higher_volume_scores_higher():
    # 5x vol should score higher than 3x vol, all else equal
    ...

def test_closer_to_high_scores_higher():
    # close_position=0.95 should score higher than close_position=0.70
    ...

def test_screen_sorted_by_score_descending():
    # results[0].score >= results[1].score >= ...
    ...

def test_doji_candle_returns_none():
    # high == low (candle_range = 0) → should return None safely
    ...
```
