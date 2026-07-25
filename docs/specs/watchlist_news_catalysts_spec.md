# Spec: Watchlist News & Catalysts

## Objective
To establish a unified, performant, and resilient pipeline for aggregating and classifying **News & Sentiment Catalysts** within the Watchlist view of MomentumScan. This specification encompasses:
1. Multi-source news aggregation (`/api/news` or `/api/v1/news`) using a waterfall strategy (Yahoo Finance, Google News RSS, and optionally MarketAux).
2. Catalyst & Sentiment extraction powered by **NVIDIA NIM** (with 5-minute in-memory caching and Gemini fallback resilience).
3. Watchlist frontend UI integration (sentiment pills, loading state controls, and error boundaries).

---

## Tech Stack
- **Backend:** Python 3.8+, Flask, SQLAlchemy (SQLite/PostgreSQL DB mapping via `scan_history.db`).
- **External Providers & Libraries:**
  - **Yahoo Finance:** `yfinance` Python package.
  - **Google News RSS:** XML parsing using Python's standard `xml.etree.ElementTree` or standard regex.
  - **MarketAux:** Direct HTTPS requests via `requests`.
- **AI/LLM Integration:**
  - **NVIDIA NIM API:** HTTP requests (using `meta/llama-3.1-70b-instruct` or `openai/gpt-oss-120b`).
  - **Google Gemini API:** REST endpoint using `gemini-flash-lite-latest` or `gemini-3.5-flash` as fallback.
- **Frontend:** Vanilla HTML/CSS/JS (embedded in `static/js/app.js`, `templates/index.html`).

---

## Commands
- **Run Dev Server:** `python run.py`
- **Run Test Suite:** `pytest`
- **Run Specific Tests:** `pytest tests/unit/test_watchlist_news_catalysts.py`
- **Check Linting:** `flake8 app/` (or matching Python syntax checkers)
- **Run E2E Checks:** `python -m pytest -q e2e/tests/*.py`

---

## Project Structure
We will modify existing components to conform with Flask/SQLAlchemy patterns:

```text
app/
├── api/v1/
│   └── news.py                        → [MODIFY] Return structured JSON news & sentiment pills, delegating to NewsService.
├── services/
│   ├── ai_service.py                  → [MODIFY] Implement NVIDIA NIM logic, retry wrapper (`callNvidiaNimWithRetry`), in-memory cache, and fallback to Gemini.
│   └── market_intelligence/
│       ├── providers/
│       │   ├── yahoo_finance.py       → [NEW] Yahoo Finance news provider using yfinance.
│       │   ├── manager.py             → [MODIFY] Register Yahoo Finance as primary news provider in the waterfall.
│       │   └── __init__.py            → [MODIFY] Export YahooFinanceProvider.
│       └── services/
│           └── news_service.py        → [MODIFY] Primary orchestrator for waterfall news fetch and DB persistence.
static/
└── js/
    └── app.js                         → [MODIFY] Update to call `/api/news`, display sentiment pills (🟢, 🟡, 🔴), and manage newsLoadingTickers state.
```

---

## Code Style
The backend code must use explicit type annotations, log operations with Python's standard logger, and handle database sessions safely:

```python
import logging
from typing import Dict, Any, List, Optional
from app.models import NewsArticle

logger = logging.getLogger(__name__)

def cache_sentiment_result(symbol: str, sentiment: str, summary: str) -> Dict[str, Any]:
    """Caches analysis results in-memory."""
    # Example logic for caching
    result = {
        "sentiment": sentiment,
        "summary": summary,
        "timestamp": datetime.now()
    }
    return result
```

---

## Testing Strategy
- **Unit Tests:**
  - Mock `yfinance`, Google News RSS feeds, and MarketAux API responses.
  - Test `callNvidiaNimWithRetry` to verify retry counts, exponential backoff, and fallback to Gemini.
  - Test in-memory cache behavior for NIM news analysis (verify expiration after 5 minutes).
  - Verify regex and related tickers check validation in the Yahoo Finance provider.
- **Integration Tests:**
  - Verify that the GET `/api/news?symbol={TICKER}` endpoint aggregates correctly and retrieves cached/live sentiment results.
- **End-to-End Tests:**
  - Verify that selecting a watchlist item triggers news fetch and renders the timeline with sentiment pills.

---

## Boundaries
- **Always do:** 
  - Validate that retrieved news matches Indian stock tickers.
  - Dedup articles by URL or title hash before calling the NIM API.
  - Catch rate-limiting/network exceptions and log them properly.
- **Ask first:** 
  - Adding new dependencies to `requirements.txt`.
- **Never do:** 
  - Call third-party LLMs synchronously during user requests without short-circuited caching.
  - Bypass database transaction safety (always call `db.session.rollback()` on exception).

---

## Success Criteria
- [ ] Backend endpoint `/api/news?symbol={TICKER}` aggregates news from Yahoo Finance, Google News, and optionally MarketAux.
- [ ] News sentiments are extracted using NVIDIA NIM (caching for 5 minutes) and return `sent-positive`, `sent-neutral`, or `sent-negative`.
- [ ] A retry wrapper `callNvidiaNimWithRetry` includes exponential backoff and falls back to Gemini if NIM is unreachable.
- [ ] Watchlist UI correctly displays sentiment pills and manages the `newsLoadingTickers` loading states.
