# Spec: AI-Powered Stock Analysis with Signal Score

## Objective

Build a comprehensive **TechnicalSnapshot** analysis service that extends MomentumScan's existing MCS (Momentum Confidence Score) infrastructure with six new signal capabilities inspired by WorldMonitor's `analyze-stock.ts`. The feature targets swing traders and intraday momentum hunters on NSE India who need a single-stock deep-analysis view that goes beyond screening — delivering multi-timeframe moving average alignment, MACD cross detection, RSI multi-period classification, auto-computed support/resistance levels, composite signal scoring, risk analytics, and auto-generated stop-loss / take-profit trade levels.

### Who is the user?
Active NSE India traders who have already shortlisted a stock (via EP Screener, Bull Snort, or Watchlist) and want to drill into a **360° analysis** before entering a trade. They need:
- A clear signal verdict: **Strong Buy / Buy / Hold / Watch / Sell / Strong Sell**
- Auto-computed trade levels (stop-loss, take-profit) they can directly enter into their broker
- An LLM-generated action summary grounding the signal in news sentiment and technicals

### What does success look like?
The trader opens a stock's detail drawer (or a new dedicated analysis view), sees the TechnicalSnapshot rendered as a signal card, understands the composite signal in < 3 seconds, and can copy auto-generated SL/TP levels directly.

---

## Assumptions

```
ASSUMPTIONS I'M MAKING:
1. This builds on the existing MCS scoring pillar infrastructure — not a replacement
2. OHLCV data source is Yahoo Finance via fetch_historical_prices() + DailyBar ORM (existing)
3. AI overlay uses the existing AIService (NIM → Gemini fallback) — no new LLM vendor
4. RSI computation reuses _calculate_rsi() from app/utils/technical.py (extended for multi-period)
5. MACD uses the existing compute_macd() from app/services/scoring/fetcher_utils.py
6. Support/Resistance is computed from price action (swing highs/lows), not order book depth
7. This is a backend-first feature; frontend rendering is a separate spec
8. The new service is accessed via a dedicated API endpoint, not wired into MCS batch scoring
9. No new database model is required — results are computed on-demand and optionally cached in memory
10. Python 3.8+ only — type hints use typing module
→ Correct me now or I'll proceed with these.
```

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Language | Python 3.8+ | Type-annotated service layer |
| Framework | Flask | Existing app factory pattern |
| Data fetching | Yahoo Finance (`fetch_historical_prices`) + DailyBar ORM | Already cached with 15-min TTL |
| Technical indicators | `app/utils/technical.py`, `app/services/scoring/fetcher_utils.py` | Reuse `compute_ema`, `compute_macd`, `_calculate_rsi` |
| AI / LLM | `app/services/ai_service.py` (`AIService`) | NIM → Gemini cascade |
| Database | SQLAlchemy (SQLite dev) | Existing `db` extension; no new model for v1 |
| Testing | pytest | `tests/` directory |

---

## Commands

```bash
# Install runtime dependencies (no new dependencies required)
pip install -r requirements.txt

# Run the app locally
python run.py

# Run full test suite
pytest

# Run only signal-score tests
pytest tests/unit/test_signal_score_service.py -v

# Run coverage for new module
pytest tests/unit/test_signal_score_service.py --cov=app/services/signal_score --cov-report=term-missing
```

---

## Project Structure

```
app/
├── services/
│   └── signal_score/                    ← NEW package
│       ├── __init__.py                  ← Public API: analyze_stock(symbol) → TechnicalSnapshot
│       ├── ma_alignment.py              ← Multi-timeframe MA alignment scoring
│       ├── macd_cross.py                ← MACD golden/death cross detection
│       ├── rsi_multi.py                 ← Multi-period RSI (6, 12, 24) with classification
│       ├── volume_analysis.py           ← Volume regime classification
│       ├── support_resistance.py        ← S/R level computation from swing highs/lows
│       ├── trend_classifier.py          ← Trend status: Strong Bull → Strong Bear
│       ├── risk_analytics.py            ← Realized vol, ATR, max drawdown
│       ├── trade_levels.py              ← Auto SL/TP from signal direction + S/R
│       ├── composite_signal.py          ← Signal score aggregation → verdict
│       └── ai_overlay.py               ← LLM-powered summary with news sentiment
├── api/v1/
│   └── signal_score.py                  ← NEW endpoint: GET /api/v1/signal-score/<symbol>
tests/
└── unit/
    └── test_signal_score_service.py      ← NEW comprehensive test suite
docs/
└── specs/
    └── ai_stock_analysis_signal_score_spec.md  ← THIS FILE
```

