# Kronos AI Prediction Panel

**Feature:** Expose `KronosPredictor` forecasts as a first-class UI panel inside the Trade Drawer and a standalone "AI Forecast" tab.

---

## Background

`model/kronos.py` contains a fully-trained `KronosPredictor` class that wraps the `Kronos` transformer model and `KronosTokenizer`. It supports:

- **Single-series prediction** via `predictor.predict(df, x_timestamp, y_timestamp, pred_len, ...)`
- **Batch prediction** via `predictor.predict_batch(df_list, ...)`
- **Stochastic confidence bands** via `sample_count` — the model runs `N` parallel Monte Carlo samples and averages them; individual samples are available before averaging to derive percentile bands.

The model is **not yet wired into the dashboard**. This document specifies exactly how to surface it.

---

## Goals

1. Show predicted OHLCV candles for the next **3 / 5 / 10 sessions** (user-configurable).
2. Show **confidence bands** (P10–P90 envelope) derived from `sample_count` sampling.
3. Provide a **"Forecast vs Actual" backtesting view** once real candles arrive for the predicted dates.
4. Integrate into the **Trade Drawer** (quick glance) and a dedicated **"AI Forecast" workspace tab** (full detail).

---

## Architecture

### 1. Backend — `/api/kronos-forecast`

#### Route

```
GET /api/kronos-forecast?ticker=RELIANCE&pred_len=5&sample_count=20
```

#### Parameters

| Param | Type | Default | Notes |
|---|---|---|---|
| `ticker` | `str` | required | NSE ticker, e.g. `RELIANCE` |
| `pred_len` | `int` | `5` | Sessions to forecast: `3`, `5`, or `10` |
| `sample_count` | `int` | `20` | Monte Carlo samples for confidence bands. Higher = smoother bands, slower. |
| `top_p` | `float` | `0.9` | Nucleus sampling threshold passed to `predictor.predict()` |
| `T` | `float` | `1.0` | Sampling temperature |

#### What the handler does

```python
# Pseudocode — fill in your data-fetch pattern
@app.route('/api/kronos-forecast')
def kronos_forecast():
    ticker   = request.args.get('ticker')
    pred_len = int(request.args.get('pred_len', 5))
    n        = int(request.args.get('sample_count', 20))

    # 1. Fetch last ~200 daily candles for context
    df, x_timestamp = fetch_ohlcv(ticker, periods=200)  # returns DataFrame + DatetimeIndex

    # 2. Build future timestamps (next pred_len trading days, skip weekends/holidays)
    y_timestamp = next_trading_days(x_timestamp[-1], pred_len)

    # 3. Run predictor with sample_count=n to collect all samples (not just the mean)
    #    Temporarily patch generate() to return raw samples before averaging,
    #    OR call generate() n times with sample_count=1 and stack results.
    raw_samples = []
    for _ in range(n):
        pred_df = predictor.predict(df, x_timestamp, y_timestamp, pred_len,
                                    sample_count=1, verbose=False)
        raw_samples.append(pred_df[['open','high','low','close','volume']].values)

    raw = np.stack(raw_samples, axis=0)          # (n, pred_len, 5)
    mean_pred = raw.mean(axis=0)                  # (pred_len, 5)
    p10       = np.percentile(raw, 10, axis=0)   # lower band
    p90       = np.percentile(raw, 90, axis=0)   # upper band

    # 4. Build response
    dates = [d.strftime('%Y-%m-%d') for d in y_timestamp]
    cols  = ['open','high','low','close','volume']

    result = {
        'ticker':   ticker,
        'pred_len': pred_len,
        'forecast': [
            {
                'date':    dates[i],
                **{c: round(float(mean_pred[i, j]), 2) for j, c in enumerate(cols)},
                'p10_close': round(float(p10[i, 3]), 2),
                'p90_close': round(float(p90[i, 3]), 2),
            }
            for i in range(pred_len)
        ],
        'last_close': float(df['close'].iloc[-1]),
        'generated_at': datetime.utcnow().isoformat(),
    }
    return jsonify(result)
```

#### Confidence Band Strategy

Because `auto_regressive_inference` averages samples *internally* (`preds = np.mean(preds, axis=1)`), to get individual samples for P10/P90 you have two options:

- **Option A (simple):** Call `predictor.predict(..., sample_count=1)` in a loop `n` times. Slightly slower but zero code changes to `kronos.py`.
- **Option B (fast):** Patch `auto_regressive_inference` to return `z` before the `np.mean` call, so all `sample_count` paths are returned at once. One-line change, much faster at `sample_count=20`.

