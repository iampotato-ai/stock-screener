# MCS (Momentum Confidence Score) Implementation – Detailed Explanation  

*This document explains how the **Momentum Confidence Score (MCS)** tab works in the MomentumScan codebase, covering the frontend UI, backend scoring service, data‑fetching layer, API contract, and common migration‑related issues.*  

---  

## 1. Overview  

The MCS tab is one of the **system workspaces** displayed in the top navigation bar (under the “System” group). It presents a table of stocks scored on five core factors (Technical, Fundamental, Momentum, Institutional, Risk/Liquidity) with an optional **Swing** mode that adds a sixth factor.  

Each row shows:  

| Column | Meaning |
|--------|---------|
| **Symbol** | Ticker (e.g., `RELIANCE.NS`) |
| **Total Score** | 0‑100 composite score (higher = stronger momentum confidence) |
| **Technical** | 0‑100 score derived from price‑based indicators (RSI, MACD, ADX, SuperTrend, EMA crossovers, price‑pattern bonus). |
| **Fundamental** | 0‑100 score from valuation & health ratios (PE, PB, ROE, debt/equity, profit margins, etc.). |
| **Momentum** | 0‑100 score from short‑term price acceleration, RS‑rating, and volume spikes. |
| **Institutional** | 0‑100 score from institutional ownership, beta, and float‑shares metrics. |
| **Risk/Liquidity** | 0‑100 score from average daily volume, volatility, and liquidity ratio, and price‑range stability. |
| **Swing** *(optional)* | 0‑100 extra score that blends technical, momentum, and risk (45/45/10 weighting) – only shown when Swing mode is enabled. |
| **Badges** | Visual indicator of confidence: **HIGH** (≥ 72), **MEDIUM** (55‑71), **LOW** (< 55). |
| **Actions** | Click a row → opens a detail drawer with deep‑dive charts and raw data.  

---  

## 2. Front‑End (Static JS + HTML)  

### 2.1 Workspace Registration (`static/js/app.js`)  

```javascript
// Around line 8178‑8190
{
  id: "sys-mcs-stage2",
  name: "🧠 MCS + Stage 2",
  isSystem: true,                       // appears under the “System” workspace group
  filters: { setup: "all" },            // default filter – can be overridden by UI controls
  // Additional metadata (icon, tooltip, etc.) lives in the HTML/template
}
```

During bootstrap, `initWorkspaceTabs()` pushes this object into the global `workspaceTabs` array. When the user clicks the tab, `switchWorkspace('sys-mcs-stage2')` shows the view whose DOM root is `<div id="view-sys-mcs-stage2" class="workspace-view">`.

### 2.2 UI Markup (`templates/index.html`)  

* The table header (`#mcs-table thead`) defines clickable `<th>` elements with `data-sort` attributes that map to JSON keys (e.g., `data-sort="total_score"`).  
* The table body (`#mcs-table-body`) is populated by `renderMCS(rows)`.  
* Stat cards above the table (`.mcs-stat-card`) show aggregate counts (HIGH/MED/LOW, average score, etc.).  
* Mode toggle buttons (`#mcs-mode-classic` & `#mcs-mode-swing`) call `window.setMCSMode('classic'|'swing')`. The selected mode is persisted in `localStorage` (`mcs_scoring_mode`).  

### 2.3 Core UI Functions  

| Function | Purpose |
|----------|---------|
| `fetchMCSData(params)` | Builds a query string from UI filters (exchange, min‑score, mode, sort, order, pagination) and calls `/api/mcs/score` (or `/api/score` if the dedicated MCS blueprint is absent). Returns `{ items: [...], total, page, pages }`. |
| `renderMCS(rows)` | Iterates over `rows` (array of score objects) and creates `<tr>` elements. Each cell receives: <br>• Symbol (link to TradingView). <br>• Score cells – colour‑coded via CSS classes (`.score-high`, `.score-medium`, `.score-low`). <br>• Badges – generated from the `confidence` field. |
| `sortMCS(column)` | Updates global `mcsSort` / `mcsOrder`, then re‑invokes `fetchMCSData()` with the new sort/order. |
| `setMCSMode(mode)` | Stores mode in `localStorage`, toggles button active states, and (if switching to *Swing*) forces a re‑sort by `swing_score`. |
| `openMCSDrawer(symbol)` / `closeMCSDrawer()` | Shows/hides the fixed‑position drawer (`#mcs-drawer`). The drawer’s content is filled by `renderMCSDetail(payload)` which receives the detailed JSON from `/api/mcs/detail/<symbol>` (or the same scoring endpoint with `detail=true`). |
| `applyMCSModeUI()` | Runs on page load to reflect the saved mode. |

