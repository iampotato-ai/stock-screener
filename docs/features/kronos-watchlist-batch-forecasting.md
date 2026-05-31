# Kronos Watchlist Batch Forecasting — Feature Spec

> **Feature ID:** `FEAT-002`  
> **Branch:** `feature/workspace-ui`  
> **Status:** 📋 Planned  
> **Priority:** High  
> **Component:** Watchlist Center + Kronos AI Predictor

---

## 1. Overview

Wire the existing `predict_batch()` parallel prediction engine into the **Watchlist Center** to display a live **"Kronos Momentum Ranking"** — a sorted table of all watchlist stocks ranked by their expected 5-day forward return as predicted by the Kronos-small model.

This gives you at-a-glance AI-powered prioritisation of your watchlist every morning before market open.

---

## 2. Goals

- Surface Kronos 5-day predicted return for every stock in every watchlist section.
- Rank stocks **highest expected return → lowest** within each section.
- Reuse the existing 4-hour TTL cache (`_kronos_cache`) — no redundant model inference.
- Keep the existing Watchlist Center UI layout; add a new **"Kronos Rank"** column/badge.
- Graceful degradation: stocks where Kronos is unavailable or errored show `—`.

---

## 3. Backend Changes

### 3.1 New API Endpoint

```
GET /api/watchlist/kronos-ranking?section_id=<id>
```

**Query Params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `section_id` | `string` | _(all sections)_ | Filter to a single watchlist section. Omit to rank all sections. |
| `pred_len` | `int` | `5` | Forecast horizon (3, 5, or 10 days). |

**Response Shape:**

```json
{
  "generated_at": "2026-05-30T18:41:00",
  "pred_len": 5,
  "sections": [
    {
      "id": "swing-watchlist",
      "name": "Swing Trades",
      "rankings": [
        {
          "ticker": "RELIANCE",
          "rank": 1,
          "predicted_return_pct": 3.42,
          "ai_forecast_bias": "Bullish Continuation",
          "ai_confidence_score": 78,
          "forecast_metrics": { ... },
          "cache_hit": true
        },
        ...
      ]
    }
  ]
}
```

---

### 3.2 `predict_batch()` Integration

`predict_batch()` already exists in the model layer and runs inference in parallel via `ThreadPoolExecutor`. The new endpoint calls it as follows:

```python
from concurrent.futures import ThreadPoolExecutor

def _run_kronos_for_ticker(ticker):
    """Wraps the existing single-ticker Kronos logic; returns ranking dict."""
    cached = _get_kronos_cache(ticker)
    if cached:
        bias, score, forecast_list, metrics = cached
        return build_ranking_entry(ticker, bias, score, metrics, cache_hit=True)

    history = fetch_historical_prices(ticker, range_str="6mo")
    if not history or len(history) < 10:
        return build_ranking_entry(ticker, None, 0, {}, cache_hit=False)

    # ... existing Kronos inference logic (same as /api/setup-analysis) ...
    # Returns populated ranking entry and populates _kronos_cache.

def batch_kronos_ranking(tickers, pred_len=5):
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(_run_kronos_for_ticker, tickers))
    results.sort(key=lambda x: x["predicted_return_pct"] or -999, reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1
    return results
```

**Key design decisions:**
- Workers capped at **8** (same as `populate_screener_intelligence`) to avoid NSE/Yahoo rate limiting.
- Cache-first: any ticker already in `_kronos_cache` within TTL is served immediately — no model call.
- `predicted_return_pct` is derived from `forecast_metrics["return_pct"]` (the M1 endpoint return already computed in `/api/setup-analysis`).

---

### 3.3 `build_ranking_entry()` Helper

```python
def build_ranking_entry(ticker, bias, score, metrics, cache_hit):
    return {
        "ticker": ticker,
        "rank": None,  # assigned post-sort
        "predicted_return_pct": metrics.get("return_pct"),  # M1 metric
        "ai_forecast_bias": bias,
        "ai_confidence_score": score,
        "forecast_metrics": metrics,
        "cache_hit": cache_hit
    }
```

---

## 4. Frontend Changes