**Recommended: Option B.** Add a `return_samples=False` flag to `auto_regressive_inference`:

```python
# In kronos.py — auto_regressive_inference(), last 5 lines
z = z.reshape(-1, sample_count, z.size(1), z.size(2))
preds = z.cpu().numpy()
if return_samples:
    return preds                    # shape: (batch, sample_count, seq_len, feat)
preds = np.mean(preds, axis=1)
return preds
```

---

### 2. Frontend — Trade Drawer Panel (Quick View)

**Trigger:** When `openTradeDrawer(ticker)` fires, after the existing `/api/setup-analysis` fetch resolves, fire a second fetch to `/api/kronos-forecast?ticker=X&pred_len=5&sample_count=20`.

**HTML (insert inside `#trade-drawer`, after `#drawer-kronos-forecast-row`):**

```html
<!-- Kronos AI Forecast Row -->
<div id="drawer-kronos-section" style="display:none; margin-top: 1.25rem;">
  <div class="drawer-section-header">
    <span>🔮 Kronos AI Forecast</span>
    <div class="kronos-pred-len-toggle">
      <button class="kronos-len-btn active" data-len="3">3D</button>
      <button class="kronos-len-btn" data-len="5">5D</button>
      <button class="kronos-len-btn" data-len="10">10D</button>
    </div>
    <span id="kronos-confidence-badge" class="badge" style="font-size:0.7rem;"></span>
  </div>

  <!-- Mini forecast candle chart -->
  <div id="drawer-kronos-chart" style="height: 160px; width: 100%;"></div>

  <!-- Forecast table -->
  <table id="drawer-kronos-table" class="kronos-forecast-table">
    <thead>
      <tr>
        <th>Date</th>
        <th>Open</th>
        <th>High</th>
        <th>Low</th>
        <th>Close</th>
        <th>Vol</th>
        <th>Band (P10–P90)</th>
      </tr>
    </thead>
    <tbody id="drawer-kronos-tbody"></tbody>
  </table>

  <!-- Forecast vs Actual toggle (shown only when actuals exist) -->
  <div id="kronos-backtest-row" style="display:none; margin-top:0.75rem;">
    <button id="btn-kronos-backtest" class="btn-secondary" style="font-size:0.8rem;">
      📊 Show Forecast vs Actual
    </button>
    <span id="kronos-mae-badge" class="badge" style="margin-left:0.5rem; font-size:0.7rem;"></span>
  </div>
</div>
```

**JavaScript — `renderKronosForecastPanel(data)`:**

