# Bull Snort Filter — Design & Implementation Guide

The **Bull Snort** is a two-layer signal:

- **Layer 1 — 200 DMA Context**: The 200 DMA slope was previously declining and is now flattening or curling upward. This filters the universe to stocks where the long-term trend is recovering.
- **Layer 2 — Bull Snort Candle Trigger**: On that same day, a single candle meets all three conditions simultaneously — confirming institutional buying at the exact moment the trend turns.

> The DMA layer finds the **setup**. The candle layer confirms the **trigger**.

---

## Full Signal Conditions (ALL must be true)

| # | Layer | Condition | Rule |
|---|---|---|---|
| 1 | DMA Context | 200 DMA was declining | Slope N days ago was negative |
| 2 | DMA Context | 200 DMA is now flattening/curling up | Current slope ≥ flattening threshold |
| 3 | Candle Trigger | Volume Surge | Volume ≥ 3× the 10/20/50-day avg |
| 4 | Candle Trigger | Positive Price Move | Close > previous day's close |
| 5 | Candle Trigger | Strong Close | Close in top 35% of day's candle range |

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

### Layer 1 — 200 DMA Slope Transition

The slope is measured as a normalised percentage per day so it works across all price ranges.

```
# Current slope (short lookback — is it flattening NOW?)
current_slope = (DMA_200[today] - DMA_200[5 days ago]) / 5
norm_current_slope = (current_slope / DMA_200[today]) * 100   # % per day

# Prior slope (longer lookback — was it declining BEFORE?)
prior_slope = (DMA_200[20 days ago] - DMA_200[40 days ago]) / 20
norm_prior_slope = (prior_slope / DMA_200[20 days ago]) * 100   # % per day

# Conditions
was_declining    = norm_prior_slope < -0.01    # was falling at least 0.01%/day
is_flattening    = norm_current_slope >= -0.005  # now flat or turning up

dma_context_pass = was_declining AND is_flattening
```

**Tunable thresholds:**
- `prior_slope_max = -0.01` — how steep the prior decline must have been
- `current_slope_min = -0.005` — how flat counts as "flattening" (use 0.0 for strict curl-up only)

### Layer 2 — Bull Snort Candle

```
# Condition 3: Volume Surge
avg_vol       = rolling mean of Volume over last N days (excl. today)
vol_ratio     = today_volume / avg_vol
is_vol_surge  = vol_ratio >= 3.0

# Condition 4: Positive Price Move
is_positive   = today_close > prev_close
pct_change    = (today_close - prev_close) / prev_close * 100

# Condition 5: Strong Close (top 35% of candle range)
candle_range    = today_high - today_low
close_position  = (today_close - today_low) / candle_range  # 0.0=bottom, 1.0=top
is_strong_close = close_position >= 0.65

bull_snort_candle = is_vol_surge AND is_positive AND is_strong_close
```