All UI functions gracefully handle missing data: if a field is `null` or `undefined`, a placeholder (`–`) is displayed and the score defaults to `0` (or the midpoint for the factor that cannot be computed).  

### 2.4 Styling & Icons  

* CSS block under `/* ── MCS Design System ─────────────────────────────────── */` (lines 1937‑2070 in `index.html`) defines: <br>• Tabular‑numeric fonts for score columns (`font-variant-numeric: tabular-nums`). <br>• Stat‑card layout (`.mcs-stat-card`). <br>• Score colour mapping (`.score-high` → green, `.score-medium` → amber, `.score-low` → red). <br>• Badge pill styling and hover tooltips.  
* Lucide icons (e.g., `trending-up`, `zap`) are imported via the global `initIcons()` helper; missing icons appear as fallback Unicode characters.  

---  

## 3. Back‑End  

### 3.1 API Contract  

If a dedicated blueprint exists (`app/api/v1/mcs.py`), the endpoint is:  

```
GET /api/mcs/score
```

**Query parameters**  

| Param | Description |
|-------|-------------|
| `symbol` | Single ticker (e.g., `RELIANCE`). |
| `symbols` | Comma‑separated list for batch requests (alternative to `symbol`). |
| `exchange` | `NSE` or `BSE` (default `NSE`). |
| `mode` | `classic` (default) or `swing`. |
| `page` / `limit` | Pagination (optional; defaults to page 1, limit 100). |
| `sort` / `order` | Column name and direction (defaults to `total_score DESC`). |

**Success response** (`200 OK`)  

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "symbol": "RELIANCE.NS",
        "total_score": 78.4,
        "technical_score": 82.1,
        "fundamental_score": 71.3,
        "momentum_score": 75.0,
        "institutional_score": 68.9,
        "risk_liquidity_score": 60.2,
        "swing_score": 74.5,          // present only when mode=swing
        "confidence": "HIGH",
        "badges": ["HIGH"],
        "raw": { … }                 // optional – used by the detail drawer
      }
      // … more items …
    ],
    "total": 1234,
    "page": 1,
    "pages": 13
  }
}
```

If the legacy generic scoring endpoint (`/api/score`) is used, it accepts the same parameters and returns an identical shape (the MCS tab treats it as a drop‑in replacement).  

### 3.2 Service Layer – `MomentumConfidenceScoreService` (`app/services/scoring_service.py`)  

```python
class MomentumConfidenceScoreService:
    def calculate_score_for_stock(
        self,
        symbol: str,
        exchange: str = "NSE",
        swing: bool = False,
    ) -> Dict[str, Any]:
        # 1️⃣ Pull raw market data via the fetcher
        raw = StockDataFetcher().fetch_stock_data(symbol, exchange)

        # 2️⃣ Apply sensible defaults for any missing fields
        raw = self._apply_missing_defaults(raw, symbol, exchange)

        # 3️⃣ Compute the five factor scores (0‑100 each)
        technical    = self._technical_score(raw)
        fundamental  = self._fundamental_score(raw)
        momentum     = self._momentum_score(raw)
        institutional= self._institutional_score(raw)
        risk_liq     = self._risk_liquidity_score(raw)

        # 4️⃣ Combine according to selected mode
        if swing:
            swing_score = self._swing_score(raw)          # 0‑100
            total = (
                0.30 * technical +
                0.25 * fundamental +
                0.20 * momentum +
                0.15 * institutional +
                0.10 * risk_liq
            ) * 0.9 + 0.1 * swing_score                  # 45/45/10 weighting
        else:
            total = (
                0.30 * technical +
                0.25 * fundamental +
                0.20 * momentum +
                0.15 * institutional +
                0.10 * risk_liq
            )

        # 5️⃣ Derive confidence badge from total score
        confidence = self._confidence_from_total(total)

        # 6️⃣ Build payload for the frontend
        return {
            "symbol": symbol,
            "total_score": round(total, 2),
            "technical_score": round(technical, 2),
            "fundamental_score": round(fundamental, 2),
            "momentum_score": round(momentum, 2),
            "institutional_score": round(institutional, 2),
            "risk_liquidity_score": round(risk_liq, 2),
            "swing_score": round(swing_score, 2) if swing else None,
            "confidence": confidence,          # "HIGH"/"MEDIUM"/"LOW"
            "badges": self._badge_list(confidence),
            "raw": raw                         # optional deep‑dive data
        }
