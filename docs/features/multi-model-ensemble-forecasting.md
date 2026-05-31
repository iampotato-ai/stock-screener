# Multi-Model Ensemble Forecasting — Implementation Plan

> **Feature Codename:** `EnsembleCast`
> **Target Branch:** `feature/workspace-ui`
> **Relates To:** Kronos AI Predictor (existing), AI Forecast Tab (existing)

---

## 1. Overview

Currently, MomentumScan's AI forecasting relies solely on the `Kronos-small` foundation model for price path prediction. While Kronos provides strong deep-learning-driven signal, a single-model architecture is vulnerable to regime blind spots — e.g., Kronos may underperform during mean-reverting sideways markets or sharp news-driven reversals.

**EnsembleCast** blends three complementary forecasting models into a single confidence-weighted consensus prediction path:

| Model | Type | Strength |
|---|---|---|
| `Kronos-small` | Transformer (deep learning) | Momentum & trend continuation |
| `Prophet` (Facebook) | Additive time-series | Seasonality, holidays, trend inflections |
| `ARIMA/SARIMA` | Classical statistical | Mean reversion, short-term oscillations |

The ensemble output replaces (or augments) the existing Kronos single-path display in both the **Trade Drawer chart** and the **AI Forecast Tab**.

---

## 2. Goals

- Increase directional accuracy of price forecasts by 10–20% vs. single-model baseline
- Surface model disagreement as a **Divergence Warning** badge (high disagreement = lower conviction trade)
- Keep latency acceptable: full ensemble for a single ticker must complete in **< 6 seconds** on CPU
- Maintain full backward compatibility with existing Kronos cache and batch sort (`/api/kronos_forecast`)

---

## 3. Architecture

### 3.1 Backend — New Ensemble Pipeline

```
app.py
 └── /api/ensemble_forecast  (NEW endpoint)
      ├── kronos_predict(ticker, horizon)      ← existing function, reused
      ├── prophet_predict(ticker, horizon)     ← NEW
      ├── arima_predict(ticker, horizon)       ← NEW
      └── ensemble_blend(k, p, a, weights)    ← NEW aggregation layer
```

All three model runners execute **in parallel** using `concurrent.futures.ThreadPoolExecutor` (max 3 workers per ticker), mirroring the existing batch-sort threading pattern.

### 3.2 Blending Strategy — Confidence-Weighted Average

Each model produces a daily predicted close array `[d1, d2, ..., dN]`.

**Step 1 — Individual model weights (default):**

```
w_kronos  = 0.50   # deep learning, strongest on trend
w_prophet = 0.30   # seasonality-aware
w_arima   = 0.20   # short-term mean reversion
```

Weights are **dynamic** — they auto-adjust based on each model's recent backtested MAPE on the same ticker over the last 20 trading days:

```python
def compute_dynamic_weights(mape_k, mape_p, mape_a):
    scores = [1/mape_k, 1/mape_p, 1/mape_a]
    total = sum(scores)
    return [s / total for s in scores]
```

**Step 2 — Ensemble path:**

```
ensemble[d] = w_k * kronos[d] + w_p * prophet[d] + w_a * arima[d]
```

**Step 3 — Divergence Score:**

```
divergence = std([kronos[d], prophet[d], arima[d]]) / ensemble[d]  (normalized)
```

A divergence > 0.03 (3%) on any forecast day triggers a **⚠️ Low Conviction** badge in the UI.

### 3.3 Frontend — UI Changes

#### Trade Drawer Chart (existing Kronos chart)
- Replace single purple dashed path → render **three faint model paths** (purple = Kronos, orange = Prophet, teal = ARIMA) plus a **thick white/gold ensemble path**
- Add a small legend toggle: `[ ] Show Individual Models` (collapsed by default)
- Divergence badge rendered below the chart: `🟢 High Conviction` / `🟡 Moderate` / `🔴 Low Conviction`

#### AI Forecast Tab
- Add a new **"Ensemble" sub-tab** alongside existing `3D / 5D / 10D` selectors
- Render a model contribution bar: shows the weight % each model contributed to the ensemble for that ticker
- Add a **Model Agreement Matrix** — a small 3×3 heatmap showing pairwise directional agreement between models (up/down alignment)

---

## 4. New Dependencies

```bash
pip install prophet statsmodels
```

| Package | Purpose | Size Impact |
|---|---|---|
| `prophet` | Facebook Prophet model | ~50MB |
| `statsmodels` | ARIMA/SARIMA | ~20MB |

> **Note:** Both are CPU-only and do not require CUDA. Prophet depends on `pystan` — ensure `pystan >= 3.0` is installed.

---

## 5. New API Endpoint

### `POST /api/ensemble_forecast`

**Request Body:**
```json
{
  "ticker": "RELIANCE.NS",
  "horizon": 10,
  "use_dynamic_weights": true
}
```

**Response:**
```json
{
  "ticker": "RELIANCE.NS",
  "horizon": 10,
  "ensemble_path": [2450.2, 2461.5, 2478.3, "..."],
  "model_paths": {
    "kronos":  [2455.1, 2468.0, 2481.2, "..."],
    "prophet": [2447.8, 2455.3, 2472.1, "..."],
    "arima":   [2448.0, 2461.0, 2479.5, "..."]
  },
  "weights": {
    "kronos": 0.52,
    "prophet": 0.29,
    "arima": 0.19
  },
  "divergence_score": 0.018,
  "conviction": "HIGH",
  "cached": false,
  "latency_ms": 3820
}
```

**Error Handling:**
- If any single model fails (e.g., insufficient ARIMA data for illiquid stocks), the endpoint degrades gracefully — returns a 2-model ensemble and sets `"degraded": true` in the response
- Minimum 60 days of price history required; return `400` with `"error": "insufficient_history"` if not met

---

## 6. Caching Strategy

Ensemble forecasts are cached in the existing `kronos_forecasts` SQLite table with a new `model_type` column:

```sql
ALTER TABLE kronos_forecasts ADD COLUMN model_type TEXT DEFAULT 'kronos';
```

| `model_type` value | Description |
|---|---|
| `'kronos'` | Legacy single-model cache (backward compatible) |
| `'ensemble'` | New EnsembleCast result |

Cache TTL: **4 hours** (same as existing Kronos cache policy).

---

## 7. Backtester Integration

The existing **On-the-Fly Dynamic Backtester** (in the AI Forecast Tab) needs a new ensemble evaluation mode:

- Add `[ Kronos Only ] [ Ensemble ]` toggle above the backtester metrics panel
- When `Ensemble` is selected, re-run backtest slicing against all 3 model paths and the blended ensemble path
- Report per-model MAE/MAPE alongside ensemble MAE/MAPE in a comparison table:

```
┌──────────────┬────────┬────────┬──────────────┐
│ Model        │  MAE   │  MAPE  │  Dir. Acc %  │
├──────────────┼────────┼────────┼──────────────┤
│ Kronos       │ 18.4   │ 0.82%  │   62.1%      │
│ Prophet      │ 22.1   │ 1.01%  │   58.3%      │
│ ARIMA        │ 25.6   │ 1.18%  │   55.7%      │
│ **Ensemble** │ **14.2**│**0.63%**│ **67.8%**  │
└──────────────┴────────┴────────┴──────────────┘
```

---

## 8. Implementation Phases

