# Spec: EP Screener Trader Workflow Upgrade

## Status

Proposed — implementation must begin only after this specification is approved.

## Objective

Upgrade the Episodic Pivot (EP) screener from an event-and-volume ranking list into an auditable trader workflow for NSE/BSE swing setups. The product must help a trader answer four questions quickly:

1. Is the catalyst material, timely, and verifiable?
2. Has the market accepted the catalyst through constructive price and volume action?
3. Is the stock executable with a defined entry, invalidation level, and position size?
4. Does the historical evidence support this setup type in the current market context?

The feature supports research and trade planning; it does not provide investment advice or guarantee outcomes.

## Assumptions

- The existing Flask application, SQLite development database, SQLAlchemy models, vanilla JavaScript UI, and APScheduler workflow remain in use.
- Phases 1–2 use existing TradingView, NSE announcement, Yahoo Finance, and local OHLCV sources. Any paid data provider requires a separate approval.
- Long EPs are the default workflow. Short EPs remain informational until the symbol is verified as F&O eligible and the user explicitly enables short candidates.
- The current `ep_features` and `ep_watchlist` records are historical data and must not be destructively rewritten.
- Existing `/api/ep/*` behaviour remains backward compatible while new fields are added.

## Current-State Constraints

- Discovery currently requires relative volume of at least 3x and deep-enriches only the top 40 candidates.
- The scorer has both a rules fallback and an XGBoost model. The model is presently trained to replicate the rules target, not a clean realized-return target.
- An active watchlist entry currently has its stop refreshed from the latest daily low. This must be corrected before relying on stored risk metrics.
- Catalyst, price, and model data can be incomplete. Every trader-facing result needs freshness and coverage metadata.

## Approved Product Decisions

### Risk defaults

Ship an editable, conservative risk template: 0.5% account risk per trade, five concurrent positions, 2.5% aggregate initial account risk, two positions per sector/theme, and 20% maximum exposure in one position. These are safety defaults, not personalised trading advice. The user may change them; the system must not calculate a quantity without an explicit account-risk setting.

### Authoritative market data

- Delivery percentage: daily NSE security-wise delivery/equity reports.
- F&O eligibility: NSE's daily Equity Derivatives underlyings/contracts data; never infer eligibility from a static symbol list.
- Surveillance: NSE ASM/GSM lists and notices, with BSE equivalents checked for dual-listed securities.
- Free float: an estimate derived from the latest NSE shareholding-pattern filing (public shareholding × paid-up shares). Show its filing date and never describe it as real-time free float.

The ingestion layer must store source URL, published/observed time, effective trading date, fetch time, and source status for each value.

### Catalyst overrides

Only administrators or authorised research analysts may change the shared catalyst classification/materiality. All users may create private notes or submit a correction request. Every approved override preserves the original extraction and records value, reason, evidence URL, actor, reviewer, and timestamps.

### Release scope

The first trader release is EOD-only. Phase 3 may define intraday-compatible contracts, but VWAP/opening-range signals remain disabled until a reliable minute-bar source, announcement timestamps, and independent intraday backtest are available.

### EP-to-journal ownership

The EP episode is the canonical source for signal facts: catalyst, score/version, original EP-day levels, thesis, and proposed plan. `TradeJournal` is the canonical source for execution facts: entry, stop, targets, quantity, status, exits, P&L, and realised R. Link them with a non-null `ep_episode_id`/`source_signal_id`; journal creation copies an immutable signal snapshot and never rewrites the episode.

## Commands

```powershell
# Run EP unit/integration coverage
pytest tests/test_ep_screener.py tests/test_ep_scoring_model.py tests/test_phase3_delayed_ep.py tests/test_phase4_backtest.py -q

# Run all backend tests
pytest

# Run EP-related browser checks after Playwright is installed
python -m pytest -q e2e/tests/test_ep_view.py

# Train only after Phase 4 acceptance criteria and a reviewed dataset are available
python scripts/train_ep_scoring_model.py
```

## Project Areas

| Area | Primary locations |
|---|---|
| EP rules and queries | `app/services/ep_service.py` |
| EP API | `app/api/v1/ep.py`, `app/api/v1/ep_watchlist.py` |
| Legacy EP pipeline/backtest | `app/api/v1/legacy_routes.py` |
| Persistence | `app/models.py`, `app/database.py` |
| Watchlist lifecycle | `app/services/watchlist_service.py` |
| Dashboard UI | `templates/index.html`, `static/js/app.js`, `static/css/style.css` |
| Model training | `scripts/train_ep_scoring_model.py` |
| Tests | `tests/test_ep_*.py`, `tests/test_phase*.py`, `e2e/tests/test_ep_view.py` |