```javascript
let activeKronosChart = null;

function destroyKronosChart() {
    if (activeKronosChart) {
        activeKronosChart.destroy();
        activeKronosChart = null;
    }
}

function renderKronosForecastPanel(data) {
    const section = document.getElementById('drawer-kronos-section');
    if (!section || !data || !data.forecast) return;
    section.style.display = 'block';

    // Badge: expected move from last close to mean forecast close
    const lastClose = data.last_close;
    const finalClose = data.forecast[data.forecast.length - 1].close;
    const movePct = ((finalClose - lastClose) / lastClose * 100).toFixed(2);
    const badge = document.getElementById('kronos-confidence-badge');
    if (badge) {
        badge.textContent = `${movePct > 0 ? '▲' : '▼'} ${Math.abs(movePct)}% over ${data.pred_len}D`;
        badge.style.background = movePct > 0
            ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)';
        badge.style.color = movePct > 0 ? '#10b981' : '#ef4444';
    }

    // Table rows
    const tbody = document.getElementById('drawer-kronos-tbody');
    if (tbody) {
        tbody.innerHTML = data.forecast.map(row => {
            const closeClass = row.close >= lastClose ? 'val-up' : 'val-down';
            const band = `₹${row.p10_close.toLocaleString('en-IN')} – ₹${row.p90_close.toLocaleString('en-IN')}`;
            return `
              <tr>
                <td>${row.date}</td>
                <td>₹${row.open.toLocaleString('en-IN')}</td>
                <td>₹${row.high.toLocaleString('en-IN')}</td>
                <td>₹${row.low.toLocaleString('en-IN')}</td>
                <td class="${closeClass}" style="font-weight:700;">₹${row.close.toLocaleString('en-IN')}</td>
                <td>${formatVolume(row.volume)}</td>
                <td style="font-size:0.75rem; color:var(--color-text-secondary);">${band}</td>
              </tr>`;
        }).join('');
    }

    // Lightweight Charts — candlestick + P10/P90 area band
    destroyKronosChart();
    const container = document.getElementById('drawer-kronos-chart');
    if (!container || typeof LightweightCharts === 'undefined') return;

    const chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 160,
        layout: { background: { color: 'transparent' }, textColor: 'var(--color-text-secondary)' },
        grid: { vertLines: { visible: false }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
        timeScale: { borderVisible: false },
        rightPriceScale: { borderVisible: false },
    });
    activeKronosChart = chart;

    const candleSeries = chart.addCandlestickSeries({
        upColor: '#10b981', downColor: '#ef4444',
        borderUpColor: '#10b981', borderDownColor: '#ef4444',
        wickUpColor: '#10b981', wickDownColor: '#ef4444',
    });
    candleSeries.setData(data.forecast.map(r => ({
        time: r.date,
        open: r.open, high: r.high, low: r.low, close: r.close,
    })));

    // P10 lower band (area)
    const bandLow = chart.addAreaSeries({
        lineColor: 'rgba(99,102,241,0.3)', topColor: 'rgba(99,102,241,0.08)',
        bottomColor: 'transparent', lineWidth: 1,
    });
    bandLow.setData(data.forecast.map(r => ({ time: r.date, value: r.p10_close })));

    // P90 upper band (area)
    const bandHigh = chart.addAreaSeries({
        lineColor: 'rgba(99,102,241,0.3)', topColor: 'transparent',
        bottomColor: 'rgba(99,102,241,0.08)', lineWidth: 1,
    });
    bandHigh.setData(data.forecast.map(r => ({ time: r.date, value: r.p90_close })));

    chart.timeScale().fitContent();
}
```

**Wiring inside `openTradeDrawer`:**

```javascript
// After setup-analysis fetch resolves and drawer is populated:
const kronosSection = document.getElementById('drawer-kronos-section');
if (kronosSection) {
    kronosSection.style.display = 'none';   // hide while loading
    destroyKronosChart();
}
fetch(`/api/kronos-forecast?ticker=${ticker}&pred_len=5&sample_count=20`)
    .then(r => r.json())
    .then(data => renderKronosForecastPanel(data))
    .catch(() => {});  // silent fail — forecast is non-critical

// Pred-len toggle buttons
document.querySelectorAll('.kronos-len-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.kronos-len-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const len = btn.dataset.len;
        fetch(`/api/kronos-forecast?ticker=${window.currentTradeStock?.clean_ticker}&pred_len=${len}&sample_count=20`)
            .then(r => r.json())
            .then(data => renderKronosForecastPanel(data));
    });
});
```

**Cleanup on drawer close:**

```javascript
// Inside btn-close-drawer click handler, add:
destroyKronosChart();
const kronosSection = document.getElementById('drawer-kronos-section');
if (kronosSection) kronosSection.style.display = 'none';
```

---

### 3. Frontend — "AI Forecast" Workspace Tab (Full Detail)

Add a new tab next to `screener`, `watchlist`, `rrg`:

```html
<button class="workspace-tab" data-view="ai-forecast">🔮 AI Forecast</button>
```

```html
<div id="view-ai-forecast" class="workspace-view">
  <!-- Stock search to pick a symbol -->
  <div class="ai-forecast-header">
    <input id="kronos-ticker-input" placeholder="Enter NSE ticker…" class="search-input" style="max-width:200px;" />
    <div class="kronos-pred-len-toggle" style="margin-left:1rem;">
      <button class="kronos-len-btn active" data-len="3">3D</button>
      <button class="kronos-len-btn" data-len="5">5D</button>
      <button class="kronos-len-btn" data-len="10">10D</button>
    </div>
    <button id="btn-run-kronos" class="btn-primary" style="margin-left:1rem;">Run Forecast</button>
  </div>

  <!-- Full-size chart (reuses Lightweight Charts) -->
  <div id="kronos-full-chart" style="height: 380px; width: 100%; margin-top:1rem;"></div>

  <!-- Forecast + backtest table -->
  <div id="kronos-full-table-wrap" style="margin-top:1rem; overflow-x:auto;"></div>

  <!-- Forecast vs Actual section (shown after actuals arrive) -->
  <div id="kronos-backtest-section" style="display:none; margin-top:1.5rem;">
    <h3 style="font-size:0.9rem; color:var(--color-text-secondary);">Forecast vs Actual</h3>
    <div id="kronos-backtest-chart" style="height:280px;"></div>
    <div id="kronos-accuracy-metrics" style="margin-top:0.75rem; display:flex; gap:1.5rem;"></div>
  </div>
</div>
```