### Phase 1 — Backend Core (Est. 2–3 days)
- [ ] Implement `prophet_predict(ticker, horizon)` function
- [ ] Implement `arima_predict(ticker, horizon)` function
- [ ] Implement `ensemble_blend()` with static weights
- [ ] Wire up `/api/ensemble_forecast` endpoint
- [ ] Add `model_type` column migration to SQLite schema
- [ ] Unit test each model runner independently with NIFTY 50 stocks

### Phase 2 — Dynamic Weights & Divergence (Est. 1–2 days)
- [ ] Implement `compute_dynamic_weights()` using rolling 20-day MAPE
- [ ] Implement `divergence_score` computation
- [ ] Map divergence score → conviction label logic
- [ ] Add graceful degradation for 2-model fallback

### Phase 3 — Frontend Integration (Est. 2 days)
- [ ] Update Trade Drawer chart renderer to display 3 model paths + ensemble path
- [ ] Add `Show Individual Models` toggle (JS)
- [ ] Add Conviction badge component (reuse existing badge CSS)
- [ ] Add `Ensemble` sub-tab to AI Forecast Tab
- [ ] Render Model Contribution Bar and Model Agreement Matrix

### Phase 4 — Backtester & Polish (Est. 1 day)
- [ ] Add Kronos/Ensemble toggle to backtester panel
- [ ] Render per-model vs. ensemble metrics comparison table
- [ ] Performance profiling: ensure < 6s latency on CPU for full ensemble
- [ ] Update Kronos Batch Sort (`/api/kronos_batch_sort`) to optionally use ensemble scores

---

## 9. File Change Map

| File | Change Type | Description |
|---|---|---|
| `app.py` | Modify | Add `prophet_predict()`, `arima_predict()`, `ensemble_blend()`, `/api/ensemble_forecast` route |
| `app.py` | Modify | SQLite schema migration — add `model_type` column |
| `static/js/main.js` (or equivalent) | Modify | Ensemble chart rendering, conviction badge, model toggle |
| `templates/index.html` | Modify | Add Ensemble sub-tab markup, Model Agreement Matrix container |
| `requirements.txt` (if present) | Modify | Add `prophet`, `statsmodels` |

---

## 10. Risk & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Prophet install issues (`pystan` build failures on Windows) | Medium | Document workaround: `pip install prophet --no-build-isolation`; provide pre-built wheel link |
| ARIMA insufficient data for small-cap / illiquid stocks | High | Graceful 2-model degradation (Phase 2) |
| Ensemble latency > 6s on slow machines | Medium | Cap Prophet `changepoint_prior_scale` for speed; add timeout guard per model |
| Cache collision between old Kronos entries and ensemble | Low | `model_type` column disambiguates; old cache entries untouched |
| Dynamic weights fluctuating too aggressively on volatile stocks | Medium | Smooth weights with EMA over last 3 recompute cycles |

---

## 11. Success Metrics

- Ensemble directional accuracy **≥ 65%** on NIFTY 500 backtest (vs. ~62% Kronos-only baseline)
- Full ensemble latency **< 6 seconds** on CPU (P95)
- Conviction badge accuracy: `HIGH` conviction trades should outperform `LOW` conviction trades by **≥ 1.5x** over a 30-day paper trading validation window
- Zero regressions in existing Kronos single-model flow

---

*Last Updated: May 2026 | Author: MomentumScan Dev*

---

## 12. Phase 1 — Backend Implementation Code

> Drop the following code blocks into `app.py`. Each section is self-contained and integrates with your existing Flask + yfinance + SQLite architecture.

### 12.1 New Imports

Add these at the top of `app.py` alongside existing imports:

```python
import numpy as np
import pandas as pd
from prophet import Prophet
from statsmodels.tsa.arima.model import ARIMA
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import warnings
warnings.filterwarnings('ignore', module='prophet')      # suppress Prophet verbose output
warnings.filterwarnings('ignore', module='statsmodels')  # suppress ARIMA convergence warnings
```

---

### 12.2 SQLite Schema Migration

Find your existing DB initialisation block in `app.py` (where `CREATE TABLE kronos_forecasts` lives) and add the migration guard right after it:

```python
def migrate_ensemble_schema(conn):
    """
    Adds model_type column to kronos_forecasts if it doesn't already exist.
    Safe to call on every startup — no-ops if column is present.
    Backfills existing 'kronos' rows so the ensemble cache filter never misses them.
    """
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE kronos_forecasts ADD COLUMN model_type TEXT DEFAULT 'kronos'")
        conn.commit()
        print("[EnsembleCast] Schema migration: added model_type column.")
    except Exception:
        pass  # column already exists
    # Backfill any rows that were inserted before the column existed
    cursor.execute("UPDATE kronos_forecasts SET model_type = 'kronos' WHERE model_type IS NULL")
    conn.commit()

# Call once during app startup, after your existing init_db() call:
# migrate_ensemble_schema(get_db_connection())
```

---

### 12.3 Price History Helper

A shared utility used by both Prophet and ARIMA runners to fetch and validate price history:

```python
def _fetch_price_history(ticker: str, min_days: int = 60) -> pd.DataFrame:
    """
    Fetches daily Close price history for `ticker` using native fetch_historical_prices.
    Returns a DataFrame with columns ['ds', 'y'] (Prophet-compatible).
    Raises ValueError if fewer than min_days of history are available.
    """
    clean_ticker = ticker
    if clean_ticker.startswith("NSE:"):
        clean_ticker = clean_ticker[4:]

    history = fetch_historical_prices(clean_ticker, range_str="2y")
    if not history or len(history) < min_days:
        raise ValueError(
            f"insufficient_history: {clean_ticker} has only {len(history)} days (need {min_days})"
        )

    df = pd.DataFrame([{
        'ds': pd.to_datetime(d['date']),
        'y': float(d['close'])
    } for d in history])
    df['ds'] = df['ds'].dt.tz_localize(None)  # strip tz for Prophet
    return df
```

---

### 12.4 Prophet Model Runner

```python
def prophet_predict(ticker: str, horizon: int = 10) -> list[float]:
    df = _fetch_price_history(ticker)

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        interval_width=0.80
    )
    model.fit(df[['ds', 'y']])

    # Use NSE-aware future dates (skips weekends + NSE holidays)
    last_date_str = df['ds'].iloc[-1].strftime('%Y-%m-%d')
    future_dates = generate_next_trading_days(last_date_str, horizon)
    future_df = pd.DataFrame({'ds': pd.to_datetime(future_dates).dt.tz_localize(None)})

    forecast = model.predict(future_df)
    return forecast['yhat'].tolist()
```

---

### 12.5 ARIMA Model Runner

```python
def arima_predict(ticker: str, horizon: int = 10) -> list[float]:
    df = _fetch_price_history(ticker)
    closes = df['y'].values

    try:
        model = ARIMA(closes, order=(5, 1, 0))
        result = model.fit()
    except Exception:
        model = ARIMA(closes, order=(2, 1, 0))
        result = model.fit()

    forecast = result.forecast(steps=horizon)
    return forecast.tolist()
```

---

### 12.6 Ensemble Blend Function