## Technology and Code Style

- Backend: Python 3.8+, Flask, Flask-SQLAlchemy, APScheduler, SQLite in development.
- Frontend: Jinja templates and vanilla JavaScript/CSS.
- Tests: pytest plus Playwright E2E tests.
- New business rules belong in type-annotated service modules; route modules validate input and serialize responses only.
- Use `snake_case` for Python data and functions, `PascalCase` for classes, and explicit reason-code constants rather than duplicated string literals.
- All new persistence writes must be transactional and idempotent for a `(episode_id, trading_date)` key.

```python
def assess_tradability(candidate: CandidateSnapshot) -> TradabilityAssessment:
    """Return explicit gate outcomes; never hide a failed candidate without a reason."""
    return TradabilityAssessment(
        status="PASS" if candidate.median_turnover_cr >= 20 else "FAIL",
        reasons=[] if candidate.median_turnover_cr >= 20 else ["LOW_MEDIAN_TURNOVER"],
    )
```

## Design Principles

- Preserve immutable facts: catalyst date, original EP-day range, original score/version, original stop, and source links never change.
- Store daily state separately: current price, current score, current trailing stop, trigger status, and freshness can change every session.
- Explain every ranking: no score may appear without catalyst, price acceptance, participation, context, and data-quality evidence.
- Prefer hard tradability gates over a high score on an untradable symbol.
- Evaluate and rank each EP type independently. Growth, turnaround, story, volume, delayed, and short EPs are not one strategy.
- Default to conservative execution assumptions in testing and backtesting.

## Data Contracts

### Candidate quality contract

Every returned EP candidate must expose the following additive fields:

```json
{
  "score_version": "rules-v3|outcome-v1",
  "setup_state": "ACTIONABLE_NOW|WAIT_FOR_TRIGGER|WAIT_FOR_PULLBACK|AVOID|TRIGGERED",
  "quality": {
    "catalyst": "PASS|WARN|FAIL",
    "price_acceptance": "PASS|WARN|FAIL",
    "participation": "PASS|WARN|FAIL",
    "context": "PASS|WARN|FAIL",
    "tradability": "PASS|WARN|FAIL"
  },
  "freshness": {
    "feature_date": "YYYY-MM-DD",
    "pipeline_completed_at": "ISO-8601 timestamp",
    "source_status": "COMPLETE|PARTIAL|STALE"
  },
  "coverage": {
    "universe_scanned": 0,
    "discovered": 0,
    "deep_enriched": 0,
    "excluded_by_reason": {"illiquid": 0}
  }
}
```

### Immutable EP episode

Create an `ep_episodes` record, or add equivalent immutable fields to an EP-specific history table. It must include:

- symbol, exchange, episode/catalyst ID, event timestamp, event source URL, and normalized event type;
- original Day-1 OHLCV, relative volume, delivery data, EP score, score version, and all score components;
- original entry-plan levels, original stop, and catalyst materiality inputs;
- data-quality and enrichment status.

Do not overwrite this row during future refreshes.

### Daily EP state

Create `ep_episode_daily_state` keyed by episode and trading date. Store current close, current score, current trailing stop, setup state, trigger, R achieved, and reason codes. This supports auditability, charts, and accurate backtests.

## Phase 0 — Safety, Semantics, and Baseline

### Goal

Make today’s EP output internally consistent before adding new signals.

### Scope

1. Freeze the original stop when an entry is created.
2. Add an optional trailing stop that can only ratchet upward for long EPs and downward for short EPs.
3. Define one confidence vocabulary and one set of user-visible thresholds.
4. Add score version, feature date, pipeline completion time, and source-status fields to API responses.
5. Record a baseline report by EP type: candidate count, alert count, average score, and current backtest metrics.

### Required rules

- Manual stop changes require a user action and an audit note.
- Automated stop changes require a named trailing rule and may never increase initial risk.
- `HIGH`, `MEDIUM`, and `LOW` must be derived from one central configuration source; the UI must consume the same values.
- A candidate with partial/stale inputs can be displayed, but must be marked `WARN` and cannot auto-alert as HIGH.