```

*The helper methods (`_technical_score`, `_fundamental_score`, …) each read a handful of fields from `raw` (e.g., RSI, MACD histogram, PE, debt‑to‑equity, institutional ownership %, average daily volume, beta, volatility, etc.) and map them to a 0‑100 scale via piece‑wise linear functions or lookup tables. Implementation details are available in the source file.*  

### 3.3 Data Fetcher – `StockDataFetcher` (`app/services/scoring/fetcher.py`)  

| Source | Method | Fields Provided | Used In |
|--------|--------|----------------|--------|
| **Yahoo Finance OHLCV** | `_fetch_yahoo_ohlcv(symbol)` | `open, high, low, close, volume` (daily, up to 2 years) | Technical indicators (EMA, MACD, ADX, SuperTrend, RSI, ATR, volume‑based metrics) |
| **Yahoo Fundamentals** | `_fetch_yahoo_fundamentals(symbol)` | `trailingPE, forwardPE, priceToBook, debtToEquity, returnOnEquity, profitMargins, …` | Fundamental score |
| **Yahoo Info dict** | `info` from `yfinance.Ticker(symbol).info` | `sharesOutstanding, floatShares, heldPercentInstitutions, beta, averageVolume, …` | Institutional & Risk/Liquidity |
| **Technical Utilities** | `fetcher_utils.py` (EMA, MACD, ADX, SuperTrend, volatility, etc.) | Derived series & latest values | Technical score |
| **Pattern Classification** | `technical.classify_technical_pattern(history)` | String like `"Bullish Engulfing"` or `None` | Small pattern bonus added to technical score |

If any of these calls raise an exception (network error, HTTP 401/403, missing data), the fetcher returns a **partial dictionary** and the scoring service runs `_apply_missing_defaults()` to fill in safe fallbacks (e.g., RSI = 50, PE = 0, beta = 1, volume = 0). This prevents a total crash but will push the factor scores toward the centre – a frequent symptom after a migration when a new dependency is broken or a proxy blocks Yahoo/TV access.  

### 3.4 Background Jobs (Optional)  

The MCS calculation itself is **on‑demand** (triggered by the UI request). No periodic APScheduler job is required for the score itself, but the project may still run:  

* `ep_refresh_job` – updates the underlying OHLCV/fundamentals tables used indirectly by the fetcher (if the fetcher is configured to read from the internal `daily_bars`/`fundamentals` tables rather than Yahoo).  
* `ep_model_training` – unrelated to MCS but shares the same scheduler.  

---  

## 4. How a New IPO Gets Updated Automatically  

When a new main‑board IPO appears on NSE/BSE:  

1. **Nightly/Ingestion Job** (`legacy_routes.py → seed_ipo_listings()`) pulls the NSE *public‑past‑issues* API, filters for listings within the last ~18 months, and inserts rows into `ipo_listings` (and mirrors them for BSE).  
2. The **IPO metrics refresh** (`app/services/ipo_service.py → IPOService.refresh_ipo_metrics()`) runs hourly (APScheduler). For each ticker in `ipo_listings` it fetches up to 2 years of OHLCV, computes `listing_gain_pct`, `current_vs_issue_pct`, `rvol_ratio`, `swing_score`, `momentum_phase`, etc., and writes/updates a row in `ipo_metrics_cache`.  
3. The **MCS scoring service** does **not** read directly from `ipo_metrics_cache`; instead, when a user requests the MCS tab (or a detail view), the `StockDataFetcher` pulls the **latest OHLCV** from Yahoo Finance (or the internal `daily_bars` table if the fetcher is wired to the DB). Because the OHLCV table is refreshed by the nightly ETL pipelines, any new IPO will have its price/volume data available within a few minutes of market open, and the MCS score will reflect that fresh data on the next UI request.  

Thus, the pipeline that keeps the IPO list current also ensures the pricing data needed by MCS stays up‑to‑date, without any extra coupling.  

---  

## 5. Common Migration Pitfalls & How to Diagnose Them  

| Symptom | Likely Cause | Where to Look / Fix |
|---------|--------------|---------------------|
| **MCS tab missing from workspace list** | Feature flag disabled or tab object removed/renamed. | Verify `app/config.py` (or `.env`) contains `ENABLE_MCS = True` (or `MCS_ENABLED = True`). Check `static/js/app.js` for the `{ id:"sys-mcs-stage2", … }` entry in `workspaceTabs`. |
| **Tab shows “Loading…” forever, then toast error** | Network request to `/api/mcs/score` (or `/api/score`) returns 404/500 or malformed JSON. | Open DevTools → Network → filter “xhr”. Reload the MCS tab and inspect the request: <br>• **404** → route missing → ensure the MCS blueprint is registered in `app/api/v1/__init__.py` or that the fallback `/api/score` route exists. <br>• **500** → check server console/log for the traceback (most often an import error, e.g., `ModuleNotFoundError: No module named 'yfinance'`). |
| **Response 200 but table empty** | JSON shape changed (e.g., `data.items` missing, or field names differ). | In Network tab, click the response and compare with what `renderMCS()` expects: an array under `data.items` (or `data` if not paginated) where each object has at least `symbol`, `total_score`, `confidence`. Adjust either the backend response or the frontend parsing (`fetchMCSData`). |
| **All scores are 0 or ≈ 50 (default values)** | Fetcher could not retrieve real data → fallbacks used, pulling every factor toward the midpoint. | Inspect the `raw` field inside a returned item (the API includes it when `detail=true` or you can log it). If you see many `null` or zeros (e.g., `close:0`, `volume:0`, `pe:0`), the data source is broken. <br>• Confirm `yfinance` (or `pandas`, `numpy`) is installed (`pip install -r requirements.txt`). <br>• Verify no corporate proxy blocks `https://query1.finance.yahoo.com`. <br>• If you switched to a paid provider (Tiingo, IEX Cloud), ensure the API key is set in environment variables and the fetcher is updated accordingly. |
| **Swing mode shows no extra column or swing score always null** | Backend ignores `swing` flag or `_swing_score()` missing/returns `None`. | Check the network request URL for `&mode=swing`. In `MomentumConfidenceScoreService.calculate_score_for_stock`, ensure the `if swing:` block executes and that `_swing_score()` returns a float 0‑100. Add logging or a breakpoint if necessary. |
| **Sorting / pagination broken** | UI expects a certain key name (e.g., `total_score`) but API uses a different field (`score` or `pts`). | Compare the `data-sort` attribute in `<th>` (e.g., `data-sort="total_score"`) with the actual key in the JSON objects. Rename either side to match. |
| **Drawer does not open or shows “No data”** | Detail endpoint (`/api/mcs/detail/<symbol>`) missing or returns error. | Click a row → DevTools → Network → look for request to `/api/mcs/detail/<RELIANCE>` (or `/api/score?symbol=RELIANCE&detail=1`). Ensure it returns a JSON with deep‑dive sections (technical, fundamental, etc.). |
| **Styling looks off (missing colours, badge not showing)** | CSS/JS changes removed classes used by the MCS table (`.mcs-stat-card`, `.badge`, `.score-high`, etc.) or Lucide icons failed to load. | Inspect a score cell in the Elements tab – does it have the expected class? Look at the `<style>` block under “MCS Design System” in `templates/index.html`. If missing, re‑add the CSS or verify the base CSS file (`static/css/app.css`) is still loaded. |
| **Console shows “ReferenceError: fetchMCSData is not defined”** | Function renamed, moved, or script bundle failed to load (new build step omitted the file). | Verify `static/js/app.js` still contains `fetchMCSData`, `renderMCS`, `sortMCS`, `setMCSMode`, `openMCSDrawer`, `closeMCSDrawer`. If you split the JS into multiple bundles, ensure the MCS‑related bundle is included in the base template (`<script src="{{ url_for('static', filename='js/mcs.js') }}"></script>`). |
| **Server logs: “ModuleNotFoundError: No module named 'yfinance’”** | Dependency added but not installed in the deployed environment. | Run `pip install -r requirements.txt` (or the equivalent for your deployment) and confirm `yfinance`, `pandas`, `numpy` are present. |
| **Data appears stale** | Internal cache layer (if added) not invalidated after background refresh. | Look for `@cache.memoize` decorators on the scoring endpoint. If present, ensure TTL is appropriate or add a cache‑busting query param (`?_ts=${Date.now()}`) to the AJAX call. |