---

## Code Style

All new code follows existing MomentumScan conventions. Example of the target coding style:

```python
"""
Multi-timeframe Moving Average alignment scoring.
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def compute_ma_alignment(
    closes: List[float],
    periods: tuple = (5, 10, 20, 60),
) -> Dict[str, Any]:
    """
    Compute SMA values and bullish/bearish alignment score.

    Args:
        closes: Daily closing prices, oldest-first.
        periods: MA periods to evaluate.

    Returns:
        Dict with 'sma_values', 'bias_pcts', 'alignment_score' (-1.0 to +1.0),
        and 'alignment_label' ("Bullish Aligned" | "Mixed" | "Bearish Aligned").
    """
    if len(closes) < max(periods):
        return _default_result()

    sma_values = {}
    for p in periods:
        sma_values[f"sma_{p}"] = sum(closes[-p:]) / p

    # ... scoring logic ...
    return result
```

**Key conventions:**
- `snake_case` for functions/variables, `PascalCase` for classes
- Type hints on all public function signatures
- Module-level `logger = logging.getLogger(__name__)`
- Docstrings on all public APIs with Args/Returns sections
- Defensive `.get(key, default)` for all dict access
- No bare `except:` — always catch specific exceptions
- Pure functions where possible; no Flask globals inside service modules

---

## Detailed Design

### Component 1: `TechnicalSnapshot` Data Structure

The central output type. All downstream consumers (API, AI overlay, frontend) work from this dict:

```python
class TechnicalSnapshot(TypedDict, total=False):
    """Complete stock analysis snapshot."""
    # Identity
    symbol: str
    exchange: str
    analysis_timestamp: str  # ISO 8601

    # Multi-timeframe MAs
    ma_alignment: MAAlignment         # SMA 5/10/20/60 values, bias %, alignment score
    
    # Trend
    trend_status: str                 # "Strong Bull" | "Bull" | "Neutral" | "Bear" | "Strong Bear"
    
    # Volume
    volume_analysis: VolumeAnalysis   # regime, rvol, classification
    
    # MACD
    macd_status: MACDStatus           # value, signal, histogram, cross type
    
    # RSI
    rsi_multi: RSIMulti               # RSI 6/12/24, classifications
    
    # Support / Resistance
    support_resistance: SRLevels      # nearest support, nearest resistance, key levels
    
    # Composite Signal
    signal_score: float               # 0.0 to 100.0
    signal_verdict: str               # "Strong Buy" | "Buy" | "Hold" | "Watch" | "Sell" | "Strong Sell"
    signal_breakdown: dict            # per-component contributions
    
    # AI Overlay
    ai_summary: str                   # LLM-generated plain-prose action plan
    ai_bull_factors: List[str]        # Key bullish drivers
    ai_risk_factors: List[str]        # Key risk items
    news_sentiment: str               # "sent-positive" | "sent-neutral" | "sent-negative"
    
    # Risk Analytics
    risk_analytics: RiskAnalyticsResult  # realized vol, ATR, max drawdown
    
    # Trade Levels
    trade_levels: TradeLevels         # auto_stop_loss, auto_take_profit, risk_reward_ratio
```

---

### Component 2: MA Alignment (`ma_alignment.py`)

**What it does:** Computes SMA values for 5, 10, 20, and 60-day periods. Calculates bias percentages (close vs each SMA). Determines alignment direction.

**Scoring:**
- **Bullish Aligned**: Close > SMA5 > SMA10 > SMA20 > SMA60 → score = +1.0
- **Bearish Aligned**: Close < SMA5 < SMA10 < SMA20 < SMA60 → score = -1.0
- **Mixed**: Partial alignment → interpolated score between -1.0 and +1.0
- **Bias %**: `(close - sma) / sma * 100` for each SMA

**Integration with existing code:** The existing `compute_swing_score()` in `technical.py` already checks `close > SMA21` and `SMA21 > SMA50`. The new module uses different periods (5/10/20/60) specifically for the signal score, avoiding collision with the MCS pillar scoring.

---

### Component 3: MACD Cross Detection (`macd_cross.py`)

**What it does:** Uses the existing `compute_macd()` from `fetcher_utils.py`. Adds cross-type detection:

- **Golden Cross**: MACD line crosses above signal line (histogram flips positive)
- **Death Cross**: MACD line crosses below signal line (histogram flips negative)
- **Approaching Golden**: Histogram negative but narrowing
- **Approaching Death**: Histogram positive but narrowing
- **Sustained Bull**: MACD above signal for 5+ consecutive bars
- **Sustained Bear**: MACD below signal for 5+ consecutive bars

**Output:**
```python
{
    "macd_line": float,
    "signal_line": float,
    "histogram": float,
    "cross_type": "golden_cross" | "death_cross" | "approaching_golden" | ... | "none",
    "bars_since_cross": int,
    "score": float  # -1.0 to +1.0
}
```

---

### Component 4: Multi-Period RSI (`rsi_multi.py`)

**What it does:** Computes RSI for periods 6, 12, and 24 using the existing `_calculate_rsi()` from `technical.py`. Classifies each:

| RSI Range | Classification |
|-----------|---------------|
| > 80 | Overbought |
| 60–80 | Bullish |
| 40–60 | Neutral |
| 20–40 | Bearish |
| < 20 | Oversold |

**Composite RSI score:** Weighted average: RSI6 (40%), RSI12 (35%), RSI24 (25%), normalized to [-1.0, +1.0].

---

### Component 5: Volume Analysis (`volume_analysis.py`)

**What it does:** Classifies today's volume action into one of six regimes:

| Regime | Condition |
|--------|-----------|
| **Heavy Up** | Price up + RVOL ≥ 1.5 |
| **Light Up** | Price up + RVOL < 1.5 |
| **Heavy Down** | Price down + RVOL ≥ 1.5 |
| **Light Down** | Price down + RVOL < 1.5 |
| **Shrink Up** | Price up + RVOL < 0.7 |
| **Shrink Down** | Price down + RVOL < 0.7 |

**RVOL Calculation:** `today_volume / mean(last_20_days_volume)`

---

### Component 6: Support/Resistance (`support_resistance.py`)

**What it does:** Identifies key S/R levels from price action using swing highs and swing lows.

**Algorithm:**
1. Use `_find_swing_highs()` and `_find_swing_lows()` from `pattern_detection.py` with window=5
2. Cluster nearby levels (within 1.5% of each other) into zones
3. Rank zones by touch count (more touches = stronger level)
4. Return nearest support (below current price) and nearest resistance (above current price)

**Output:**
```python
{
    "nearest_support": float,
    "nearest_resistance": float,
    "key_levels": [
        {"price": float, "type": "support" | "resistance", "strength": int, "touches": int}
    ],
    "price_position": float  # 0.0 (at support) to 1.0 (at resistance) within the nearest S/R band
}
```

---

### Component 7: Trend Classifier (`trend_classifier.py`)

**What it does:** Synthesizes MA alignment + MACD + RSI + price action into a discrete trend label.

| Label | Conditions |
|-------|-----------|
| **Strong Bull** | MA fully aligned bullish + MACD golden/sustained bull + RSI composite > 0.3 |
| **Bull** | MA mostly bullish (score > 0.3) + MACD not death cross |
| **Neutral** | MA alignment near zero (-0.3 to 0.3) or conflicting signals |
| **Bear** | MA mostly bearish (score < -0.3) + MACD not golden cross |
| **Strong Bear** | MA fully aligned bearish + MACD death/sustained bear + RSI composite < -0.3 |

---

### Component 8: Risk Analytics (`risk_analytics.py`)

**What it does:** Computes three risk metrics from daily OHLCV data:

1. **Realized Volatility (30d):** Annualized std deviation of log returns over the trailing 30 trading days. Formula: `σ = std(ln(close_t / close_{t-1})) × √252`

2. **ATR (14-period):** Average True Range. Uses Wilder smoothing. Provides both absolute ATR and ATR% (`ATR / close * 100`).

3. **Max Drawdown (90d):** Largest peak-to-trough decline in the trailing 90 trading days. Formula: `max_dd = min((close_t - running_peak) / running_peak)`

**Output:**
```python
{
    "realized_vol_30d": float,      # annualized, e.g. 0.35 = 35%
    "atr_14": float,                # absolute INR value
    "atr_14_pct": float,            # percentage of close, e.g. 2.5
    "max_drawdown_90d": float,      # negative decimal, e.g. -0.12 = 12% drawdown
    "risk_label": str               # "Low" | "Medium" | "High" | "Very High"
}
```

---

### Component 9: Trade Levels (`trade_levels.py`)

**What it does:** Auto-computes stop-loss and take-profit based on:
- Signal direction (buy-side vs sell-side)
- Nearest support/resistance levels
- ATR for volatility-adjusted placement

