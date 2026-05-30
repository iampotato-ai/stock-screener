# Code Review: Kronos AI Prediction Panel

> **Branch:** `feature/workspace-ui`  
> **Commits reviewed:** `Kronos AI Prediction Panel update` + `Kronos update`  
> **Files reviewed:** `app.py`, `model/kronos.py`, `static/js/app.js`, `static/css/style.css`, `templates/index.html`  
> **Reviewed on:** 2026-05-30

---

## 🔴 Bugs / Correctness Issues

### 1. Duplicate `except` block in `backtest_summary`
At the end of the `backtest_summary` route, there are **two identical `except Exception as e` blocks** — the second one is orphaned dead code with no matching `try`. Python will never enter it, but it's a copy-paste mistake that should be removed.

```python
# BUG: second except is unreachable / orphaned
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    except Exception as e:   # <-- remove this
        return jsonify({"error": str(e)}), 500
```

---

### 2. `_get_kronos_cache` silently drops `forecast_metrics` on old cache entries
The guard `entry[4] if len(entry) > 4 else {}` handles stale cache entries from a previous app version, but does so silently. Add a log so you know when this migration fallback triggers:

```python
def _get_kronos_cache(ticker):
    entry = _kronos_cache.get(ticker)
    if entry and (_time.time() - entry[0]) < _KRONOS_TTL:
        if len(entry) <= 4:
            print(f"[Kronos Cache] Old cache entry for {ticker} — metrics unavailable")
        return entry[1], entry[2], entry[3], entry[4] if len(entry) > 4 else {}
    return None
```

---

### 3. `cup_idx` calculation in `classify_technical_pattern` is fragile
```python
cup_idx = highs[-70:-25].index(cup_left_high) + (len(highs) - 70)
```
`.index()` on a list slice returns a 0-based index within that slice. Adding `len(highs) - 70` to reconstruct the absolute position is fragile — if `len(highs)` == 70 exactly, `cup_idx` becomes 0, and `lows[0:-12]` spans almost the entire list (wrong cup bottom). Use explicit absolute indexing instead:

```python
# Safer approach
slice_start = len(highs) - 70
local_idx = highs[slice_start:-25].index(cup_left_high)
cup_idx = slice_start + local_idx
```

---

## 🟡 Design / Performance Issues

### 4. `compute_extra_fields` synthesizes fundamental data using `hash(ticker) % 100`
Fields like `sales_cagr`, `revenue_growth_yoy`, `wc_intensity`, `segment_growth`, and `ebitda_cagr` are **pseudo-random numbers derived from the ticker's hash**, not real data. These get displayed on the frontend as real metrics, which is highly misleading for trading decisions.

**Fix options:**
- Return `null` for all simulated growth fields and show "N/A" on the frontend, OR
- Add a flag `stock["growth_data_source"] = "simulated"` so the frontend can display a clear disclaimer badge

---

### 5. `populate_screener_intelligence` fires 50 Yahoo Finance requests with `max_workers=25`
Under load (repeated scans), this can trigger Yahoo Finance rate-limiting (HTTP 429), all of which silently fall back to "Trend Continuation". Consider:
- Reducing `max_workers` to **5–8**
- Adding a per-ticker in-memory cache with a **15-min TTL** before the parallel fetch
- Logging the failure count so you can observe the error rate

---

### 6. ATR% calculation is duplicated in 3 places
The same 14-day ATR% loop appears verbatim in:
- `get_setup_analysis`
- `get_kronos_forecast`
- `get_kronos_backtest`

Extract it into a helper function to avoid drift between the three copies:

```python
def compute_atr_pct(history, window=14):
    """Compute ATR as % of last close over `window` trading days."""
    if len(history) < window + 1:
        return 5.0  # default fallback
    tr_list = []
    for i in range(len(history) - window, len(history)):
        h_val = float(history[i]["high"])
        l_val = float(history[i]["low"])
        p_close = float(history[i-1]["close"])
        tr = max(h_val - l_val, abs(h_val - p_close), abs(l_val - p_close))
        tr_list.append(tr)
    atr = sum(tr_list) / window
    curr_close = float(history[-1]["close"])
    return (atr / curr_close) * 100 if curr_close > 0 else 5.0
```

