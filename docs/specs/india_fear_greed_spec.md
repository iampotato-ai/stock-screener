# Spec: India-Specific Fear & Greed Index

## Objective
Build a real-time, composite **India Fear & Greed Index** (0–100 score and category label: Extreme Fear, Fear, Neutral, Greed, Extreme Greed) tailored for the National Stock Exchange (NSE) of India. 

The index will aggregate 5 key sub-indicators derived from local database tables (`daily_bars`, `breadth_history`, market breadth indicators) and external feeds (India VIX via yfinance `^INDIAVIX` or NSE API):
1. **Market Momentum (20%)**: Nifty 50 (% deviation from 125-day SMA).
2. **Stock Price Strength (20%)**: Ratio of 52-week highs vs 52-week lows across active NSE universe.
3. **Stock Price Breadth (20%)**: % of active stocks trading above 50-day SMA.
4. **Market Volatility / India VIX (20%)**: India VIX level relative to its 50-day moving average.
5. **Advance-Decline Momentum (20%)**: 5-day exponential moving average of (Advances - Declines) / (Advances + Declines).

The index will be exposed via a new API endpoint (`GET /api/v1/fear-greed-index`), cached with a 15-minute TTL, scheduled for EOD/periodic background calculation, and rendered in the frontend dashboard header/hero section as an interactive gauge widget.

---

## Assumptions
1. Nifty 50 index prices (`^NSEI` or `NIFTY 50`) and India VIX (`^INDIAVIX`) are fetchable via yfinance or calculated from existing daily bar data.
2. Market breadth metrics (% above 50d SMA, 52-week highs/lows, advances/declines) are calculated using existing active universe data in `daily_bars` / `STAGE_ANALYSIS_RESULTS`.
3. SQLite database schema can be extended with a new model/table `fear_greed_history` or enriched inside `BreadthHistory`. Adding a dedicated `FearGreedHistory` table avoids mutating legacy tables.
4. Modern vanilla HTML/CSS/JS frontend (no bundler) renders the Fear & Greed gauge widget on `templates/index.html` with dark mode support and SVG/CSS speed-gauge visualizations.

---

## Tech Stack & Dependencies
- **Backend**: Python 3.8+, Flask, Flask-SQLAlchemy, SQLite (`scan_history.db`).
- **Data sources**: `yfinance` for `^INDIAVIX` & `^NSEI`, existing local `daily_bars` SQLite table.
- **Testing**: `pytest` (unit & service tests), Playwright for E2E verification.
- **Frontend**: Vanilla JavaScript (ES6+), Vanilla CSS variables (dark theme, glassmorphism), HTML5 SVG for gauge rendering.

---

## Commands
```bash
# Run unit & service tests
pytest tests/unit/test_fear_greed_service.py

# Run all pytest tests
pytest

# Execute Flask development server
python run.py

# Run Playwright E2E tests
python -m pytest -q e2e/tests/test_fear_greed_ui.py
```

---

## Project Structure
```
app/
├── models.py                          → [MODIFY] Add FearGreedHistory ORM model
├── services/
│   └── fear_greed_service.py          → [NEW] India Fear & Greed calculation engine & service
├── api/v1/
│   ├── fear_greed.py                  → [NEW] REST API endpoint (/api/v1/fear-greed-index)
│   └── __init__.py                    → [MODIFY] Register fear_greed blueprint/routes
├── tasks/
│   └── scheduler.py                   → [MODIFY] Add background job refresh_fear_greed_index
static/
├── js/
│   └── fear_greed_gauge.js            → [NEW] Frontend gauge component logic
└── css/
    └── fear_greed.css                 → [NEW] Styling for Fear & Greed gauge widget
templates/
└── index.html                         → [MODIFY] Mount Fear & Greed gauge widget in dashboard
tests/
└── unit/
    └── test_fear_greed_service.py     → [NEW] Unit tests for Fear & Greed calculation
```

---

## Code Style & Conventions
- `snake_case` for Python functions and variables.
- `PascalCase` for Python classes and ORM models.
- Type hints on all public service methods.
- explicit `db.session.commit()` handling in service layer.
- `try/except` fallback logic for yfinance network calls so local fallback data works offline.
- CSS: Vanilla CSS with custom properties (`var(--bg-primary)`, `var(--text-accent)`).

```python
# Example Code Pattern for Service Method
class FearGreedService:
    """Service for computing India-specific Fear & Greed index."""

    def compute_fear_greed_index(self) -> Dict[str, Any]:
        """Compute composite score (0-100) and sub-indicator breakdown."""
        momentum_score = self._calc_momentum_score()
        strength_score = self._calc_strength_score()
        breadth_score = self._calc_breadth_score()
        volatility_score = self._calc_volatility_score()
        ad_score = self._calc_ad_score()

        composite = (
            momentum_score * 0.20 +
            strength_score * 0.20 +
            breadth_score * 0.20 +
            volatility_score * 0.20 +
            ad_score * 0.20
        )
        composite_score = max(0, min(100, int(round(composite))))
        label = self.get_rating_label(composite_score)

        return {
            "score": composite_score,
            "label": label,
            "timestamp": datetime.utcnow().isoformat(),
            "sub_indicators": {
                "momentum": round(momentum_score, 1),
                "strength": round(strength_score, 1),
                "breadth": round(breadth_score, 1),
                "volatility": round(volatility_score, 1),
                "ad_momentum": round(ad_score, 1),
            }
        }
```

---

## Testing Strategy
1. **Unit Tests**:
   - `test_fear_greed_service.py`: Validate composite score calculation with mock data, bounds checking (0–100), label mapping (0-24 -> Extreme Fear, 76-100 -> Extreme Greed), and fallback graceful handling when VIX is unavailable.
2. **API Endpoint Tests**:
   - `test_fear_greed_api.py`: Verify `/api/v1/fear-greed-index` returns 200 OK with expected JSON keys (`score`, `label`, `sub_indicators`).
3. **Performance Check**:
   - Index calculation latency must be < 100ms when reading from local cached SQLite tables.

---

## Boundaries
- **Always do**: Handle external network timeouts (yfinance/VIX) gracefully with fallback or cached values; write pytest unit tests for calculation logic; enforce 0–100 bounds on all score components.
- **Ask first**: Major changes to DB schema or modifying existing legacy endpoints.
- **Never do**: Break existing `BreadthHistory` DB records or stall main Flask startup thread with slow blocking yfinance queries.

---

## Success Criteria
- [ ] `FearGreedHistory` ORM model defined and migrated cleanly.
- [ ] `FearGreedService` implements 5-factor calculation with bounds [0, 100] and label resolution.
- [ ] `GET /api/v1/fear-greed-index` returns score, label, and sub-indicator breakdown.
- [ ] Background job in `app/tasks/scheduler.py` refreshes Fear & Greed cache automatically.
- [ ] Frontend widget renders gauge meter with current score, indicator breakdown tooltip, and color theme (Red -> Yellow -> Green).
- [ ] Unit test suite passes with >90% code coverage for `fear_greed_service.py`.
