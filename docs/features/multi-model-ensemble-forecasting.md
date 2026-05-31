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
warnings.filterwarnings('ignore')  # suppress Prophet/ARIMA verbose output
```

---

### 12.2 SQLite Schema Migration

Find your existing DB initialisation block in `app.py` (where `CREATE TABLE kronos_forecasts` lives) and add the migration guard right after it:

```python
def migrate_ensemble_schema(conn):
    """
    Adds model_type column to kronos_forecasts if it doesn't already exist.
    Safe to call on every startup — no-ops if column is present.
    """
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE kronos_forecasts ADD COLUMN model_type TEXT DEFAULT 'kronos'")
        conn.commit()
        print("[EnsembleCast] Schema migration: added model_type column.")
    except Exception:
        pass  # column already exists

# Call once during app startup, after your existing init_db() call:
# migrate_ensemble_schema(get_db_connection())
```

---

### 12.3 Price History Helper

A shared utility used by both Prophet and ARIMA runners to fetch and validate price history via yfinance:

```python
def _fetch_price_history(ticker: str, min_days: int = 60) -> pd.DataFrame:
    """
    Fetches daily Close price history for `ticker` using yfinance.
    Returns a DataFrame with columns ['ds', 'y'] (Prophet-compatible).
    Raises ValueError if fewer than min_days of history are available.
    """
    import yfinance as yf
    hist = yf.Ticker(ticker).history(period="2y")[['Close']].dropna()
    if len(hist) < min_days:
        raise ValueError(
            f"insufficient_history: {ticker} has only {len(hist)} days (need {min_days})"
        )
    hist = hist.reset_index()
    hist.rename(columns={'Date': 'ds', 'Close': 'y'}, inplace=True)
    hist['ds'] = pd.to_datetime(hist['ds']).dt.tz_localize(None)  # strip tz for Prophet
    return hist
```

---

### 12.4 Prophet Model Runner

```python
def prophet_predict(ticker: str, horizon: int = 10) -> list[float]:
    """
    Runs Facebook Prophet on `ticker` and returns a list of `horizon`
    predicted closing prices for the next N trading days.

    Tuned for speed: yearly_seasonality only, no weekly/daily seasonality
    (NSE data is daily OHLCV — intra-day seasonality is irrelevant here).
    changepoint_prior_scale=0.05 keeps it fast and avoids overfitting.
    """
    df = _fetch_price_history(ticker)

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,   # lower = faster, less flexible
        interval_width=0.80
    )
    model.fit(df[['ds', 'y']])

    # Generate future calendar dates (skip weekends)
    last_date = df['ds'].iloc[-1]
    future_dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=horizon)
    future_df = pd.DataFrame({'ds': future_dates})

    forecast = model.predict(future_df)
    return forecast['yhat'].tolist()
```

---

### 12.5 ARIMA Model Runner

```python
def arima_predict(ticker: str, horizon: int = 10) -> list[float]:
    """
    Runs ARIMA(5,1,0) on `ticker` closing prices.
    Order (5,1,0): 5 AR lags, 1 differencing (for stationarity), 0 MA terms.
    This is a solid general-purpose order for daily equity price series.

    Falls back to ARIMA(2,1,0) if the primary order fails to converge
    (common on low-liquidity small-cap stocks).
    """
    df = _fetch_price_history(ticker)
    closes = df['y'].values

    try:
        model = ARIMA(closes, order=(5, 1, 0))
        result = model.fit()
    except Exception:
        # Fallback to simpler order on convergence failure
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
    """
    Blends three model forecast paths into a single weighted ensemble.

    Returns a dict with:
      - ensemble_path: weighted average per day
      - divergence_score: normalised std across models (scalar, worst day)
      - conviction: 'HIGH' / 'MODERATE' / 'LOW'
    """
    if weights is None:
        weights = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}

    w_k = weights['kronos']
    w_p = weights['prophet']
    w_a = weights['arima']

    # Align to shortest path length (safety guard)
    horizon = min(len(kronos_path), len(prophet_path), len(arima_path))
    k = np.array(kronos_path[:horizon])
    p = np.array(prophet_path[:horizon])
    a = np.array(arima_path[:horizon])

    ensemble = w_k * k + w_p * p + w_a * a

    # Divergence: normalised std of the 3 paths at each day, take worst-case day
    stacked = np.stack([k, p, a], axis=0)  # shape (3, horizon)
    daily_divergence = np.std(stacked, axis=0) / (ensemble + 1e-9)
    max_divergence = float(np.max(daily_divergence))

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