### Acceptance criteria

- Re-running the nightly pipeline does not change `original_stop_price`, `entry_price`, catalyst date, or original EP-day values.
- A long trailing stop never decreases across daily states.
- API, UI, alerting, and tests agree on confidence boundaries.
- The EP table displays feature date and source status.

### Verification

- Unit tests for stop immutability and monotonic trailing stops.
- Regression tests for confidence cutoffs in service and API responses.
- Manual refresh test proving the historical episode is unchanged.

## Phase 1 — Tradability and Coverage Gates

### Goal

Prevent thin, distorted, or incomplete candidates from competing with executable EPs.

### Scope

Implement a reusable `TradabilityAssessment` for every candidate.

| Gate | Initial long-EP default | Trader-facing reason |
|---|---:|---|
| Market cap | ₹200 Cr minimum | Reduces micro-cap distortions |
| Median traded value | ₹20 Cr over 20 sessions | Enables realistic entry/exit |
| EP-day traded value | ₹5 Cr minimum | Prevents nominal-volume signals |
| Price | ₹30 minimum | Avoids penny-stock mechanics |
| Circuit/surveillance | Exclude or warn | Identifies execution risk |
| Delivery participation | Display when available | Distinguishes broad participation from churn |
| Short eligibility | F&O verified + user opt-in | Prevents impractical short ideas |

Thresholds must be configuration values, not literals in scoring code. Show the failed-gate reason rather than silently removing every rejected candidate.

### Discovery changes

Use independent queues, deduplicated by symbol and event date:

1. Material earnings/results queue.
2. Corporate announcement queue.
3. Abnormal-price-and-volume queue.
4. Delayed EP trigger queue.
5. Theme-cluster queue.

Relative volume remains a quality signal, but it must not be the sole discovery gate. Deep-enrichment prioritization must use a documented budget and return its coverage statistics.

### Acceptance criteria

- A material, liquid earnings event can enter the candidate set below 3x volume.
- An illiquid candidate receives `tradability=FAIL` with explicit reasons and cannot auto-alert.
- The API reports discovered, enriched, excluded, and failed-source counts for each run.
- Short EP candidates are hidden unless the user enables them and the F&O gate passes.

### Verification

- Fixture tests for each gate and queue.
- Integration test for a 2x-volume earnings candidate and a 10x-volume illiquid candidate.
- UI test verifying gate reasons and coverage banner.

## Phase 2 — Catalyst Materiality and Evidence

### Goal

Make the catalyst score evidence-based instead of relying mainly on a category label.

### Scope

Add `CatalystAssessment` with source provenance, timestamp, extraction confidence, and materiality measures.

| Catalyst | Required evidence | Suggested materiality metric |
|---|---|---|
| Results | reported vs prior periods; guidance when available | revenue/EPS/margin acceleration and surprise |
| Order win | disclosed order value and counterparty | order value ÷ TTM revenue and market cap |
| Capex | amount, timeline, funding source | capex ÷ market cap; debt/funding effect |
| Turnaround | profitability and balance-sheet proof | loss-to-profit durability; debt reduction |
| Governance | filing source and severity | promoter transaction / board change evidence |
| Theme | named policy or industry trigger | sector breadth and peer confirmation |

### Rules

- A source URL and timestamp are required for `catalyst=PASS`.
- Unknown announcements may remain as research leads, but do not receive a high catalyst score merely from a generic label.
- Store the original text, normalized facts, model/NLP extraction version, confidence, and manual override reason.
- Use event time to label entries as pre-market, market-hours, or post-close. Backtesting must respect this availability time.

### Acceptance criteria

- The EP detail view shows “why this matters” in measurable terms, not only the event category.
- A materiality score can be traced to source values and a source link.
- Missing values yield `WARN`, never fabricated certainty.
- Traders can correct a classification with an audit trail.

### Verification

- Parser/NLP fixtures for results, order win, capex, and routine disclosure.
- Tests that verify timestamp-aware availability and override auditing.
- Manual review of 20 historical events with source links.

## Phase 3 — Price Acceptance, Context, and Setup Playbook

### Goal

Convert an EP event into a clear trading plan.

### Scope

Create deterministic assessments for price acceptance, market context, and execution state.

### Price acceptance

Measure and retain:

- gap %, close location, range/ATR expansion, relative volume, delivery %, and close versus VWAP when intraday data is available;
- Day-1 high/low, Day-1 range, opening-range structure, and whether the gap held;
- distance from 10/20/50 DMA, prior base high, and overhead supply;
- 3–5 day tightness and pullback quality.

### Context

Use the existing market-breadth and RRG data to label:

- index regime: risk-on, neutral, risk-off;
- sector RS trend and quadrant;
- theme breadth: number of independent high-quality EPs in the group;
- leader/laggard status within sector.

### Setup states

| State | Condition | User action |
|---|---|---|
| `ACTIONABLE_NOW` | Clean catalyst day, acceptable risk, all critical gates pass | Show entry/stop/size plan |
| `WAIT_FOR_TRIGGER` | Strong thesis, needs reclaim/OR breakout/tight-area breakout | Show exact trigger and expiry |
| `WAIT_FOR_PULLBACK` | Good EP but extended beyond risk limit | Show preferred pullback zone |
| `AVOID` | Failed acceptance, poor context, or failed tradability | Explain failure; no alert |
| `TRIGGERED` | Trigger occurred and entry is recorded | Start trade-management workflow |

### Acceptance criteria

- Every displayed candidate has exactly one state and at least one reason code.
- The details panel shows catalyst-day levels, setup trigger, invalidation, and a concise “why now / why wait” explanation.
- Delayed triggers use immutable catalyst-day levels and are independently testable.
- Sector/theme context appears as evidence, not as a hidden score bonus.

### Verification

- Rule tests for clean Day-1, failed breakout, reclaim, tight-area breakout, and pullback states.
- UI tests for state-specific calls to action.
- Snapshot tests for candidate detail responses.

## Phase 4 — Risk Planning and Journal Integration

### Goal

Give traders a complete, constraint-aware trade plan before they act.

### Scope

Add an EP risk-plan object and connect a triggered episode to the existing journal.

```json
{
  "entry_rule": "DAY2_OR_BREAKOUT",
  "entry_zone": [100.0, 102.0],
  "original_stop": 94.0,
  "trail_rule": "UNDER_3_DAY_LOW",
  "risk_per_share": 6.0,
  "account_risk_pct": 0.5,
  "suggested_quantity": 0,
  "max_chase_price": 103.5,
  "one_r": 106.0,
  "two_r": 112.0,
  "invalidated": false
}
```

### Rules

- Position sizing uses user-configured account risk, not a universal percentage.
- A proposed entry is rejected if its stop distance or gap exceeds configured limits.
- Original risk and every stop change are visible in the journal.
- Correlated sector/theme exposure is shown before a trader adds a position.

### Acceptance criteria

- A triggered setup creates a prefilled journal draft with immutable episode facts.
- The UI shows quantity, risk amount, R levels, stop, and a maximum chase price.
- A trader cannot mark a setup actionable if required risk-plan fields are missing.

### Verification

- Unit tests for sizing, invalid stop, gap limit, and trailing-stop directions.
- Integration test from EP trigger to journal draft.
- Manual test using an account-risk setting and a simulated triggered EP.

## Phase 5 — Outcome Model and Honest Backtesting

### Goal

Replace score-replication claims with a walk-forward, execution-aware evidence system.

### Model design

- Keep `rules-v3` as an explainable baseline.
- Create an outcome model only after the episode history has sufficient real data.
- Train distinct models or calibrations for EP type, not one pooled score.
- Use an outcome defined before training, for example 10- or 20-session return in R after the permitted entry, with realistic stop handling.
- Use time-based walk-forward splits. Never shuffle future data into training.
- Log feature schema, label definition, training window, test window, candidate coverage, and calibration metrics with each model version.
- Do not use synthetic data for a production score model.

### Backtest requirements

Include brokerage, taxes/charges, conservative slippage, gap-through-stop behavior, position limits, cash constraints, and overlapping exposure. Respect event availability time and exclude data that was not known at entry.

Report separately for every EP type, market regime, score decile, market-cap bucket, catalyst type, and entry rule:

- trade count, win rate, expectancy in R, profit factor, median return;
- MAE/MFE, percent never positive, hold duration, and maximum drawdown;
- score-decile monotonicity and calibration;
- sensitivity to costs and one-day delayed execution.

### Promotion gate

No model replaces the rules ranking unless its out-of-sample, net-of-cost results improve the baseline on a predeclared period and enough independent trades exist per segment. Until then, display it as an experimental secondary ranking.