### Quick Diagnostic Checklist  

1. **DevTools → Console** – fix any red errors first.  
2. **Network tab** – reload the MCS tab, find the XHR to `/api/mcs/score` (or `/api/score`). Check status and JSON shape.  
3. If JSON looks correct → temporarily add `console.log('MCS rows', rows);` inside `fetchMCSData()` to confirm you’re receiving data.  
4. If data but table empty → verify the DOM selector (`#mcs-table-body`) exists and that `renderMCS()` is actually called.  
5. If scores all default → inspect one object’s `raw` field; if many zeros/nulls, test the fetcher directly:  

   ```python
   from app.services.scoring.fetcher import StockDataFetcher
   f = StockDataFetcher()
   print(f.fetch_stock_data('RELIANCE', 'NSE'))
   ```  

   (run inside a Flask shell or a temporary script).  

6. Confirm any feature flags (`ENABLE_MCS`, `MCS_ENABLED`) are set to `True`.  

After fixing the backend or frontend issue, do a **hard refresh** (Ctrl + F5) to clear any cached service‑worker or bundled‑JS assets, then verify the tab works again.  

---  

## 6. File‑by‑File Summary (for quick reference)

| File / Path | Responsibility |
|-------------|----------------|
| `templates/index.html` | HTML structure, CSS (MCS Design System), placeholder containers for the table, stat‑cards, drawer, mode toggle. |
| `static/js/app.js` | Workspace tab registration, UI event handlers (`fetchMCSData`, `renderMCS`, `sortMCS`, `setMCSMode`, `openMCSDrawer`, `closeMCSDrawer`), localStorage handling for mode, AJAX calls to the API. |
| `app/api/v1/mcs.py` *(if present)* | Flask blueprint exposing `/api/mcs/score` (and optionally `/api/mcs/detail/<symbol>`). Delegates to `MomentumConfidenceScoreService`. |
| `app/api/v1/__init__.py` | Registers the MCS blueprint (or ensures the generic `/api/score` route is available). |
| `app/services/scoring_service.py` | Core scoring logic – five factor calculations, mode handling, confidence/badge generation. |
| `app/services/scoring/fetcher.py` | `StockDataFetcher` – pulls OHLCV, fundamentals, info from Yahoo Finance (or internal DB), computes technical indicators, applies fallbacks. |
| `app/services/scoring/fetcher_utils.py` | Helper functions (EMA, MACD, ADX, SuperTrend, volatility, etc.) used by the fetcher. |
| `app/models.py` *(optional)* | If the fetcher reads from internal tables, the relevant models are `DailyBar`, `Fundamental`, `CorporateEvent`, etc. (not required for the default Yahoo‑based fetcher). |
| `app/config.py` | Feature flag (`ENABLE_MCS = True/False`) and any tuning parameters (e.g., `MCS_DEFAULT_LIMIT`, `MCS_SWING_WEIGHTS`). |
| `app/tasks/scheduler.py` | Background jobs that keep OHLCV/fundamentals fresh (e.g., `ep_refresh_job`). Not directly part of MCS but essential for up‑to‑date data. |
| `scripts/smoke_test_mcs.py` | Simple script to instantiate the service and print scores for a few tickers – useful for verifying the backend after a migration. |

---  

## 7. Closing Note  

The MCS tab is deliberately **loosely coupled**: the UI only needs a JSON endpoint that returns a predictable set of fields; the heavy lifting (data acquisition, indicator calculation, scoring) lives entirely in the Python service layer. When you migrate the codebase (change dependencies, reorganise modules, or switch data providers), **just verify two things**:

1. **The API contract** (`/api/mcs/score` or `/api/score`) still returns the shape the frontend expects.  
2. **The data fetcher** can successfully retrieve raw market data (OHLCV, fundamentals, info) for the symbols you care about.  

If both hold, the MCS tab will render correctly, show accurate scores, and update automatically as new IPOs or price data arrive.  

---  

*End of document.*