**Buy-side signal logic:**
- **Stop-Loss:** `max(nearest_support - 0.5 * ATR, close - 2.0 * ATR)`
  - Never further than 5% from close
- **Take-Profit:** `min(nearest_resistance + 0.3 * ATR, close + 3.0 * ATR)`
  - Minimum 1.5:1 reward-risk ratio enforced

**Sell-side signal logic (mirror):**
- **Stop-Loss:** `min(nearest_resistance + 0.5 * ATR, close + 2.0 * ATR)`
- **Take-Profit:** `max(nearest_support - 0.3 * ATR, close - 3.0 * ATR)`

**Output:**
```python
{
    "direction": "LONG" | "SHORT" | "NEUTRAL",
    "stop_loss": float,
    "take_profit": float,
    "risk_reward_ratio": float,    # e.g. 2.3:1
    "risk_amount_pct": float,      # % distance from close to SL
    "reward_amount_pct": float,    # % distance from close to TP
}
```

---

### Component 10: Composite Signal Score (`composite_signal.py`)

**What it does:** Aggregates all component scores into a 0–100 composite signal.

**Weighting:**

| Component | Weight | Range | Notes |
|-----------|--------|-------|-------|
| MA Alignment | 25% | -1.0 to +1.0 | Core trend indicator |
| MACD Cross | 15% | -1.0 to +1.0 | Momentum confirmation |
| RSI Multi | 15% | -1.0 to +1.0 | Mean-reversion / strength |
| Volume Analysis | 15% | -1.0 to +1.0 | Participation validation |
| Trend Classifier | 20% | -1.0 to +1.0 | Synthesis signal |
| Risk Analytics | 10% | 0.0 to +1.0 | Penalty for high risk |

**Score formula:**
```
raw = Σ(component_score × weight)                  # range: -1.0 to +1.0
normalized = (raw + 1.0) / 2.0 × 100               # range: 0 to 100
final = clamp(normalized, 0, 100)
```

**Verdict mapping:**

| Score Range | Verdict |
|-------------|---------|
| 80–100 | Strong Buy |
| 65–79 | Buy |
| 45–64 | Hold |
| 30–44 | Watch |
| 15–29 | Sell |
| 0–14 | Strong Sell |

---

### Component 11: AI Overlay (`ai_overlay.py`)

**What it does:** Uses the existing `AIService` to generate a human-readable action summary grounded in the technical snapshot data and recent news sentiment.

**Prompt structure:**
1. Feed the computed TechnicalSnapshot (signal verdict, MA alignment, MACD status, RSI, S/R levels, risk analytics)
2. Optionally include recent news sentiment from `ai_service.analyze_news_catalysts()`
3. Request structured output: `{ summary, bull_factors, risk_factors }`

**Constraints:**
- Summary: 2–4 sentences, plain prose, no markdown
- Bull factors: Max 3 bullet points
- Risk factors: Max 3 bullet points
- Falls back to template-generated summary if LLM is unavailable

---

### Component 12: API Endpoint (`app/api/v1/signal_score.py`)