```python
def ensemble_blend(
    kronos_path: list[float],
    prophet_path: list[float],
    arima_path: list[float],
    weights: dict = None
) -> dict:
    if weights is None:
        weights = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}

    w_k = weights.get('kronos', 0.0)
    w_p = weights.get('prophet', 0.0)
    w_a = weights.get('arima', 0.0)

    # Align to shortest available path
    lengths = [len(p) for p in [kronos_path, prophet_path, arima_path] if len(p) > 0]
    if not lengths:
        return {'ensemble_path': [], 'divergence_score': 0.0, 'conviction': 'LOW'}
    horizon = min(lengths)

    k = np.array(kronos_path[:horizon]) if len(kronos_path) > 0 else np.zeros(horizon)
    p = np.array(prophet_path[:horizon]) if len(prophet_path) > 0 else np.zeros(horizon)
    a = np.array(arima_path[:horizon]) if len(arima_path) > 0 else np.zeros(horizon)

    # Only blend paths that actually exist (avoids zero-fill weight bias)
    ensemble = np.zeros(horizon)
    for path_arr, weight in [(k, w_k), (p, w_p), (a, w_a)]:
        if weight > 0 and path_arr.sum() != 0:
            ensemble += weight * path_arr

    # Divergence: normalised std across active paths, worst-case day
    active_paths = [arr for arr, path in [(k, kronos_path), (p, prophet_path), (a, arima_path)] if len(path) > 0]
    if len(active_paths) > 1:
        stacked = np.stack(active_paths, axis=0)
        daily_divergence = np.std(stacked, axis=0) / (ensemble + 1e-9)
        max_divergence = float(np.max(daily_divergence))
    else:
        max_divergence = 0.0

    if max_divergence < 0.015:
        conviction = 'HIGH'
    elif max_divergence < 0.03:
        conviction = 'MODERATE'
    else:
        conviction = 'LOW'

    return {
        'ensemble_path': ensemble.tolist(),
        'divergence_score': round(max_divergence, 5),
        'conviction': conviction
    }
```

---

### 12.7 Flask API Endpoint

```python
@app.route('/api/ensemble_forecast', methods=['POST'])
def api_ensemble_forecast():
    import time
    start_time = time.time()

    data = request.get_json(force=True)
    ticker = data.get('ticker', '').strip().upper()
    horizon = int(data.get('horizon', 10))
    use_dynamic_weights = data.get('use_dynamic_weights', False)

    if not ticker:
        return jsonify({'error': 'ticker_required'}), 400
    if horizon < 1 or horizon > 30:
        return jsonify({'error': 'horizon must be between 1 and 30'}), 400

    # Check cache
    try:
        conn = get_db_connection()
        cached = conn.execute(
            """SELECT forecast_json FROM kronos_forecasts
               WHERE ticker = ? AND model_type = 'ensemble'
               AND datetime(generated_at) > datetime('now', '-4 hours')
               ORDER BY generated_at DESC LIMIT 1""",
            (ticker,)
        ).fetchone()
        conn.close()
        if cached:
            import json
            result = json.loads(cached['forecast_json'])
            result['cached'] = True
            result['latency_ms'] = round((time.time() - start_time) * 1000)
            return jsonify(result)
    except Exception as e:
        print(f'[EnsembleCast] Cache lookup error: {e}')

    # Run models in parallel
    results = {'kronos': None, 'prophet': None, 'arima': None}
    errors  = {'kronos': None, 'prophet': None, 'arima': None}

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            'kronos':  executor.submit(kronos_predict, ticker, horizon),
            'prophet': executor.submit(prophet_predict, ticker, horizon),
            'arima':   executor.submit(arima_predict, ticker, horizon),
        }
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=12)
            except Exception as e:
                errors[name] = str(e)
                print(f'[EnsembleCast] {name} failed: {e}')

    active_models = {k: v for k, v in results.items() if v is not None}
    degraded = len(active_models) < 3

    if len(active_models) < 2:
        return jsonify({'error': 'ensemble_failed', 'details': errors}), 500

    default_weights = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}
    if degraded:
        total_w = sum(default_weights[m] for m in active_models)
        weights = {m: default_weights[m] / total_w for m in active_models}
    else:
        weights = default_weights

    blend_result = ensemble_blend(
        kronos_path=results['kronos'] or [],
        prophet_path=results['prophet'] or [],
        arima_path=results['arima'] or [],
        weights=weights
    )

    last_close = 0.0
    try:
        df_hist = _fetch_price_history(ticker, min_days=10)
        last_close = float(df_hist['y'].iloc[-1])
    except Exception:
        pass

    response = {
        'ticker': ticker,
        'horizon': horizon,
        'ensemble_path': blend_result['ensemble_path'],
        'model_paths': {k: v for k, v in results.items() if v is not None},
        'weights': weights,
        'divergence_score': blend_result['divergence_score'],
        'conviction': blend_result['conviction'],
        'degraded': degraded,
        'model_errors': {k: v for k, v in errors.items() if v is not None},
        'cached': False,
        'last_close': last_close,
        'latency_ms': round((time.time() - start_time) * 1000)
    }

    try:
        import json
        conn = get_db_connection()
        conn.execute(
            """INSERT INTO kronos_forecasts (ticker, forecast_json, generated_at, pred_len, last_close, model_type)
               VALUES (?, ?, datetime('now'), ?, ?, 'ensemble')""",
            (ticker, json.dumps(response), horizon, last_close)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'[EnsembleCast] Cache write error: {e}')

    return jsonify(response)
```

---

### 12.8 Phase 1 Unit Test Checklist

```python
# quick_test_phase1.py
from app import prophet_predict, arima_predict, ensemble_blend

TEST_TICKERS = ['RELIANCE.NS', 'HDFCBANK.NS', 'INFY.NS', 'TATAMOTORS.NS', 'WIPRO.NS']

for ticker in TEST_TICKERS:
    print(f'\n=== {ticker} ===')
    try:
        k = [2400 + i * 5 for i in range(10)]  # mock Kronos path
        p = prophet_predict(ticker, horizon=10)
        a = arima_predict(ticker, horizon=10)
        blend = ensemble_blend(k, p, a)
        print(f'  Prophet  : {[round(x,1) for x in p]}')
        print(f'  ARIMA    : {[round(x,1) for x in a]}')
        print(f'  Ensemble : {[round(x,1) for x in blend["ensemble_path"]]}')
        print(f'  Divergence: {blend["divergence_score"]} | Conviction: {blend["conviction"]}')
    except Exception as e:
        print(f'  ERROR: {e}')
```

**Expected outcomes:**
- All 5 tickers return a 10-element list for each model
- `divergence_score` is between 0.0 and 0.10 for liquid large-caps
- `conviction` is `HIGH` or `MODERATE` for NIFTY 50 stocks in normal conditions
- Total runtime < 30 seconds on CPU

> **Next:** Once Phase 1 tests pass, proceed to Phase 2 below.

---

## 13. Phase 2 — Dynamic Weights & Divergence

> **Goal:** Replace the static `{kronos: 0.50, prophet: 0.30, arima: 0.20}` weights with weights computed from each model's rolling 20-day MAPE on the same ticker. Add EMA smoothing so weights don't flip violently on volatile names.

### 13.1 Rolling MAPE Backtester (Per-Model)

Add this helper to `app.py`. It fetches the last 30 days of actual closes, slices a context window just before that window, runs each model on the context, and scores MAPE against the actuals.