### 4.1 Watchlist Center — New "Kronos Rank" Column

Add a **Kronos Rank** column to the existing watchlist table. Column is toggled on/off via the existing column visibility controls.

| Column | Data Source | Display |
|---|---|---|
| `# Rank` | `ranking.rank` | Badge: `#1`, `#2`, ... |
| `AI Return (5d)` | `ranking.predicted_return_pct` | `+3.42%` in green / `-1.2%` in red |
| `Bias` | `ranking.ai_forecast_bias` | Pill badge (same style as setup-analysis panel) |
| `Confidence` | `ranking.ai_confidence_score` | `78%` with small bar |

### 4.2 Sort Trigger

Add a **"Kronos Sort"** button (⚡ icon) in the Watchlist Center header bar. On click:

1. Calls `GET /api/watchlist/kronos-ranking` for the active section.
2. Shows a loading spinner on the Kronos column while batch inference runs.
3. Re-sorts the displayed rows by `predicted_return_pct` descending on response.
4. Shows a `Cache / Live` pill on each row to indicate whether result is freshly inferred or served from cache.

### 4.3 Stale / Unavailable State

- If `predicted_return_pct` is `null` → show `—` in grey.
- If `ai_forecast_bias` is `null` → show `Unavailable` pill in grey.
- Rows with `—` are sorted to the bottom regardless of other metrics.

---

## 5. Caching Strategy

| Cache Layer | TTL | Scope |
|---|---|---|
| `_kronos_cache` (in-memory `OrderedDict`) | 4 hours | Per ticker, shared across all endpoints |
| `kronos_forecasts` (SQLite) | Same-day | Per ticker + `pred_len`, persists across restarts |

The batch endpoint **reads from both layers** before triggering live inference. Priority:

```
_kronos_cache (memory) → kronos_forecasts DB (today's row) → Live Kronos inference
```

---

## 6. Error Handling

| Scenario | Behaviour |
|---|---|
| Yahoo Finance timeout for a ticker | Skip ticker; return `null` metrics; log `[Kronos Batch] Fetch failed for {ticker}` |
| Kronos model not loaded | Return 503 with `{"error": "Kronos predictor not loaded"}` |
| Ticker has < 10 bars of history | Skip inference; return `null` metrics |
| Partial batch failure (some tickers fail) | Return results for successful tickers; failed tickers get `null` metrics |

---

## 7. Acceptance Criteria

- [ ] `GET /api/watchlist/kronos-ranking` returns rankings for all tickers in a watchlist section within **30 seconds** (worst case: no cache, 8-worker parallel fetch + inference).
- [ ] Cache hits are served within **2 seconds** regardless of watchlist size.
- [ ] Watchlist Center renders the Kronos Rank column without breaking existing table layout.
- [ ] "Kronos Sort" button correctly re-orders rows by `predicted_return_pct`.
- [ ] Tickers with unavailable data are sorted to the bottom.
- [ ] No additional model load is triggered if `get_kronos_predictor()` has already initialised the model.
- [ ] Works across all watchlist section types (manual watchlist, scanner snapshot imports).

---

## 8. Implementation Order

1. **Backend first:** Add `build_ranking_entry()`, `batch_kronos_ranking()`, and the `/api/watchlist/kronos-ranking` endpoint to `app.py`.
2. **Test endpoint** via curl / Postman with a small 5-ticker watchlist section.
3. **Frontend column:** Add `Kronos Rank` column to the watchlist table template.
4. **Frontend button:** Wire the "Kronos Sort" button and loading state.
5. **Polish:** Colour-code return %, add cache/live pill, handle null states.

---

## 9. Related Files

| File | Change |
|---|---|
| `app.py` | Add `build_ranking_entry()`, `batch_kronos_ranking()`, `/api/watchlist/kronos-ranking` route |
| `templates/index.html` | Watchlist table — new Kronos column, sort button, loading spinner |
| `static/app.js` (or inline script) | Fetch + render Kronos ranking, sort logic |
| `docs/feature/kronos-watchlist-batch-forecasting.md` | This file |

---

_Last updated: 2026-05-30_