### Acceptance criteria

- Training metadata accurately describes the real target.
- A model report demonstrates out-of-sample results against the rules baseline.
- Backtest results change when slippage or event timing changes, proving those controls are active.
- Users can see the score version used for each episode.

### Verification

- Deterministic backtest fixtures covering stop gaps, simultaneous target/stop days, and post-close announcements.
- Walk-forward test harness with frozen data snapshots.
- Model-card review before promotion.

## Phase 6 — Trader Experience, Alerts, and Operations

### Goal

Make high-quality EPs fast to evaluate without turning the dashboard into a noisy alert feed.

### Scope

- Add an EP command-center table with state, quality gates, data freshness, and risk at a glance.
- Add detail tabs: Thesis, Price/Volume, Catalyst Evidence, Trade Plan, History, and Journal.
- Alert only on state transitions: new actionable setup, delayed trigger, risk invalidation, and material catalyst update.
- Provide user preferences for EP type, liquidity, sector, score/version, market regime, and maximum daily alerts.
- Make details read-only from the request path: external refreshes and AI generation must run as explicit background jobs with cached results.
- Escape all third-party headline/summary content before rendering in the browser.

### Acceptance criteria

- A trader can decide in under 60 seconds whether to act, wait, or avoid, using only the EP detail view.
- Alerts are deduplicated per episode and state transition.
- Detail-page loads do not mutate fundamentals, trigger network enrichment, or block on AI generation.
- Untrusted source text cannot execute as HTML in the client.

### Verification

- E2E test for the actionable, wait, avoid, and triggered paths.
- Alert deduplication and preference tests.
- Browser security test with an HTML-bearing external headline fixture.
- Performance test for a page of EP listings and a detail view.

## API Evolution

- Keep existing endpoints and response keys operational.
- Add new fields additively under `quality`, `freshness`, `coverage`, `episode`, and `risk_plan`.
- Introduce explicit endpoints only when needed: `/api/v1/ep/episodes/<id>`, `/api/v1/ep/episodes/<id>/states`, and `/api/v1/ep/episodes/<id>/risk-plan`.
- Validate query/body values; return 400 for invalid filters and 422 for valid-but-unexecutable trade-plan requests.
- Document each new response schema in OpenAPI before frontend integration.

## Testing Strategy

| Test level | Focus |
|---|---|
| Unit | scoring components, gates, state transitions, sizing, trailing stops |
| Integration | pipeline persistence, API contracts, background-job idempotency |
| Backtest fixtures | timing, slippage, stop gaps, type-specific trade management |
| E2E | filter-to-detail-to-watchlist/journal workflow, alerts, state labels |
| Data quality | source freshness, missing fields, duplicate events, parser confidence |

Existing EP tests must remain green. Each phase adds tests before its service and UI changes are accepted.

## Boundaries

### Always

- Preserve EP historical facts and add migrations rather than rewriting rows.
- Use parameterized SQL/SQLAlchemy and validate all API input.
- Add source links, timestamps, and freshness indicators for external data.
- Test each phase before merging it.

### Ask first

- Adding a paid data provider or new ML dependency.
- Changing database engine, schema migration approach, public API versions, or alert channels.
- Enabling automatic trade execution, broker integration, or short-selling workflows.

### Never

- Represent a score as a return forecast without out-of-sample evidence.
- Train a production model on synthetic data.
- Silently widen a trader’s initial stop or overwrite original episode facts.
- Render third-party text as trusted HTML.
- Commit API credentials, model datasets containing secrets, or personal account data.

## Delivery Plan and Exit Gates

| Release | Phases | Exit gate |
|---|---|---|
| R1: Trust | 0–1 | Immutable stops, coherent confidence, coverage and tradability visible |
| R2: Decision | 2–3 | Evidence-backed catalysts and actionable/wait/avoid playbooks |
| R3: Execution | 4 | Risk plan and journal draft work end-to-end |
| R4: Evidence | 5 | Walk-forward, net-of-cost validation supports score claims |
| R5: Scale | 6 | Fast, secure, deduplicated EP research and alerts |

## Remaining Open Questions

1. Which organisation role or authentication model will authorise shared catalyst overrides?
2. Which minute-bar provider will be approved before intraday functionality is enabled?
3. What migration mechanism will be adopted for the new immutable episode and daily-state tables?