### Full Signal
```
bull_snort_signal = dma_context_pass AND bull_snort_candle
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
DEFAULT_VOL_AVG_PERIOD      = 20      # rolling avg period for volume: 10, 20, or 50
DEFAULT_VOL_SURGE_MIN        = 3.0    # 3x average volume minimum
DEFAULT_CLOSE_POSITION_MIN   = 0.65   # close must be in top 35% of candle range
DEFAULT_PRIOR_SLOPE_MAX      = -0.01  # prior 200 DMA slope must be this negative (% per day)
DEFAULT_CURRENT_SLOPE_MIN    = -0.005 # current 200 DMA slope must be >= this (flattening)
PRIOR_LOOKBACK_START         = 40     # days ago where prior slope measurement starts
PRIOR_LOOKBACK_END           = 20     # days ago where prior slope measurement ends
CURRENT_SLOPE_LOOKBACK       = 5      # days over which current slope is measured


def compute_bull_snort(
    symbol: str,
    vol_avg_period: int           = DEFAULT_VOL_AVG_PERIOD,
    vol_surge_min: float          = DEFAULT_VOL_SURGE_MIN,
    close_position_min: float     = DEFAULT_CLOSE_POSITION_MIN,
    prior_slope_max: float        = DEFAULT_PRIOR_SLOPE_MAX,
    current_slope_min: float      = DEFAULT_CURRENT_SLOPE_MIN,
) -> dict | None:
    """
    Evaluate Bull Snort signal for a single symbol.

    Two-layer check:
      Layer 1: 200 DMA slope was declining and is now flattening/curling up.
      Layer 2: Today's candle is a Bull Snort (3x vol + positive close + strong close).

    Returns result dict if all conditions pass, else None.
    """
    try:
        # ----------------------------------------------------------------
        # 1. Fetch data — need 220+ days for 200 DMA + prior slope window
        # ----------------------------------------------------------------
        df = fetch_historical_prices(symbol, period='1y')
        if df is None or len(df) < 220:
            logger.warning(f"{symbol}: insufficient data ({len(df) if df is not None else 0} rows)")
            return None

        df = df.sort_index()
        close  = df['Close']
        volume = df['Volume']

        # ----------------------------------------------------------------
        # 2. Compute 200 DMA
        # ----------------------------------------------------------------
        dma200 = close.rolling(200).mean()

        dma_today    = dma200.iloc[-1]
        dma_5ago     = dma200.iloc[-(CURRENT_SLOPE_LOOKBACK + 1)]
        dma_20ago    = dma200.iloc[-(PRIOR_LOOKBACK_END + 1)]
        dma_40ago    = dma200.iloc[-(PRIOR_LOOKBACK_START + 1)]

        if any(np.isnan(x) for x in [dma_today, dma_5ago, dma_20ago, dma_40ago]):
            return None

        # ----------------------------------------------------------------
        # 3. Layer 1a: Was the 200 DMA declining? (prior slope)
        # ----------------------------------------------------------------
        prior_raw_slope  = (dma_20ago - dma_40ago) / 20
        norm_prior_slope = (prior_raw_slope / dma_20ago) * 100   # % per day
        was_declining    = norm_prior_slope < prior_slope_max

        if not was_declining:
            return None

        # ----------------------------------------------------------------
        # 4. Layer 1b: Is the 200 DMA now flattening/curling up? (current slope)
        # ----------------------------------------------------------------
        current_raw_slope  = (dma_today - dma_5ago) / CURRENT_SLOPE_LOOKBACK
        norm_current_slope = (current_raw_slope / dma_today) * 100   # % per day
        is_flattening      = norm_current_slope >= current_slope_min

        if not is_flattening:
            return None

        # ----------------------------------------------------------------
        # 5. Layer 2a: Volume Surge (>= 3x rolling avg, excl. today)
        # ----------------------------------------------------------------
        avg_vol      = volume.iloc[-(vol_avg_period + 1):-1].mean()
        today_vol    = volume.iloc[-1]
        vol_ratio    = today_vol / avg_vol if avg_vol > 0 else 0
        is_vol_surge = vol_ratio >= vol_surge_min

        if not is_vol_surge:
            return None

        # ----------------------------------------------------------------
        # 6. Layer 2b: Positive Price Move
        # ----------------------------------------------------------------
        today_close = close.iloc[-1]
        prev_close  = close.iloc[-2]
        today_high  = df['High'].iloc[-1]
        today_low   = df['Low'].iloc[-1]
        today_open  = df['Open'].iloc[-1]

        is_positive = today_close > prev_close
        pct_change  = ((today_close - prev_close) / prev_close) * 100

        if not is_positive:
            return None

        # ----------------------------------------------------------------
        # 7. Layer 2c: Strong Close — top 35% of candle range
        # ----------------------------------------------------------------
        candle_range   = today_high - today_low
        if candle_range == 0:
            return None   # doji — skip
        close_position  = (today_close - today_low) / candle_range
        is_strong_close = close_position >= close_position_min

        if not is_strong_close:
            return None

        # ----------------------------------------------------------------
        # 8. All conditions passed — compute score
        # ----------------------------------------------------------------
        score = _compute_score(
            vol_ratio, vol_surge_min,
            pct_change,
            close_position,
            norm_current_slope,
            norm_prior_slope
        )

        return {
            'symbol'             : symbol,
            'date'               : str(df.index[-1].date()),
            # Candle data
            'open'               : round(today_open, 2),
            'high'               : round(today_high, 2),
            'low'                : round(today_low, 2),
            'close'              : round(today_close, 2),
            'prev_close'         : round(prev_close, 2),
            'pct_change'         : round(pct_change, 2),
            # Volume
            'volume'             : int(today_vol),
            'avg_volume'         : int(avg_vol),
            'vol_ratio'          : round(vol_ratio, 2),
            # Candle strength
            'candle_range'       : round(candle_range, 2),
            'close_position'     : round(close_position, 3),
            # 200 DMA context
            'dma200'             : round(dma_today, 2),
            'norm_prior_slope'   : round(norm_prior_slope, 4),   # was this negative?
            'norm_current_slope' : round(norm_current_slope, 4), # is this flattening?
            # Score
            'score'              : round(score, 1),
        }

    except Exception as e:
        logger.error(f"compute_bull_snort error for {symbol}: {e}")
        return None


def screen_bull_snort(
    symbols: list[str],
    vol_avg_period: int       = DEFAULT_VOL_AVG_PERIOD,
    vol_surge_min: float      = DEFAULT_VOL_SURGE_MIN,
    close_position_min: float = DEFAULT_CLOSE_POSITION_MIN,
    prior_slope_max: float    = DEFAULT_PRIOR_SLOPE_MAX,
    current_slope_min: float  = DEFAULT_CURRENT_SLOPE_MIN,
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
            prior_slope_max=prior_slope_max,
            current_slope_min=current_slope_min,
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
    norm_current_slope: float,
    norm_prior_slope: float,
) -> float:
    """
    Blend four component scores into a final 0–100 Bull Snort score.

    Weights:
      Volume surge       : 35%  — institutional buying confirmation
      Close position     : 30%  — conviction into close
      DMA slope recovery : 25%  — how cleanly the DMA is turning
      Price change %     : 10%  — magnitude of the move
    """
    # Volume score: 3x = 0pts baseline, 6x = 100pts
    vol_score   = min((vol_ratio - vol_surge_min) / vol_surge_min, 1.0) * 100
    vol_score   = max(vol_score, 0)

    # Close position score: 0.65 = 0pts, 1.0 = 100pts
    close_score = min((close_position - 0.65) / 0.35, 1.0) * 100
    close_score = max(close_score, 0)

    # DMA slope recovery score
    # prior was negative, current is >= -0.005. Score how much it recovered.
    slope_recovery = norm_current_slope - norm_prior_slope   # positive = recovered
    slope_score    = min(slope_recovery / 0.05, 1.0) * 100   # 0.05% recovery = full score
    slope_score    = max(slope_score, 0)

    # Price change score: 0% = 0pts, 3%+ = 100pts
    price_score = min(pct_change / 3.0, 1.0) * 100
    price_score = max(price_score, 0)

    return (
        vol_score   * 0.35 +
        close_score * 0.30 +
        slope_score * 0.25 +
        price_score * 0.10
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

    Query params (all optional, defaults shown):
      vol_avg_period      : int   — 10 / 20 / 50  (default: 20)
      vol_surge_min       : float — min vol ratio  (default: 3.0)
      close_position_min  : float — 0.0–1.0        (default: 0.65)
      prior_slope_max     : float — prior DMA slope threshold (default: -0.01)
      current_slope_min   : float — current DMA slope threshold (default: -0.005)
    """
    try:
        vol_avg_period     = int(request.args.get('vol_avg_period', 20))
        vol_surge_min      = float(request.args.get('vol_surge_min', 3.0))
        close_position_min = float(request.args.get('close_position_min', 0.65))
        prior_slope_max    = float(request.args.get('prior_slope_max', -0.01))
        current_slope_min  = float(request.args.get('current_slope_min', -0.005))

        symbols = get_nse_symbols()
        results = screen_bull_snort(
            symbols,
            vol_avg_period=vol_avg_period,
            vol_surge_min=vol_surge_min,
            close_position_min=close_position_min,
            prior_slope_max=prior_slope_max,
            current_slope_min=current_slope_min,
        )

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

# Runs daily at 4:05 PM IST (after NSE close)
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

All five conditions must pass before scoring. Score is 0–100.

| Component | Weight | Baseline (0 pts) | Max (100 pts) |
|---|---|---|---|
| **Volume surge** | 35% | 3x avg (minimum to qualify) | 6x avg |
| **Close position** | 30% | 0.65 (top 35%) | 1.0 (at the high) |
| **DMA slope recovery** | 25% | No recovery | 0.05%/day recovery |
| **Price change %** | 10% | 0% | 3%+ |

**Score bands:**
- 75–100 → 🟢 Strong Bull Snort — DMA turning + big institutional candle
- 50–74  → 🟡 Moderate — valid but lower conviction
- Below 50 → 🔴 Weak — barely qualifies, needs confirmation

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
        <th>Close Pos</th>
        <th>200 DMA</th>
        <th>Prior Slope</th>
        <th>Curr Slope</th>
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
  const volPeriod = document.getElementById('bs-vol-period').value;
  const volSurge  = document.getElementById('bs-vol-surge').value;
  const closePos  = document.getElementById('bs-close-pos').value;

  const url  = `/api/bull-snort/screen?vol_avg_period=${volPeriod}&vol_surge_min=${volSurge}&close_position_min=${closePos}`;
  const res  = await fetch(url);
  const json = await res.json();

  document.getElementById('bs-results-count').textContent = `${json.count} Bull Snort signals found`;

  const tbody = document.getElementById('bull-snort-tbody');
  tbody.innerHTML = '';

  json.data.forEach(row => {
    const scoreColor  = row.score >= 75 ? '#22c55e' : row.score >= 50 ? '#f59e0b' : '#ef4444';
    const changeColor = row.pct_change >= 0 ? '#22c55e' : '#ef4444';
    const slopeColor  = row.norm_current_slope >= 0 ? '#22c55e' : '#f59e0b';

    tbody.innerHTML += `
      <tr>
        <td><strong>${row.symbol}</strong></td>
        <td>₹${row.close}</td>
        <td style="color:${changeColor}">${row.pct_change > 0 ? '+' : ''}${row.pct_change}%</td>
        <td>${row.vol_ratio}x</td>
        <td>${(row.close_position * 100).toFixed(1)}%</td>
        <td>${row.dma200}</td>
        <td>${row.norm_prior_slope}%</td>
        <td style="color:${slopeColor}">${row.norm_current_slope}%</td>
        <td><strong style="color:${scoreColor}">${row.score}</strong></td>
      </tr>`;
  });
});
```

