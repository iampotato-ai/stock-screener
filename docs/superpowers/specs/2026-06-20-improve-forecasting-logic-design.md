# Improve Forecasting Logic – Balanced Bias Distribution

**Date:** 2026‑06‑20

---

## 1. Context & Motivation
The Momentum Scan UI shows an AI‑driven forecast panel (Kronos) that currently skews heavily toward a **down‑trend bias**. Users report that most stocks appear to be in “Strong Downtrend” or “Bearish Pressure” even when market conditions are neutral or bullish. The forecasting pipeline lives in `app/utils/forecast_math.py` and produces a `weighted_score` from five normalized metrics (`s1`‑`s5`). The final bias label is chosen via static cut‑offs.

## 2. Current Implementation Summary
- **Metrics:** `s1` (endpoint return), `s2` (momentum split), `s3` (consistency), `s4` (breakout flag), `s5` (max drawdown).
- **Weights:** `[0.30, 0.25, 0.20, 0.15, 0.10]` (hard‑coded).
- **Bias Mapping:**
  - `> 0.40` → *Strong Breakout*
  - `> 0.15` → *Bullish Continuation*
  - `> -0.15` → *Sideways Consolidation*
  - `> -0.40` → *Bearish Pressure*
  - otherwise → *Strong Downtrend*
- **Confidence:** Derived from `weighted_score` magnitude and a flat‑forecast flag.
- **Performance:** Pure CPU, linear over the forecast horizon (≈ 5‑10 days). No GPU required.

## 3. Issues Observed
- The static weight vector over‑emphasises `s1` (endpoint return) which, given recent market volatility, often yields negative `weighted_score`.
- No volatility‑aware signal to counteract persistent bearish momentum.
- Fixed cut‑offs produce an **unbalanced label distribution** (≈ 50 % down‑trend labels on recent data).

## 4. Design Goals
1. **Balanced bias distribution** – target ~20 % per label over a rolling window of recent forecasts.
2. **CPU‑only** – keep runtime identical to the current pipeline (no GPU, O(N) per ticker).
3. **Minimal code churn** – changes confined to `forecast_math.compute_forecast_metrics` and a small config section.
4. **Observability** – emit the new signal and the final percentile bucket for debugging.

## 5. Proposed Solution (combined A + B + C)
### 5.1 Re‑weight existing metrics (Approach A)
- Reduce `s1` weight from **0.30** → **0.20**.
- Increase `s3` (consistency) and `s4` (breakout) to **0.25** each.
- Keep `s2` at **0.20** and `s5` at **0.10**.
- New weight vector: **[0.20, 0.20, 0.25, 0.25, 0.10]**.
- Rationale: dampen endpoint‑return dominance, give more influence to consistency and breakout signal.

### 5.2 Add ATR volatility signal `s6` (Approach B)
- Compute 14‑day ATR % via existing `compute_atr_pct` (already in the module).
- Normalise `s6 = _norm(atr_pct, 0, 5)` where a higher ATR indicates higher volatility.
- Incorporate with weight **0.10** (total weight now 1.10; we will renormalise by dividing the sum of weighted scores by 1.10).
- This adds negligible CPU cost (single pass over the last 14 days of `history`).

### 5.3 Percentile‑based bias mapping (Approach C)
- After computing `weighted_score` (including `s6`), store it in a circular buffer of the **most recent 500 scores** (in‑memory, per‑process).
- When mapping to a bias label, compute the score’s percentile within that buffer.
- Map percentiles to labels in equal 20 % buckets:
  - **80‑100 %** → *Strong Breakout*
  - **60‑80 %** → *Bullish Continuation*
  - **40‑60 %** → *Sideways Consolidation*
  - **20‑40 %** → *Bearish Pressure*
  - **0‑20 %** → *Strong Downtrend*
- This guarantees an approximately balanced distribution regardless of raw score shape.

## 6. Data Flow Changes
1. In `compute_forecast_metrics`:
   - Call `compute_atr_pct(history, window=14)` → `atr_pct`.
   - Normalise to `s6` using `_norm` helper.
   - Apply new weight vector (including `s6`).
   - After the weighted sum, **clip** to [-1, 1] and **renormalise** by dividing by the sum of weights (1.10).
2. Store the final `weighted_score` in a module‑level `deque(maxlen=500)`.
3. Replace the static `if weighted_score > …` block with a percentile lookup (`np.percentile(buffer, [20,40,60,80])`).
4. Emit `"percentile": <pct>` in the returned `forecast_metrics` for UI debugging.

## 7. Configuration
- New constants in `forecast_math.py`:
  ```python
  METRIC_WEIGHTS = {
      "s1": 0.20,
      "s2": 0.20,
      "s3": 0.25,
      "s4": 0.25,
      "s5": 0.10,
      "s6": 0.10,
  }
  PERCENTILE_BUFFER_SIZE = 500
  ```
- All constants are easy to tweak via a future feature‑flag; the initial values are committed.

## 8. Performance Considerations
- **CPU:** One extra loop over 14 days of history (O(14) ≈ constant) and a `deque` append; negligible impact (< 0.5 ms per ticker on typical hardware).
- **Memory:** `deque(500)` of floats (~4 KB) – trivial.
- No third‑party dependencies are added.

## 9. Testing & Validation
1. **Unit tests** – add tests to `tests/test_forecast_math.py`:
   - Verify that `s6` is computed correctly from a known history.
   - Simulate a series of calls with synthetic scores to confirm that the percentile mapping yields the expected label distribution (≈ 20 % per bucket).
   - Ensure the total weight sum normalises to 1.0 and the `weighted_score` stays within [-1, 1].
2. **Heuristic validation** – in CI, run a quick simulation over the last 30 days of real data and assert that the bias label histogram is within ±5 % of the target distribution.
3. **Performance benchmark** – add a micro‑benchmark in `scripts/run_performance_tests.py` that measures the per‑ticker latency before and after the change; assert the increase is < 5 %.

## 10. Migration Plan
- **Feature flag** `ENABLE_PERCENTILE_BIAS` (default `True`).
- Deploy the new code behind the flag; monitor the UI label distribution for one full market day.
- If any regression is observed, toggle the flag off to revert to the static mapping.

## 11. Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Percentile bucket drift if buffer size too small | Labels could become temporarily unbalanced | Use a 500‑entry buffer (≈ 2 hours of forecasts) and reset on server restart – safe for short‑term fluctuations. |
| New `s6` may over‑emphasise volatility in quiet markets | Could produce false bullish bias | Weight `s6` is modest (0.10) and normalised; includes a clipping step to keep extremes in check. |
| Code change may break downstream consumers expecting `forecast_metrics` shape | UI could error | Add `"percentile"` key as optional; UI already guards missing keys. |

---

**Next steps** – after you approve this spec, I will run the self‑review, commit the document, and hand it over for your final review before we create an implementation plan.
