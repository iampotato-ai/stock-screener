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
  "ensemble_path": [2450.2, 2461.5, 2478.3, ...],
  "model_paths": {
    "kronos":  [2455.1, 2468.0, 2481.2, ...],
    "prophet": [2447.8, 2455.3, 2472.1, ...],
    "arima":   [2448.0, 2461.0, 2479.5, ...]
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