```python
def _compute_rolling_mape(ticker: str, model_fn, horizon: int = 10) -> float:
    """
    Runs `model_fn(ticker, horizon)` on a held-out window ending 20 trading
    days ago and returns MAPE (%) against actual closes.

    If the backtest run fails for any reason, returns a neutral fallback
    MAPE of 5.0 so the dynamic weight system degrades gracefully.
    """
    FALLBACK_MAPE = 5.0
    try:
        clean_ticker = ticker.replace('NSE:', '')
        history = fetch_historical_prices(clean_ticker, range_str='2y')
        if not history or len(history) < horizon + 60:
            return FALLBACK_MAPE

        # Held-out window: last `horizon` trading days
        # Context: the 120 trading days immediately before the held-out window
        context  = history[-(horizon + 120):-horizon]
        actuals  = [float(d['close']) for d in history[-horizon:]]

        if len(context) < 60:
            return FALLBACK_MAPE

        # Temporarily swap fetch_historical_prices cache so model_fn sees
        # only the context slice — build a lightweight shim DataFrame
        import pandas as pd
        df_ctx = pd.DataFrame([{
            'ds': pd.to_datetime(d['date']),
            'y':  float(d['close'])
        } for d in context])
        df_ctx['ds'] = df_ctx['ds'].dt.tz_localize(None)

        # Inject context into the module-level LRU cache under a sentinel key
        # so model_fn can call _fetch_price_history without a real HTTP fetch
        _BACKTEST_CTX_CACHE[clean_ticker] = df_ctx
        preds = model_fn(ticker, horizon)
        del _BACKTEST_CTX_CACHE[clean_ticker]

        if not preds or len(preds) < horizon:
            return FALLBACK_MAPE

        mape = float(np.mean([
            abs(p - a) / (abs(a) + 1e-9) * 100
            for p, a in zip(preds[:horizon], actuals[:horizon])
        ]))
        return max(0.1, mape)   # never return 0 — would cause division by zero in weight calc
    except Exception as e:
        print(f'[DynWeights] Rolling MAPE failed for {ticker}: {e}')
        return FALLBACK_MAPE


# Module-level context cache used by the backtest shim above
_BACKTEST_CTX_CACHE: dict = {}
```

Update `_fetch_price_history()` to honour the backtest shim:

```python
def _fetch_price_history(ticker: str, min_days: int = 60) -> pd.DataFrame:
    clean_ticker = ticker.replace('NSE:', '')

    # Backtest shim: return injected context DataFrame if present
    if clean_ticker in _BACKTEST_CTX_CACHE:
        df = _BACKTEST_CTX_CACHE[clean_ticker].copy()
        if len(df) >= min_days:
            return df

    history = fetch_historical_prices(clean_ticker, range_str='2y')
    if not history or len(history) < min_days:
        raise ValueError(
            f'insufficient_history: {clean_ticker} has only {len(history or [])} days (need {min_days})'
        )
    df = pd.DataFrame([{
        'ds': pd.to_datetime(d['date']),
        'y':  float(d['close'])
    } for d in history])
    df['ds'] = df['ds'].dt.tz_localize(None)
    return df
```

---

### 13.2 Dynamic Weight Computation with EMA Smoothing

```python
# Module-level EMA state: {ticker: {model: ema_weight}}
_weight_ema_state: dict = {}
_WEIGHT_EMA_ALPHA = 0.4   # higher = faster adaptation; 0.4 is a 4-period EMA

def compute_dynamic_weights(
    ticker: str,
    horizon: int = 10,
    use_cache: bool = True
) -> dict:
    """
    Computes per-model weights inversely proportional to each model's
    rolling MAPE on `ticker` over the last `horizon` trading days.

    EMA-smoothed across calls to prevent weight instability on volatile names.

    Returns: {'kronos': float, 'prophet': float, 'arima': float}  (sum == 1.0)
    """
    import time

    # --- Rolling MAPE per model (run in parallel for speed) ---
    mapes = {'kronos': 5.0, 'prophet': 5.0, 'arima': 5.0}

    def _score_kronos():
        return _compute_rolling_mape(ticker, kronos_predict, horizon)

    def _score_prophet():
        return _compute_rolling_mape(ticker, prophet_predict, horizon)

    def _score_arima():
        return _compute_rolling_mape(ticker, arima_predict, horizon)

    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {
            'kronos':  ex.submit(_score_kronos),
            'prophet': ex.submit(_score_prophet),
            'arima':   ex.submit(_score_arima),
        }
        for name, fut in futs.items():
            try:
                mapes[name] = fut.result(timeout=20)
            except Exception as e:
                print(f'[DynWeights] MAPE scoring failed for {name}: {e}')

    # --- Inverse-MAPE scores → raw weights ---
    inv_scores = {m: 1.0 / (mapes[m] + 1e-6) for m in mapes}
    total = sum(inv_scores.values())
    raw_weights = {m: inv_scores[m] / total for m in inv_scores}

    # --- EMA smoothing ---
    prev_ema = _weight_ema_state.get(ticker, raw_weights)
    smoothed = {
        m: _WEIGHT_EMA_ALPHA * raw_weights[m] + (1 - _WEIGHT_EMA_ALPHA) * prev_ema.get(m, raw_weights[m])
        for m in raw_weights
    }
    # Re-normalise after EMA (floating-point drift)
    s_total = sum(smoothed.values())
    smoothed = {m: round(v / s_total, 4) for m, v in smoothed.items()}

    _weight_ema_state[ticker] = smoothed

    print(
        f'[DynWeights] {ticker} | MAPE k={mapes["kronos"]:.2f}% '
        f'p={mapes["prophet"]:.2f}% a={mapes["arima"]:.2f}% '
        f'→ weights {smoothed}'
    )
    return smoothed
```

---

### 13.3 Wire Dynamic Weights into the Endpoint

In `/api/ensemble_forecast`, replace the static weight block with:

```python
# --- Build weights ---
if use_dynamic_weights and len(active_models) == 3:
    try:
        weights = compute_dynamic_weights(ticker, horizon)
        print(f'[EnsembleCast] {ticker} using dynamic weights: {weights}')
    except Exception as e:
        print(f'[EnsembleCast] Dynamic weight computation failed ({e}), falling back to static')
        weights = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}
else:
    # Degraded (1 model failed) or static mode requested
    default_weights = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}
    if degraded:
        total_w = sum(default_weights[m] for m in active_models)
        weights = {m: default_weights[m] / total_w for m in active_models}
    else:
        weights = default_weights
```

Also add `weights_source` to the response dict so the frontend can display whether dynamic or static weights were used:

```python
response['weights_source'] = 'dynamic' if (use_dynamic_weights and len(active_models) == 3) else 'static'
```

---

### 13.4 Divergence Detail Breakdown

Extend `ensemble_blend()` to also return a per-day divergence array (for the frontend sparkline) and pairwise model agreement:

```python
def ensemble_blend(
    kronos_path: list[float],
    prophet_path: list[float],
    arima_path: list[float],
    weights: dict = None
) -> dict:
    """
    Returns:
      ensemble_path       — weighted blended closes
      divergence_score    — worst-day normalised std (scalar)
      divergence_daily    — per-day normalised std list (for UI sparkline)
      conviction          — 'HIGH' / 'MODERATE' / 'LOW'
      agreement_matrix    — 3x3 pairwise directional agreement (up/down)
    """
    if weights is None:
        weights = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}

    w_k = weights.get('kronos', 0.0)
    w_p = weights.get('prophet', 0.0)
    w_a = weights.get('arima', 0.0)

    named_paths = [
        ('kronos',  kronos_path,  w_k),
        ('prophet', prophet_path, w_p),
        ('arima',   arima_path,   w_a),
    ]
    active = [(name, np.array(path), w) for name, path, w in named_paths
              if len(path) > 0 and w > 0]

    if not active:
        return {
            'ensemble_path': [], 'divergence_score': 0.0,
            'divergence_daily': [], 'conviction': 'LOW', 'agreement_matrix': {}
        }

    horizon = min(len(p) for _, p, _ in active)
    ensemble = np.zeros(horizon)
    for _, path_arr, w in active:
        ensemble += w * path_arr[:horizon]

    # Per-day divergence
    if len(active) > 1:
        stacked = np.stack([p[:horizon] for _, p, _ in active], axis=0)
        daily_div = (np.std(stacked, axis=0) / (ensemble + 1e-9)).tolist()
        max_divergence = float(max(daily_div))
    else:
        daily_div = [0.0] * horizon
        max_divergence = 0.0

    # Conviction label
    if max_divergence < 0.015:
        conviction = 'HIGH'
    elif max_divergence < 0.03:
        conviction = 'MODERATE'
    else:
        conviction = 'LOW'

    # Pairwise directional agreement matrix
    # direction[i] = +1 if path[i] > path[i-1], else -1
    def _dirs(arr):
        return [1 if arr[i] > arr[i - 1] else -1 for i in range(1, len(arr))]

    agreement_matrix = {}
    for i, (n1, p1, _) in enumerate(active):
        for j, (n2, p2, _) in enumerate(active):
            if i >= j:
                continue
            d1, d2 = _dirs(p1[:horizon]), _dirs(p2[:horizon])
            match = sum(1 for a, b in zip(d1, d2) if a == b)
            pct = round(match / len(d1) * 100, 1) if d1 else 0.0
            agreement_matrix[f'{n1}_vs_{n2}'] = pct

    return {
        'ensemble_path':    ensemble.tolist(),
        'divergence_score': round(max_divergence, 5),
        'divergence_daily': [round(v, 5) for v in daily_div],
        'conviction':       conviction,
        'agreement_matrix': agreement_matrix
    }
```

Add `agreement_matrix` and `divergence_daily` to the endpoint response dict:

```python
response['agreement_matrix'] = blend_result.get('agreement_matrix', {})
response['divergence_daily'] = blend_result.get('divergence_daily', [])
```

---

### 13.5 Phase 2 Updated API Response Shape

```json
{
  "ticker": "RELIANCE",
  "horizon": 10,
  "ensemble_path": [2450.2, 2461.5, "..."],
  "model_paths": { "kronos": [...], "prophet": [...], "arima": [...] },
  "weights": { "kronos": 0.52, "prophet": 0.31, "arima": 0.17 },
  "weights_source": "dynamic",
  "divergence_score": 0.018,
  "divergence_daily": [0.011, 0.014, 0.018, "..."],
  "agreement_matrix": {
    "kronos_vs_prophet": 80.0,
    "kronos_vs_arima": 70.0,
    "prophet_vs_arima": 75.0
  },
  "conviction": "HIGH",
  "degraded": false,
  "weights_source": "dynamic",
  "cached": false,
  "last_close": 2441.75,
  "latency_ms": 4120
}
```

---

### 13.6 Phase 2 Test Checklist

```python
# quick_test_phase2.py
import requests

BASE = 'http://localhost:5000'
TICKERS = ['RELIANCE', 'HDFCBANK', 'INFY', 'TATAMOTORS']

for ticker in TICKERS:
    res = requests.post(f'{BASE}/api/ensemble_forecast', json={
        'ticker': ticker,
        'horizon': 10,
        'use_dynamic_weights': True
    })
    d = res.json()
    print(f'{ticker}: weights={d["weights"]} source={d["weights_source"]} '
          f'conviction={d["conviction"]} divergence={d["divergence_score"]} '
          f'agreement={d["agreement_matrix"]}')
```

**Expected outcomes:**
- `weights_source` is `'dynamic'` for all tickers
- Weights sum to ~1.0 (within floating-point tolerance)
- `agreement_matrix` has all three pairwise keys
- `divergence_daily` length equals `horizon`
- Total latency < 12 seconds on CPU (dynamic weights add one extra parallel MAPE run)

---

## 14. Phase 3 — Frontend Integration

> **Goal:** Wire the `/api/ensemble_forecast` response into the existing Trade Drawer chart and AI Forecast Tab. All changes are in `static/js/main.js` (or your equivalent JS file) and `templates/index.html`.

### 14.1 HTML Markup Changes (`templates/index.html`)

Locate the AI Forecast Tab container and add the Ensemble sub-tab alongside the existing 3D/5D/10D buttons:

```html
<!-- Add inside the AI Forecast Tab header bar -->
<div id="forecastSubTabs" class="forecast-subtabs">
  <button class="subtab-btn active" data-horizon="3">3D</button>
  <button class="subtab-btn" data-horizon="5">5D</button>
  <button class="subtab-btn" data-horizon="10">10D</button>
  <!-- NEW -->
  <button class="subtab-btn ensemble-btn" data-horizon="10" data-mode="ensemble">
    ⚡ Ensemble
  </button>
</div>

<!-- NEW: Ensemble-only panels (hidden until Ensemble sub-tab is active) -->
<div id="ensemblePanel" class="ensemble-panel" style="display:none;">

  <!-- Conviction Badge -->
  <div id="convictionBadge" class="conviction-badge conviction-loading">
    <span id="convictionIcon">●</span>
    <span id="convictionLabel">Calculating…</span>
  </div>

  <!-- Model Weights Contribution Bar -->
  <div class="model-weights-bar" id="modelWeightsBar">
    <div class="weight-segment kronos-segment" id="kronosWeightSeg" style="width:50%">
      Kronos <span class="weight-pct" id="kronosWeightPct">50%</span>
    </div>
    <div class="weight-segment prophet-segment" id="prophetWeightSeg" style="width:30%">
      Prophet <span class="weight-pct" id="prophetWeightPct">30%</span>
    </div>
    <div class="weight-segment arima-segment" id="arimaWeightSeg" style="width:20%">
      ARIMA <span class="weight-pct" id="arimaWeightPct">20%</span>
    </div>
  </div>

  <!-- Model Agreement Matrix -->
  <div class="agreement-matrix" id="agreementMatrix">
    <table>
      <thead>
        <tr><th></th><th>Kronos</th><th>Prophet</th><th>ARIMA</th></tr>
      </thead>
      <tbody id="agreementMatrixBody"></tbody>
    </table>
  </div>

  <!-- Individual Models Toggle -->
  <label class="model-paths-toggle">
    <input type="checkbox" id="showIndividualModels" />
    Show individual model paths
  </label>

</div>
```

Add CSS classes to your existing stylesheet (or inline in `<style>`):