---

## Build Order & Test Cases

### Suggested Build Order
1. Write `bull_snort_service.py` — test standalone on 5–10 NSE tickers
2. Add `bull_snort.py` endpoint — test via curl or browser
3. Register blueprint in `app/__init__.py`
4. Add scheduler job in `scheduler.py`
5. Add UI tab + JS
6. Backtest: check past dates where signal fired vs next-day/week returns

### Test Cases

```python
# tests/test_bull_snort.py

def test_no_signal_when_dma_not_previously_declining():
    # prior slope is positive → Layer 1a fails → None
    ...

def test_no_signal_when_dma_still_declining():
    # current slope still very negative → Layer 1b fails → None
    ...

def test_no_signal_when_volume_below_3x():
    # vol_ratio = 2.5 → Layer 2a fails → None
    ...

def test_no_signal_when_close_negative():
    # today_close < prev_close → Layer 2b fails → None
    ...

def test_no_signal_when_close_in_lower_half():
    # close_position = 0.4 → Layer 2c fails → None
    ...

def test_signal_fires_when_all_five_pass():
    # All conditions met → returns dict with score > 0
    ...

def test_steeper_dma_recovery_scores_higher():
    # norm_current_slope=0.03 should score higher than 0.0
    ...

def test_higher_volume_scores_higher():
    # vol_ratio=5x vs 3x → former scores higher
    ...

def test_doji_candle_returns_none():
    # high == low → safe None return
    ...

def test_screen_sorted_by_score_descending():
    # results[0].score >= results[-1].score
    ...
```
