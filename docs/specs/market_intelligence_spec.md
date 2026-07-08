# Spec: Market Intelligence Events Engine

## Objective
Establish a unified **Market Intelligence** module for MomentumScan. Rather than treating news and corporate announcements as separate pipelines, this architecture unifies them into a single, extensible **Market Events** framework. 

This enables MomentumScan to:
1. Ingest, normalize, de-duplicate, run NLP enrichment on, and persist various market intelligence event types (News, Earnings, Dividends, Splits, Bonus issues, Bulk/Block deals, Insider trading).
2. Establish clean abstraction layers for data providers using a factory pattern and managed fallback system.
3. Decouple ingestion from NLP/AI enrichment, ensuring events are stored immediately even if the enrichment pipeline fails.
4. Expose a unified, paginated REST endpoint `/api/v1/events` while preserving backward compatibility for the legacy `/api/v1/news` route.
5. Provide a timeline-centric visual interface in the UI grouped by timeframe with clear indicators of event sentiment, type, and importance.

---

## Tech Stack
- **Backend**: Python 3.12, Flask, SQLAlchemy (SQLite database mapping to `scan_history.db`).
- **External APIs**: Marketaux.com News API (primary news provider, configured via token), Google News RSS (fallback provider).
- **Scheduling**: APScheduler (existing background manager in `app/tasks/scheduler.py`).
- **NLP Processing**: Existing HuggingFace pipelines (`NLPService` in `app/services/nlp_service.py` using FinBERT, Zero-Shot classifiers, and Summarization).

---

## Commands
- Run development server: `python run.py` (or execute `start.bat`)
- Run tests: `python -m pytest`
- Run specific tests: `python -m pytest tests/unit/test_market_intelligence.py`

---

## Project Structure
The implementation will introduce a modular `market_intelligence` directory and integrate with existing structures:

```text
app/
├── models.py                          → [MODIFY] Add NewsArticle, MarketEvent, and NewsFetchLog models
├── api/v1/
│   ├── events.py                      → [NEW] Expose unified GET /api/v1/events REST API
│   └── news.py                        → [MODIFY] Keep for compatibility, delegating internally to events API
├── tasks/
│   └── scheduler.py                   → [MODIFY] Configure scheduled events ingestion tasks
└── services/
    └── market_intelligence/           → [NEW] Modular Market Intelligence services
        ├── __init__.py
        ├── providers/
        │   ├── __init__.py
        │   ├── base.py                → Base data provider interface returning raw normalized dicts
        │   ├── manager.py             → ProviderManager handles fallbacks, ordering, retries, and health checks
        │   ├── marketaux.py           → Marketaux API provider
        │   ├── google_rss.py          → Google News RSS provider
        │   └── nse_rss.py             → NSE corporate disclosures scraper/RSS provider
        ├── services/
        │   ├── news_service.py        → News data ingest and fetch-logging Orchestrator
        │   └── event_service.py       → Market event ingest, deduplication, and persistence Orchestrator
        ├── deduplicator.py            → Hash/unique key comparison logic using title, url, or external_id
        ├── timeline/
        │   └── timeline_service.py    → Aggregates, filters, groups by date, and prepares timeline lists
        ├── ai/
        │   └── ai_enrichment.py       → Async/delayed NLP enrichment (sentiment confidence, why_it_matters)
        └── cache/
            └── cache_manager.py       → Cache wrappers to prevent redundant API queries
```

---

## Data Models

```python
class NewsArticle(BaseModel):
    """SQLAlchemy model for persisted news articles."""
    __tablename__ = 'news_articles'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    external_id = db.Column(db.String(100), unique=True, index=True) # Provider-native article ID
    title = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(1000), unique=True, nullable=False)
    summary = db.Column(db.Text)
    source = db.Column(db.String(100))             # Source publication/feed name
    sentiment = db.Column(db.String(20))          # Positive, Negative, Neutral
    sentiment_confidence = db.Column(db.Float)    # Confidence percentage (0-100)
    importance = db.Column(db.String(20))         # Low, Medium, High, Critical
    why_it_matters = db.Column(db.Text)           # AI explanation
    published_at = db.Column(db.DateTime, nullable=False, index=True)
    inserted_at = db.Column(db.DateTime, default=db.func.now())

    __table_args__ = (
        db.Index('idx_news_symbol_pub', 'symbol', 'published_at'),
    )


class MarketEvent(BaseModel):
    """SQLAlchemy model for structured market events (Earnings, Dividends, Insider, Deals, etc.)."""
    __tablename__ = 'market_events'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    external_id = db.Column(db.String(100), unique=True, index=True) # Corporate Action filing ID
    event_type = db.Column(db.String(50), nullable=False, index=True) # EARNINGS, DIVIDEND, SPLIT, BULK_DEAL, INSIDER, etc.
    event_date = db.Column(db.Date, nullable=False, index=True)
    title = db.Column(db.String(500), nullable=False)
    details = db.Column(db.Text)
    ratio = db.Column(db.String(50))               # For splits/bonus (e.g. 1:1)
    amount = db.Column(db.Float)                   # For dividends
    sentiment = db.Column(db.String(20))          # Positive, Negative, Neutral
    sentiment_confidence = db.Column(db.Float)    # Confidence percentage (0-100)
    importance = db.Column(db.String(20))         # Low, Medium, High, Critical
    catalyst_score = db.Column(db.Float)           # Score between -10 and +10
    why_it_matters = db.Column(db.Text)           # AI explanation
    unique_hash = db.Column(db.String(64), unique=True, nullable=False) # Ingestion deduplication key
    source = db.Column(db.String(50), default='NSE') # Ingestion source (NSE, BSE, etc.)
    inserted_at = db.Column(db.DateTime, default=db.func.now())


class NewsFetchLog(BaseModel):
    """SQLAlchemy model logging fetch metrics and API health."""
    __tablename__ = 'news_fetch_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    provider = db.Column(db.String(50), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False) # SUCCESS, ERROR
    latency_ms = db.Column(db.Integer)
    error_message = db.Column(db.Text)
    records_count = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.DateTime, default=db.func.now(), index=True)
```

---

## Testing Strategy
- **Unit Tests**:
  - Verification of deduplication logic (hash checking).
  - Validation of event normalization from different provider schemas.
  - Test of priority queue sorting for symbols fetching (including age-based decay).
- **Integration Tests**:
  - Mock providers (Marketaux, Google RSS, NSE RSS) and verify pipeline outputs.
- **API Tests**:
  - Query `/api/v1/events` endpoint verifying type filter logic, pagination, and sorting.
  - Query `/api/v1/news` legacy endpoint verifying correct formatting and backward compatibility.

---

## Boundaries
- **Always do**: Run de-duplication hash checks before persisting any new event. Log every fetch attempt in `news_fetch_logs`. Limit query operations using index scans.
- **Ask first**: Change priority queue weighting factors.
- **Never do**: Show fake/simulated action details in production UI. Fetch raw data in request thread.

---

## Success Criteria
- [ ] Database tables `news_articles`, `market_events`, and `news_fetch_logs` are correctly initialized.
- [ ] `GET /api/v1/events` returns unified events and news sorted by date.
- [ ] Pipeline correctly identifies and rejects duplicate news articles/announcements.
- [ ] The priority queue weights scheduler ingestion correctly with recently viewed items decaying after 24h.
- [ ] The dashboard renders a visually premium event timeline grouped by date with sentiment labels and "Why it matters" highlights.