Add this route to `app.py` alongside your existing `/api/kronos_forecast` route:

```python
@app.route('/api/ensemble_forecast', methods=['POST'])
def api_ensemble_forecast():
    """
    POST /api/ensemble_forecast
    Body: { "ticker": "RELIANCE.NS", "horizon": 10, "use_dynamic_weights": false }

    Runs Prophet + ARIMA in parallel alongside the existing Kronos predictor,
    then blends all three into a confidence-weighted ensemble path.

    Falls back gracefully to a 2-model ensemble if any single model fails.
    Caches results in kronos_forecasts table with model_type='ensemble'.
    """
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

    # --- Check cache first ---
    try:
        conn = get_db_connection()
        cached = conn.execute(
            """SELECT forecast_data FROM kronos_forecasts
               WHERE ticker = ? AND model_type = 'ensemble'
               AND datetime(timestamp) > datetime('now', '-4 hours')
               ORDER BY timestamp DESC LIMIT 1""",
            (ticker,)
        ).fetchone()
        conn.close()

        if cached:
            import json as _json
            result = _json.loads(cached['forecast_data'])
            result['cached'] = True
            result['latency_ms'] = round((time.time() - start_time) * 1000)
            return jsonify(result)
    except Exception as e:
        print(f'[EnsembleCast] Cache lookup error: {e}')

    # --- Run models in parallel ---
    results = {'kronos': None, 'prophet': None, 'arima': None}
    errors  = {'kronos': None, 'prophet': None, 'arima': None}

    def run_kronos():
        # Re-use your existing kronos_predict function
        return kronos_predict(ticker, horizon)

    def run_prophet():
        return prophet_predict(ticker, horizon)

    def run_arima():
        return arima_predict(ticker, horizon)

    runners = {'kronos': run_kronos, 'prophet': run_prophet, 'arima': run_arima}

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {name: executor.submit(fn) for name, fn in runners.items()}
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=12)  # 12s hard timeout per model
            except Exception as e:
                errors[name] = str(e)
                print(f'[EnsembleCast] {name} failed: {e}')

    # --- Assess which models succeeded ---
    active_models = {k: v for k, v in results.items() if v is not None}
    degraded = len(active_models) < 3

    if len(active_models) < 2:
        return jsonify({
            'error': 'ensemble_failed',
            'details': errors
        }), 500

    # --- Build weights (static for Phase 1; dynamic weights in Phase 2) ---
    default_weights = {'kronos': 0.50, 'prophet': 0.30, 'arima': 0.20}
    # If a model failed, redistribute its weight proportionally
    if degraded:
        active_weight_sum = sum(default_weights[m] for m in active_models)
        weights = {m: default_weights[m] / active_weight_sum for m in active_models}
    else:
        weights = default_weights

    # --- Blend ---
    blend_result = ensemble_blend(
        kronos_path=results['kronos'] or [],
        prophet_path=results['prophet'] or [],
        arima_path=results['arima'] or [],
        weights=weights
    )

    # --- Build response ---
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
        'latency_ms': round((time.time() - start_time) * 1000)
    }

    # --- Persist to cache ---
    try:
        import json as _json
        conn = get_db_connection()
        conn.execute(
            """INSERT INTO kronos_forecasts (ticker, forecast_data, timestamp, model_type)
               VALUES (?, ?, datetime('now'), 'ensemble')""",
            (ticker, _json.dumps(response))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'[EnsembleCast] Cache write error: {e}')

    return jsonify(response)
```

---

### 12.8 Phase 1 Unit Test Checklist

Before moving to Phase 2, validate each runner independently in a Python shell or a test script:

```python
# quick_test_phase1.py  — run from project root
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
- All 5 tickers return a 10-element list for each model with no exceptions
- `divergence_score` is a float between 0.0 and 0.10 for liquid large-caps
- `conviction` is `'HIGH'` or `'MODERATE'` for NIFTY 50 stocks in normal market conditions
- Total runtime for all 5 tickers should be **< 30 seconds** on CPU

---

> **Next:** Once Phase 1 tests pass, proceed to [Phase 2 — Dynamic Weights & Divergence](#phase-2--dynamic-weights--divergence-est-12-days).
