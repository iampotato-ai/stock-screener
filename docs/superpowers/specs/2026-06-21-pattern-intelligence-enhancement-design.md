# Pattern‑Intelligence Heuristics Tightening Design

**Goal** – Reduce false‑positives/negatives in the existing candlestick and chart‑pattern detectors while keeping the public API unchanged. All changes stay inside `app/utils/pattern_detection.py` and its test suite.

---
## 1. High‑level approach
| Aspect | Change | Rationale |
|--------|--------|-----------|
| Separate trend flags | Introduce `is_uptrend` and `is_downtrend` *per‑candle* instead of sharing a single variable. | Prevents bullish engulfing from inheriting a previous down‑trend flag (Bug #1). |
| Hammer / Shooting Star | Require a clear down‑trend (`is_downtrend = c1 < c0 and c1 < c2`) **and** a lower‑shadow > 2 × real‑body. | Tightens detection to true reversal bars. |
| Engulfing | Use fresh trend flags; bullish engulfing needs `c1 > c0` **and** `c1 - o1 >= (o0 - c0) * 1.0`, bearish analogous. | Removes cross‑contamination (Bug #1). |
| Morning / Evening Star gaps | Replace `max(o1, c1) < c2` with `max(o1, c1) < min(o2, c2)` (and mirrored for Evening Star). | Correct reference to the body of the prior candle (Bug #3). |
| Doji on zero‑range candles | If `range0 < 1e-5` treat the candle as *no‑data* and skip pattern emission; otherwise require `body0 / range0 <= 0.1` **and** `range0 > 1e-5`. | Stops every zero‑move candle being labelled Doji (Bug #4). |
| Double‑Top / Double‑Bottom tolerance | Change default `tolerance` from `0.03` (3 %) to `0.01` (1 %). Make it a module‑level constant `DOUBLE_TOLERANCE = 0.01`. | NSE intraday swings are tighter; prevents spurious double‑top signals (Bug #2). |
| Volatility Contraction Pattern (VCP) | Raise `min_contractions` default from `2` to `3`. Add a constant `VCP_MIN_CONTRACTIONS = 3`. | Requires a more sustained contraction before signalling (Bug #5). |
| Config constants | Group all tunable values (`DOUBLE_TOLERANCE`, `VCP_MIN_CONTRACTIONS`, `ENGULFING_BODY_RATIO`, etc.) in a dedicated `PATTERN_CONFIG` dict at the top of the file. | Makes future tuning explicit and testable. |
| Documentation | Update module docstring to list the new constants and tightened criteria. Add inline comments where logic changed. | Improves maintainability. |
| Unit‑test coverage | Add tests that specifically cover the edge cases fixed: Engulfing with mixed trend flags, Morning/Evening Star gap check, Zero‑range Doji suppression, Double‑Top/Bottom with 2 % vs 1 % tolerance, VCP requiring 3 contractions. | Guarantees regressions are caught. |
| Backward compatibility | Public function signatures stay the same; only detection thresholds change. Existing callers (Kronos, UI) receive more accurate `candle_results` and `chart_results`. No breaking changes. |

---
## 2. File‑level changes
| File | Changes |
|------|---------|
| `app/utils/pattern_detection.py` | • Add `PATTERN_CONFIG` dict with new defaults.<br>• Refactor hammer/engulfing sections to compute fresh `is_uptrend`/`is_downtrend` per iteration.<br>• Update gap checks for Morning/Evening Star.<br>• Guard zero‑range candles before Doji logic.<br>• Replace hard‑coded tolerances with `PATTERN_CONFIG` values.<br>• Adjust VCP call to use new `VCP_MIN_CONTRACTIONS`. |
| `tests/test_pattern_detection.py` | • New test cases for each tightened rule (as listed above).<br>• Adjust existing tests if they relied on previous looser thresholds. |
| `docs/superpowers/specs/2026-06-21-pattern-intelligence-enhancement-design.md` | This design document. |

---
## 3. Acceptance criteria
1. **Functional** – All existing tests still pass **and** the new tests added for the tightened heuristics pass.
2. **No regression** – Running the full app (`flask run`) still produces a populated scan UI; no new exceptions appear.
3. **Accuracy check** – Manual inspection of a sample of recent scans shows a noticeable drop in spurious Hammer/Doji signals and more sensible Engulfing and Star patterns.
4. **Configuration** – Changing a value in `PATTERN_CONFIG` (e.g., `DOUBLE_TOLERANCE`) immediately affects detection without code changes elsewhere.

---
## 4. Open items
* None – the design is self‑contained.

---
*Spec written and ready for review.*