```css
/* Conviction Badge */
.conviction-badge { display:flex; align-items:center; gap:6px; padding:4px 10px;
                    border-radius:6px; font-size:0.85rem; font-weight:600; width:fit-content; }
.conviction-badge.HIGH    { background:#0d2b1a; color:#22c55e; border:1px solid #22c55e; }
.conviction-badge.MODERATE{ background:#2b1f06; color:#f59e0b; border:1px solid #f59e0b; }
.conviction-badge.LOW     { background:#2b0e0e; color:#ef4444; border:1px solid #ef4444; }

/* Model Weights Bar */
.model-weights-bar { display:flex; height:24px; border-radius:4px; overflow:hidden;
                     margin:8px 0; font-size:0.75rem; }
.weight-segment   { display:flex; align-items:center; justify-content:center;
                    color:#fff; transition:width 0.5s ease; overflow:hidden; white-space:nowrap; }
.kronos-segment   { background:#7c3aed; }
.prophet-segment  { background:#ea580c; }
.arima-segment    { background:#0891b2; }

/* Agreement Matrix */
.agreement-matrix table { width:100%; border-collapse:collapse; font-size:0.78rem; }
.agreement-matrix th, .agreement-matrix td { padding:4px 8px; text-align:center;
                                              border:1px solid rgba(255,255,255,0.08); }
.agreement-cell-high   { color:#22c55e; font-weight:700; }
.agreement-cell-medium { color:#f59e0b; }
.agreement-cell-low    { color:#ef4444; }
```

---

### 14.2 JavaScript — Ensemble Chart Renderer

Add the following to `main.js` (after your existing Kronos chart rendering logic).

#### 14.2.1 Fetch ensemble data

```javascript
/**
 * Fetches ensemble forecast from the backend and renders the chart.
 * @param {string} ticker  — clean NSE ticker, e.g. 'RELIANCE'
 * @param {number} horizon — forecast horizon in trading days
 * @param {boolean} useDynamicWeights
 */
async function loadEnsembleForecast(ticker, horizon = 10, useDynamicWeights = false) {
  const panel = document.getElementById('ensemblePanel');
  panel.style.display = 'block';
  document.getElementById('convictionLabel').textContent = 'Calculating…';
  document.getElementById('convictionBadge').className = 'conviction-badge conviction-loading';

  try {
    const res = await fetch('/api/ensemble_forecast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, horizon, use_dynamic_weights: useDynamicWeights })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    renderEnsembleChart(data);
    renderConvictionBadge(data.conviction, data.divergence_score);
    renderModelWeightsBar(data.weights);
    renderAgreementMatrix(data.agreement_matrix);

  } catch (err) {
    document.getElementById('convictionLabel').textContent = 'Ensemble unavailable';
    console.error('[EnsembleCast]', err);
  }
}
```

#### 14.2.2 Chart rendering (LightweightCharts v4)

```javascript
/**
 * Renders the ensemble forecast chart using TradingView LightweightCharts.
 * Draws 3 faint model paths + 1 bold ensemble path on top of the existing
 * historical candlestick series.
 */
function renderEnsembleChart(data) {
  // Assumes `ensembleChart` is your existing LightweightCharts instance
  // and `ensembleSeries` objects are stored in a module-level map.

  const MODEL_COLORS = {
    kronos:  { color: 'rgba(124, 58, 237, 0.45)',  lineWidth: 1 },  // faint purple
    prophet: { color: 'rgba(234, 88,  12,  0.45)', lineWidth: 1 },  // faint orange
    arima:   { color: 'rgba(8,   145, 178, 0.45)', lineWidth: 1 },  // faint teal
  };
  const ENSEMBLE_STYLE = { color: '#fbbf24', lineWidth: 2.5 };      // gold bold path

  const showIndividual = document.getElementById('showIndividualModels')?.checked ?? false;

  // Generate future date labels aligned to the ensemble path
  const futureDates = generateFutureTradingDates(data.last_close_date, data.horizon);

  // Remove stale series
  ['kronosSeries', 'prophetSeries', 'arimaSeries', 'ensembleSeries'].forEach(key => {
    if (window[key]) {
      try { ensembleChart.removeSeries(window[key]); } catch (_) {}
    }
  });

  // Draw individual model paths (toggled by checkbox)
  if (showIndividual) {
    Object.entries(data.model_paths).forEach(([modelName, path]) => {
      const style = MODEL_COLORS[modelName] || { color: '#888', lineWidth: 1 };
      const series = ensembleChart.addLineSeries({
        color: style.color,
        lineWidth: style.lineWidth,
        lineStyle: 2,   // dashed
        priceLineVisible: false,
        lastValueVisible: false,
      });
      series.setData(
        path.map((close, i) => ({ time: futureDates[i], value: close }))
      );
      window[`${modelName}Series`] = series;
    });
  }

  // Draw bold ensemble path
  const ensembleSeries = ensembleChart.addLineSeries({
    color: ENSEMBLE_STYLE.color,
    lineWidth: ENSEMBLE_STYLE.lineWidth,
    priceLineVisible: false,
    title: 'Ensemble',
  });
  ensembleSeries.setData(
    data.ensemble_path.map((close, i) => ({ time: futureDates[i], value: close }))
  );
  window.ensembleSeries = ensembleSeries;
}

/**
 * Returns an array of YYYY-MM-DD strings for the next N NSE trading days.
 * Mirrors the backend `generate_next_trading_days()` logic.
 */
function generateFutureTradingDates(lastDate, n) {
  const NSE_HOLIDAYS_2026 = new Set([
    '2026-01-26','2026-03-03','2026-03-19','2026-04-02',
    '2026-04-03','2026-04-14','2026-05-01','2026-08-15',
    '2026-10-02','2026-10-20','2026-11-25','2026-12-25'
  ]);
  const dates = [];
  const cur = new Date(lastDate);
  while (dates.length < n) {
    cur.setDate(cur.getDate() + 1);
    const dow = cur.getDay();
    const iso = cur.toISOString().slice(0, 10);
    if (dow !== 0 && dow !== 6 && !NSE_HOLIDAYS_2026.has(iso)) {
      dates.push(iso);
    }
  }
  return dates;
}
```

#### 14.2.3 Conviction badge, weights bar, agreement matrix renderers

```javascript
function renderConvictionBadge(conviction, divergenceScore) {
  const badge  = document.getElementById('convictionBadge');
  const icon   = document.getElementById('convictionIcon');
  const label  = document.getElementById('convictionLabel');
  const ICONS  = { HIGH: '🟢', MODERATE: '🟡', LOW: '🔴' };
  const LABELS = {
    HIGH:     `High Conviction  (divergence: ${(divergenceScore * 100).toFixed(1)}%)`,
    MODERATE: `Moderate Conviction  (divergence: ${(divergenceScore * 100).toFixed(1)}%)`,
    LOW:      `Low Conviction ⚠️  (divergence: ${(divergenceScore * 100).toFixed(1)}%)`,
  };
  badge.className = `conviction-badge ${conviction}`;
  icon.textContent  = ICONS[conviction]  ?? '●';
  label.textContent = LABELS[conviction] ?? conviction;
}

function renderModelWeightsBar(weights) {
  const models = ['kronos', 'prophet', 'arima'];
  models.forEach(m => {
    const pct = Math.round((weights[m] ?? 0) * 100);
    document.getElementById(`${m}WeightSeg`).style.width  = `${pct}%`;
    document.getElementById(`${m}WeightPct`).textContent  = `${pct}%`;
  });
}

function renderAgreementMatrix(matrix) {
  // matrix = { kronos_vs_prophet: 80, kronos_vs_arima: 70, prophet_vs_arima: 75 }
  const MODELS = ['kronos', 'prophet', 'arima'];
  const tbody  = document.getElementById('agreementMatrixBody');
  tbody.innerHTML = '';

  MODELS.forEach(row => {
    const tr = document.createElement('tr');
    const th = document.createElement('th');
    th.textContent = row.charAt(0).toUpperCase() + row.slice(1);
    tr.appendChild(th);

    MODELS.forEach(col => {
      const td = document.createElement('td');
      if (row === col) {
        td.textContent = '—';
      } else {
        const key = [row, col].sort().join('_vs_');
        const val = matrix[key];
        if (val != null) {
          td.textContent = `${val}%`;
          td.className = val >= 75 ? 'agreement-cell-high'
                       : val >= 55 ? 'agreement-cell-medium'
                       :             'agreement-cell-low';
        } else {
          td.textContent = 'N/A';
        }
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}
```