```
GET /api/v1/signal-score/<symbol>
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `exchange` | string | `NSE` | Stock exchange |
| `include_ai` | bool | `true` | Include AI overlay (skip for faster response) |
| `range` | string | `6mo` | Historical data range for analysis |

**Response:** Full `TechnicalSnapshot` JSON.

**Error responses:**
- `404` — Symbol not found or no data available
- `503` — External data source unavailable (Yahoo Finance down)

**Registration:** Blueprint registered in `app/api/v1/__init__.py` alongside existing blueprints.

---

## Testing Strategy

| Test Level | Location | Coverage Target |
|-----------|----------|-----------------|
| **Unit tests** | `tests/unit/test_signal_score_service.py` | ≥ 90% for all signal_score modules |
| **Integration tests** | `tests/unit/test_signal_score_api.py` | API endpoint with mocked services |
| **Existing regression** | `pytest` (full suite) | Must not break any existing tests |

### Unit Test Cases (required):

1. **MA Alignment:**
   - Perfect bullish alignment → score = +1.0
   - Perfect bearish alignment → score = -1.0
   - Insufficient data → graceful default
   - Bias percentage calculation accuracy

2. **MACD Cross:**
   - Golden cross detection on known data
   - Death cross detection
   - "Approaching" state detection
   - Sustained bull/bear counting

3. **RSI Multi:**
   - Known RSI values match expected output
   - Classification boundaries (80, 60, 40, 20)
   - Composite score weighting

4. **Volume Analysis:**
   - Heavy Up / Heavy Down classification
   - Shrink volume detection
   - Edge case: zero volume

5. **Support/Resistance:**
   - Known swing highs/lows produce correct S/R
   - Clustering of nearby levels
   - Nearest S/R selection relative to current price

6. **Trend Classifier:**
   - Strong Bull conditions met → "Strong Bull"
   - Conflicting signals → "Neutral"
   - All bearish → "Strong Bear"

7. **Risk Analytics:**
   - Realized volatility calculation against known series
   - ATR matches manual calculation
   - Max drawdown on known declining series

8. **Trade Levels:**
   - Buy-side SL < close < TP
   - Risk-reward ratio ≥ 1.5 enforced
   - SL capped at 5% from close
   - Direction = "NEUTRAL" when signal is Hold/Watch

9. **Composite Signal:**
   - All-bullish components → score ≥ 80, verdict "Strong Buy"
   - All-bearish → score ≤ 14, verdict "Strong Sell"
   - Mixed signals → score in 45–64, verdict "Hold"
   - Score clamping at 0 and 100

10. **AI Overlay:**
    - LLM call mocked → structured output parsed correctly
    - LLM unavailable → fallback template generated
    - News sentiment integrated into prompt

11. **API Endpoint:**
    - Valid symbol → 200 + full TechnicalSnapshot
    - Unknown symbol → 404
    - `include_ai=false` → snapshot without ai_summary
    - Service error → 503

---

## Boundaries

### Always Do:
- Run `pytest` before committing
- Follow `snake_case` / `PascalCase` naming conventions
- Add type hints to all new public functions
- Use defensive `.get(key, default)` for all dict access
- Log errors via `logger.error()` — never `print()`
- Reuse existing infrastructure (`fetch_historical_prices`, `compute_macd`, `_calculate_rsi`, `AIService`, `_find_swing_highs/lows`)
- Mock all external I/O (Yahoo Finance, LLM calls) in tests
- Keep each submodule under 200 lines

### Ask First:
- Adding new Python dependencies to `requirements.txt`
- Creating a new SQLAlchemy model for caching TechnicalSnapshot results
- Changing the MCS scoring pillar weights or formula
- Modifying existing `technical.py` or `pattern_detection.py` helper signatures
- Adding new background scheduler tasks

### Never Do:
- Make real network calls in unit tests
- Modify existing MCS scoring behavior
- Store API keys in source code
- Use bare `except:` clauses
- Break existing API endpoint contracts
- Remove or modify existing test assertions

---

## Success Criteria

- [ ] `analyze_stock("RELIANCE")` returns a complete `TechnicalSnapshot` dict with all 12 top-level fields populated
- [ ] Signal score for a known strongly-trending stock (e.g., RELIANCE in a bull trend) produces "Buy" or "Strong Buy"
- [ ] Auto-computed stop-loss is always below current close for LONG signals
- [ ] Auto-computed take-profit is always above current close for LONG signals
- [ ] Risk-reward ratio is ≥ 1.5 for all generated trade levels
- [ ] AI overlay gracefully degrades to template when LLM APIs are down
- [ ] API endpoint responds in < 3 seconds (excluding LLM call time)
- [ ] Test coverage for `app/services/signal_score/` ≥ 90%
- [ ] All existing tests continue to pass (`pytest` green)
- [ ] No new runtime dependencies required

---

## Open Questions

> [!IMPORTANT]
> **Q1: Frontend integration scope.** Should the TechnicalSnapshot be rendered as an expansion of the existing MCS detail drawer, or as a standalone analysis view/page? This spec covers backend only — confirming the UI approach determines whether we need a separate frontend spec.

> [!IMPORTANT]
> **Q2: Caching strategy.** Should TechnicalSnapshot results be cached in SQLite (new model) with a TTL, or is on-demand computation with the existing `fetch_historical_prices` 15-minute cache sufficient? The per-stock computation is ~200ms (excluding AI overlay ~2s).

> [!NOTE]
> **Q3: MACD parameters.** The existing `compute_macd()` uses standard (12, 26, 9). Should we also support fast MACD (5, 13, 6) for intraday signals, or keep it simple with one set of parameters?

> [!NOTE]
> **Q4: Signal score relationship to MCS.** Should the new Signal Score be displayed alongside the existing MCS Total Score, or should it be integrated as an optional "6th pillar" in MCS? The current spec treats it as a separate, complementary analysis.