---

### 7. `get_kronos_forecast` DB cache check compares against last Yahoo Finance date
```python
if gen_date == last_date_str:  # last_date_str = history[-1]["date"] from Yahoo
```
If Yahoo Finance lags by a day (common on weekends/holidays), the DB entry is never reused and Kronos re-runs every time. Use today's actual date instead:

```python
today_str = datetime.now().strftime('%Y-%m-%d')
if gen_date == today_str:
```

---

### 8. In-memory `_kronos_cache` dict is unbounded — slow memory leak
Every unique ticker that runs through Kronos is added to `_kronos_cache` and **never evicted** (TTL only stops reads, not growth). On a long-running server scanning hundreds of tickers, this will slowly grow. Cap it with an LRU cache:

```python
from collections import OrderedDict

_MAX_KRONOS_CACHE = 200

def _set_kronos_cache(ticker, bias, score, forecast_list, forecast_metrics):
    if len(_kronos_cache) >= _MAX_KRONOS_CACHE:
        _kronos_cache.popitem(last=False)  # evict oldest
    _kronos_cache[ticker] = (_time.time(), bias, score, list(forecast_list), dict(forecast_metrics))

# Change _kronos_cache declaration to:
_kronos_cache = OrderedDict()
```

---

## 🟢 Minor / Style

### 9. `fetch_google_news` — `dt` variable referenced before guaranteed assignment
```python
'_dt': dt if 'dt' in locals() else datetime.datetime.min...
```
Using `locals()` as a safety check is fragile. If the `parsedate_to_datetime` call raises on the very first article, `dt` is never set. Initialize `dt` before the `try` block:

```python
dt = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)  # safe default
if pub_date:
    try:
        dt = parsedate_to_datetime(pub_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        if (now_utc - dt).days > 30:
            continue
    except Exception:
        pass
```

---

### 10. `app.py` is ~1700 lines with all concerns in one file
Routes, DB helpers, scraping, scoring logic, and ML inference are all mixed together. As Kronos, RRG, breadth, and journal features grow, this will become difficult to maintain. Consider splitting into Flask Blueprints:

```
routes/
  screener.py     # /api/scan, /api/save_snapshot
  kronos.py       # /api/setup-analysis, /api/kronos-forecast, /api/kronos-backtest
  watchlist.py    # /api/watchlist/*
  journal.py      # /api/journal/*
  market.py       # /api/announcements, /api/events, /api/deals, /api/news
  breadth.py      # /api/breadth-snapshot, /api/breadth-history
```

---

### 11. NSE 2026 holidays list is marked "preliminary"
```python
# 2026 holidays (preliminary)
"2026-01-26", "2026-03-03", ...
```
A hardcoded preliminary list will cause Kronos forecast dates to skip incorrect days. Fetch dynamically once per session from the NSE API:

```python
# NSE trading holiday API
url = "https://www.nseindia.com/api/holiday-master?type=trading"
```
Cache the result for the day and fall back to the static list on failure.

---

## Summary

| # | Severity | Issue |
|---|----------|-------|
| 1 | 🔴 Bug | Duplicate `except` block in `backtest_summary` |
| 2 | 🔴 Bug | Silent cache metrics drop with no log |
| 3 | 🔴 Bug | Fragile `cup_idx` calculation in Cup & Handle pattern |
| 4 | 🟡 Design | Simulated fundamental data shown as real metrics |
| 5 | 🟡 Perf | Yahoo Finance rate-limit risk from 25 concurrent threads |
| 6 | 🟡 Design | ATR% logic duplicated in 3 routes |
| 7 | 🟡 Bug | Kronos DB cache check uses Yahoo date, not today's date |
| 8 | 🟡 Perf | Unbounded `_kronos_cache` dict — memory leak |
| 9 | 🟢 Minor | `dt` referenced before assignment in news fetch |
| 10 | 🟢 Minor | `app.py` should be split into Blueprints |
| 11 | 🟢 Minor | NSE 2026 holidays list is preliminary / hardcoded |