#### 14.2.4 Hook sub-tab click events

```javascript
// Add inside your DOMContentLoaded or tab-init block
document.querySelectorAll('.subtab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.subtab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const mode    = btn.dataset.mode;
    const horizon = parseInt(btn.dataset.horizon, 10);
    const ticker  = getCurrentDrawerTicker();  // your existing helper

    if (mode === 'ensemble') {
      document.getElementById('ensemblePanel').style.display = 'block';
      const useDynamic = true;  // flip to false to force static weights
      loadEnsembleForecast(ticker, horizon, useDynamic);
    } else {
      document.getElementById('ensemblePanel').style.display = 'none';
      loadKronosForecast(ticker, horizon);  // your existing Kronos loader
    }
  });
});

// Individual models toggle
document.getElementById('showIndividualModels')?.addEventListener('change', () => {
  const ticker  = getCurrentDrawerTicker();
  const horizon = parseInt(document.querySelector('.subtab-btn.active')?.dataset.horizon ?? 10);
  loadEnsembleForecast(ticker, horizon, true);
});
```

---

### 14.3 Phase 3 Test Checklist

- [ ] Clicking **⚡ Ensemble** sub-tab fires `POST /api/ensemble_forecast` (visible in DevTools Network tab)
- [ ] Gold ensemble path renders on the chart; purple/orange/teal individual paths appear when the toggle is checked
- [ ] Conviction badge updates colour correctly for HIGH / MODERATE / LOW
- [ ] Model Weights Bar widths sum to 100% for both static and dynamic weights
- [ ] Agreement Matrix renders a 3×3 table with colour-coded cells
- [ ] Switching back to 3D / 5D / 10D hides `ensemblePanel` and re-renders the Kronos-only chart
- [ ] No console errors on tickers where one model is degraded (`degraded: true` in response)

---

## 15. Phase 4 — Backtester & Polish

> **Goal:** Extend the existing On-the-Fly Backtester panel to compare all three individual models against the blended ensemble on historical data. Add a Kronos/Ensemble toggle, performance-profile the full stack, and optionally surface ensemble scores in the Kronos Batch Sort.

### 15.1 Backend — Ensemble Backtest Endpoint

Add this new route to `app.py` alongside `/api/kronos-backtest`:

```python
@app.route('/api/ensemble-backtest', methods=['GET'])
def get_ensemble_backtest():
    """
    GET /api/ensemble-backtest?ticker=RELIANCE&horizon=10

    Runs a walk-forward backtest over the last `horizon` trading days,
    comparing Kronos, Prophet, ARIMA, and the blended Ensemble path
    against actual closes.

    Returns per-model MAE, MAPE, directional accuracy, and band hit rate
    alongside the blended ensemble metrics.
    """
    from flask import request
    import time
    t0 = time.time()

    ticker  = request.args.get('ticker', '').strip().upper().replace('NSE:', '')
    horizon = int(request.args.get('horizon', 10))

    if not ticker:
        return jsonify({'error': 'ticker_required'}), 400
    if horizon < 3 or horizon > 20:
        return jsonify({'error': 'horizon must be between 3 and 20'}), 400

    history = fetch_historical_prices(ticker, range_str='2y')
    if not history or len(history) < horizon + 80:
        return jsonify({'error': 'insufficient_history'}), 400

    # Split history: context window vs held-out actuals
    context = history[-(horizon + 120):-horizon]
    actuals = [float(d['close']) for d in history[-horizon:]]
    actual_dates = [d['date'] for d in history[-horizon:]]
    last_context_close = float(context[-1]['close'])

    # Inject context into backtest shim
    _BACKTEST_CTX_CACHE[ticker] = pd.DataFrame([{
        'ds': pd.to_datetime(d['date']),
        'y':  float(d['close'])
    } for d in context]).assign(ds=lambda df: df['ds'].dt.tz_localize(None))

    model_preds = {'kronos': None, 'prophet': None, 'arima': None}
    model_errors_bt = {}

    def _run(name, fn):
        try:
            return name, fn(ticker, horizon)
        except Exception as e:
            return name, e

    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [
            ex.submit(_run, 'kronos',  kronos_predict),
            ex.submit(_run, 'prophet', prophet_predict),
            ex.submit(_run, 'arima',   arima_predict),
        ]
        for fut in futs:
            name, result = fut.result(timeout=30)
            if isinstance(result, Exception):
                model_errors_bt[name] = str(result)
            else:
                model_preds[name] = result

    # Clean up shim
    _BACKTEST_CTX_CACHE.pop(ticker, None)

    active = {k: v for k, v in model_preds.items() if v is not None}
    if len(active) < 2:
        return jsonify({'error': 'backtest_failed', 'details': model_errors_bt}), 500

    # Build ensemble path using current dynamic weights if available
    default_w = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}
    total_w   = sum(default_w[m] for m in active)
    weights   = {m: default_w[m] / total_w for m in active}
    blend     = ensemble_blend(
        kronos_path=model_preds.get('kronos', []),
        prophet_path=model_preds.get('prophet', []),
        arima_path=model_preds.get('arima', []),
        weights=weights
    )
    active['ensemble'] = blend['ensemble_path']

    def _metrics(preds, actuals, prev_close):
        n = min(len(preds), len(actuals))
        if n == 0:
            return {}
        abs_err = [abs(preds[i] - actuals[i]) for i in range(n)]
        pct_err = [abs_err[i] / (actuals[i] + 1e-9) * 100 for i in range(n)]
        dir_hits = 0
        for i in range(n):
            p_ref = preds[i-1] if i > 0 else prev_close
            a_ref = actuals[i-1] if i > 0 else prev_close
            if (preds[i] > p_ref) == (actuals[i] > a_ref):
                dir_hits += 1
        return {
            'mae':                round(sum(abs_err) / n, 2),
            'mape':               round(sum(pct_err) / n, 2),
            'direction_accuracy': round(dir_hits / n * 100, 1),
            'n_days':             n
        }

    per_model = {
        name: _metrics(preds, actuals, last_context_close)
        for name, preds in active.items()
    }

    comparison_points = []
    for i, (date, actual) in enumerate(zip(actual_dates, actuals)):
        pt = {'date': date, 'actual': actual}
        for name, preds in active.items():
            pt[name] = round(preds[i], 2) if i < len(preds) else None
        comparison_points.append(pt)

    return jsonify({
        'ticker':             ticker,
        'horizon':            horizon,
        'per_model_metrics':  per_model,
        'comparison_points':  comparison_points,
        'model_errors':       model_errors_bt,
        'latency_ms':         round((time.time() - t0) * 1000)
    })
```