---

## Forecast vs Actual — Backtesting Logic

Once `pred_len` sessions have elapsed since a forecast was generated, surface accuracy metrics:

| Metric | Formula | Good threshold |
|---|---|---|
| **MAE** | mean(|forecast\_close − actual\_close|) | < 1.5% of close price |
| **MAPE** | mean(|forecast − actual| / actual) × 100 | < 3% |
| **Direction Accuracy** | % of days where direction (up/down) was correct | > 55% |
| **Band Hit Rate** | % of actual closes that fell within P10–P90 band | > 70% |

Store past forecasts in a new SQLite table `kronos_forecasts`:

```sql
CREATE TABLE IF NOT EXISTS kronos_forecasts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,
    generated_at TEXT NOT NULL,          -- ISO datetime
    pred_len    INTEGER NOT NULL,
    forecast_json TEXT NOT NULL,          -- JSON array of {date, open, high, low, close, volume, p10_close, p90_close}
    last_close  REAL NOT NULL
);
```

A background task (or lazy-evaluated on next drawer open) fetches actual OHLCV for the forecast dates and computes accuracy. Surface results in `#kronos-backtest-section`.

---

## CSS

```css
/* Forecast table */
.kronos-forecast-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
    margin-top: 0.5rem;
}
.kronos-forecast-table th {
    color: var(--color-text-muted);
    font-weight: 600;
    padding: 0.35rem 0.5rem;
    text-align: right;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.kronos-forecast-table th:first-child,
.kronos-forecast-table td:first-child { text-align: left; }
.kronos-forecast-table td {
    padding: 0.35rem 0.5rem;
    text-align: right;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}
.kronos-forecast-table tr:last-child td { border-bottom: none; }

/* Pred-len toggle */
.kronos-pred-len-toggle { display: flex; gap: 0.25rem; }
.kronos-len-btn {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    color: var(--color-text-secondary);
    border-radius: 4px;
    padding: 0.25rem 0.6rem;
    font-size: 0.75rem;
    cursor: pointer;
    transition: background 0.15s;
}
.kronos-len-btn.active,
.kronos-len-btn:hover {
    background: rgba(99,102,241,0.2);
    color: var(--color-text-primary);
    border-color: rgba(99,102,241,0.4);
}
```

---

## Implementation Checklist

### Backend
- [ ] Add `fetch_ohlcv(ticker, periods)` utility (or reuse existing data-fetch pattern from `app.py`)
- [ ] Add `next_trading_days(last_date, n)` utility that skips weekends + NSE holidays
- [ ] Load `KronosPredictor` once at app startup (module-level singleton, not per-request)
- [ ] Add `return_samples` flag to `auto_regressive_inference` in `kronos.py` (Option B)
- [ ] Implement `/api/kronos-forecast` route in `app.py`
- [ ] Create `kronos_forecasts` SQLite table in DB init
- [ ] Add `/api/kronos-backtest?ticker=X` route to retrieve stored forecasts + actuals

### Frontend
- [ ] Add `#drawer-kronos-section` HTML to Trade Drawer in `templates/index.html`
- [ ] Add `renderKronosForecastPanel(data)` + `destroyKronosChart()` to `app.js`
- [ ] Wire fetch inside `openTradeDrawer()` after setup-analysis resolves
- [ ] Wire `destroyKronosChart()` inside close-drawer handler
- [ ] Add pred-len toggle button listeners
- [ ] Add `view-ai-forecast` workspace tab + full-page view HTML
- [ ] Add Kronos CSS to `static/css/style.css`

---

## Performance Notes

- **Model load time:** `KronosPredictor` is large — load once at Flask startup (`app.py` module level), not per request.
- **Inference time:** At `sample_count=20`, `pred_len=10`, expect ~2–4 seconds on CPU. Run in a thread (`concurrent.futures.ThreadPoolExecutor`) so it doesn't block the Flask worker.
- **Caching:** Cache forecast results per `(ticker, pred_len, date)` key in memory (TTL = market close). No need to re-run the same forecast twice in one session.
- **GPU:** If CUDA is available, `KronosPredictor` auto-detects it. Inference drops to <500ms.