---

### 15.2 Frontend — Backtester Toggle & Comparison Table

Locate the existing backtester panel in `templates/index.html` and add the Kronos/Ensemble toggle above the metrics:

```html
<!-- Add above the backtester metrics panel -->
<div class="backtest-mode-toggle">
  <button class="bt-mode-btn active" data-mode="kronos">Kronos Only</button>
  <button class="bt-mode-btn" data-mode="ensemble">⚡ Ensemble</button>
</div>

<!-- Ensemble comparison table (hidden until Ensemble mode is active) -->
<div id="ensembleBacktestTable" style="display:none;">
  <table class="bt-comparison-table">
    <thead>
      <tr>
        <th>Model</th>
        <th>MAE</th>
        <th>MAPE %</th>
        <th>Dir. Acc %</th>
      </tr>
    </thead>
    <tbody id="btComparisonBody"></tbody>
  </table>
</div>
```

Add to `main.js`:

```javascript
const BT_MODEL_LABELS = {
  kronos: 'Kronos',
  prophet: 'Prophet',
  arima: 'ARIMA',
  ensemble: '⚡ Ensemble'
};

async function loadEnsembleBacktest(ticker, horizon = 10) {
  try {
    const res = await fetch(`/api/ensemble-backtest?ticker=${ticker}&horizon=${horizon}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderBacktestComparisonTable(data.per_model_metrics);
  } catch (err) {
    console.error('[EnsembleCast Backtest]', err);
  }
}

function renderBacktestComparisonTable(metrics) {
  const tbody = document.getElementById('btComparisonBody');
  tbody.innerHTML = '';

  // Render in fixed order: individual models first, ensemble last
  const ORDER = ['kronos', 'prophet', 'arima', 'ensemble'];
  ORDER.forEach(name => {
    const m = metrics[name];
    if (!m) return;
    const tr = document.createElement('tr');
    if (name === 'ensemble') tr.classList.add('ensemble-row');
    tr.innerHTML = `
      <td>${BT_MODEL_LABELS[name] ?? name}</td>
      <td>${m.mae}</td>
      <td>${m.mape}%</td>
      <td>${m.direction_accuracy}%</td>
    `;
    tbody.appendChild(tr);
  });
}

// Hook toggle buttons
document.querySelectorAll('.bt-mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.bt-mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const mode   = btn.dataset.mode;
    const ticker = getCurrentDrawerTicker();

    if (mode === 'ensemble') {
      document.getElementById('ensembleBacktestTable').style.display = 'block';
      loadEnsembleBacktest(ticker);
    } else {
      document.getElementById('ensembleBacktestTable').style.display = 'none';
      loadKronosBacktest(ticker);  // your existing Kronos backtest loader
    }
  });
});
```

Add styling:

```css
.bt-comparison-table { width:100%; border-collapse:collapse; font-size:0.82rem; margin-top:8px; }
.bt-comparison-table th { padding:5px 8px; background:rgba(255,255,255,0.05);
                           border-bottom:1px solid rgba(255,255,255,0.12); text-align:left; }
.bt-comparison-table td { padding:4px 8px; border-bottom:1px solid rgba(255,255,255,0.06); }
.bt-comparison-table tr.ensemble-row td { color:#fbbf24; font-weight:700; }
.backtest-mode-toggle { display:flex; gap:6px; margin-bottom:8px; }
.bt-mode-btn { padding:4px 12px; border-radius:5px; border:1px solid rgba(255,255,255,0.15);
               background:transparent; color:#ccc; cursor:pointer; font-size:0.82rem; }
.bt-mode-btn.active { background:#7c3aed; color:#fff; border-color:#7c3aed; }
```

---

### 15.3 Performance Profiling

Add this lightweight profiling decorator to `app.py` to measure end-to-end latency of the ensemble endpoint on startup:

```python
import functools

def profile_endpoint(fn):
    """Logs wall-clock time for any decorated Flask route on each call."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        import time
        t0 = time.time()
        result = fn(*args, **kwargs)
        elapsed = round((time.time() - t0) * 1000)
        if elapsed > 6000:
            print(f'[PERF WARNING] {fn.__name__} took {elapsed}ms — exceeds 6s SLA')
        return result
    return wrapper

# Decorate the ensemble endpoint:
@app.route('/api/ensemble_forecast', methods=['POST'])
@profile_endpoint
def api_ensemble_forecast():
    ...  # existing implementation
```

**Tuning levers if latency exceeds 6s:**

| Lever | Where | Impact |
|---|---|---|
| Reduce Prophet `n_changepoints` | `prophet_predict()` | −0.5–1.0s |
| Reduce `changepoint_prior_scale` to 0.01 | `prophet_predict()` | −0.3s |
| Use ARIMA(1,1,0) fallback only | `arima_predict()` | −0.2s on small-caps |
| Cache `_fetch_price_history` result at endpoint entry | `api_ensemble_forecast()` | Eliminates 2 duplicate fetches |
| Skip dynamic weights for cached tickers | `compute_dynamic_weights()` | −2–4s per request |

---

### 15.4 Batch Sort Integration (Optional)

In the existing `/api/kronos_batch_sort` or equivalent, you can optionally surface the ensemble conviction label as a sort signal. Add this helper:

```python
def get_ensemble_conviction_label(ticker: str) -> str:
    """
    Returns cached ensemble conviction for `ticker` if available in the
    kronos_forecasts table (avoids re-running the full ensemble just for sort).
    Returns 'UNKNOWN' if no cached result exists.
    """
    try:
        conn = get_db_connection()
        row = conn.execute(
            """SELECT forecast_json FROM kronos_forecasts
               WHERE ticker = ? AND model_type = 'ensemble'
               AND datetime(generated_at) > datetime('now', '-4 hours')
               ORDER BY generated_at DESC LIMIT 1""",
            (ticker,)
        ).fetchone()
        conn.close()
        if row:
            import json
            data = json.loads(row['forecast_json'])
            return data.get('conviction', 'UNKNOWN')
    except Exception:
        pass
    return 'UNKNOWN'
```

Use the conviction label as a sort tiebreaker in batch results:

```python
CONVICTION_ORDER = {'HIGH': 0, 'MODERATE': 1, 'LOW': 2, 'UNKNOWN': 3}

# Inside your batch sort:
batch_results.sort(
    key=lambda s: (
        -s['swingscore'],                                      # primary: swing score
        CONVICTION_ORDER.get(                                  # secondary: conviction
            get_ensemble_conviction_label(s['clean_ticker']), 3
        )
    )
)
```

---

### 15.5 Phase 4 Test Checklist

- [ ] `GET /api/ensemble-backtest?ticker=RELIANCE&horizon=10` returns all four model metrics
- [ ] Ensemble row in the comparison table is visually highlighted in gold
- [ ] Kronos/Ensemble toggle correctly switches between the single-model and multi-model backtester views
- [ ] `profile_endpoint` logs a warning for any call exceeding 6s
- [ ] Batch sort respects conviction order as a tiebreaker (verify with two stocks having equal swing scores)
- [ ] Re-run Phase 1 & 2 unit tests — zero regressions

---

*Last Updated: May 2026 | Author: MomentumScan Dev*
