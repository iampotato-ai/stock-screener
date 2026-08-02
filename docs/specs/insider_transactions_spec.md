# Spec: Insider & Promoter Transactions Tracker

## Objective

Build a comprehensive **Insider & Promoter Transactions Tracker** service and REST API endpoint tailored for NSE/BSE India equity markets. The feature tracks insider transactions (PIT disclosures), promoter group buy/sell activities, promoter pledge changes, and bulk/block deal activity (> ₹5 Cr), classifying each into open-market purchases, open-market sales, or neutral transfers.

### Who is the user?
NSE swing traders and momentum investors who use promoter buying and institutional bulk/block deal disclosures as high-conviction catalysts before taking a trade. They need:
- Net promoter buy/sell value over trailing 30d and 90d windows (in ₹ Crores)
- Classification of transactions (Open Market Purchase vs Sale vs Internal Transfer/Pledge)
- Flagging of major bulk/block deal activity (> ₹5 Cr)
- Badges on Screener, Watchlist, and Stock Drawer views: `PROMOTER BUY`, `INSIDER SELL`, `BLOCK DEAL`, `PLEDGE RISK`
- An aggregate **Insider Confidence Score** (0 to 100) integrated into stock research

---

## Assumptions

```
ASSUMPTIONS I'M MAKING:
1. Primary data source is NSE India public disclosures (PIT / SAST / Bulk-Block deal endpoints) with fallback to yfinance insider data objects & DB persistence
2. New SQLAlchemy model `InsiderTransaction` stores processed disclosures with fields: id, symbol, insider_name, insider_type ('Promoter' | 'KMP' | 'Director' | 'Institutional'), transaction_type ('BUY' | 'SELL' | 'PLEDGE' | 'UNPLEDGE' | 'TRANSFER'), mode ('Market' | 'Off-Market' | 'Pledge'), quantity, value_cr, price, transaction_date, disclosure_date
3. New service module `app/services/insider_service.py` provides pure Python logic to fetch, filter out neutral codes (ESOPs, internal transfers), aggregate net flows, compute Insider Confidence Score, and generate badges
4. New Flask API endpoints:
   - GET /api/v1/insider-transactions/<symbol> → Detailed transactions & 30d/90d net flow for a single stock
   - GET /api/v1/insider-transactions/summary → Batch summary for screener enrichment & badge generation
5. Stock Drawer UI displays an "Insider & Promoter Activity" card with net 30d/90d buy/sell value, transaction feed, and pledge warning indicators
6. Pytest test suite covers fetcher, aggregator, scoring logic, and API endpoints with 100% mocked external I/O
→ Correct me now or I'll proceed with these.
```

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Language | Python 3.8+ | Type-annotated service layer |
| Framework | Flask | Existing app factory pattern |
| ORM / Persistence | SQLAlchemy (`InsiderTransaction` model) | SQLite dev database (`scan_history.db`) |
| Data Sources | NSE India PIT API / Bulk Deals + yfinance fallback | HTTP client with user-agent rotation & TTL caching |
| Technical/Scoring | `app/services/insider_service.py` | Integrated into institutional pillar scoring |
| Testing | pytest | `tests/unit/test_insider_service.py`, `tests/unit/test_insider_api.py` |

---

## Commands

```bash
# Run unit and integration tests for insider tracking
pytest tests/unit/test_insider_service.py tests/unit/test_insider_api.py -v

# Run full test suite
pytest

# Verify endpoint manually
curl -s http://localhost:5000/api/v1/insider-transactions/RELIANCE
```

---

## Project Structure

```
app/
├── models.py                          ← [MODIFY] Add InsiderTransaction model definition
├── services/
│   └── insider_service.py             ← [NEW] Insider tracking & aggregation service
├── api/v1/
│   ├── __init__.py                    ← [MODIFY] Register insider_transactions blueprint
│   └── insider_transactions.py       ← [NEW] GET /api/v1/insider-transactions/<symbol> endpoints
templates/
└── index.html                         ← [MODIFY] Add Insider Activity card to stock side drawer
static/
└── js/app.js                          ← [MODIFY] Render insider badges & drawer card
tests/
└── unit/
    ├── test_insider_service.py        ← [NEW] Unit tests for transaction parser & aggregator
    └── test_insider_api.py            ← [NEW] Integration tests for insider API endpoints
docs/
└── specs/
    └── insider_transactions_spec.md   ← THIS SPEC
```

---

## Code Style

```python
"""
Insider & Promoter Transactions Tracking Service.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def classify_transaction_mode(acq_mode: str, transaction_type: str) -> str:
    """
    Classify raw disclosure mode into standardized category.

    Args:
        acq_mode: Raw acquisition mode string from disclosure (e.g. 'Market Purchase').
        transaction_type: 'BUY', 'SELL', 'PLEDGE', etc.

    Returns:
        Standardized mode: 'OPEN_MARKET_BUY' | 'OPEN_MARKET_SELL' | 'PLEDGE' | 'TRANSFER' | 'NEUTRAL'
    """
    mode_lower = (acq_mode or '').lower()
    if 'market' in mode_lower or 'pit' in mode_lower:
        return 'OPEN_MARKET_BUY' if transaction_type == 'BUY' else 'OPEN_MARKET_SELL'
    elif 'pledge' in mode_lower:
        return 'PLEDGE'
    elif 'off market' in mode_lower or 'gift' in mode_lower or 'esop' in mode_lower:
        return 'NEUTRAL'
    return 'NEUTRAL'
```

---

## Detailed Design

### 1. Data Schema: `InsiderTransaction` Model (`app/models.py`)

```python
class InsiderTransaction(BaseModel):
    """Insider and Promoter Disclosure Transactions."""
    __tablename__ = 'insider_transactions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    exchange = db.Column(db.String(10), default='NSE')
    insider_name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), default='Promoter')  # 'Promoter' | 'Director' | 'KMP' | 'Institutional'
    transaction_type = db.Column(db.String(20), nullable=False)  # 'BUY' | 'SELL' | 'PLEDGE' | 'UNPLEDGE'
    mode = db.Column(db.String(30), default='OPEN_MARKET')     # 'OPEN_MARKET' | 'OFF_MARKET' | 'BLOCK_DEAL' | 'PLEDGE'
    num_shares = db.Column(db.BigInteger, default=0)
    price = db.Column(db.Float, default=0.0)
    value_cr = db.Column(db.Float, default=0.0)              # Transaction value in INR Crores
    holding_post_pct = db.Column(db.Float, nullable=True)     # Holding % after transaction
    transaction_date = db.Column(db.Date, nullable=False, index=True)
    disclosure_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

---

### 2. Transaction Aggregation & Metrics (`app/services/insider_service.py`)

Computes trailing metrics for a single stock:

- **`net_promoter_buy_30d`** (float, ₹ Cr): Total open-market promoter buys minus open-market promoter sells over trailing 30 days.
- **`net_promoter_buy_90d`** (float, ₹ Cr): Trailing 90-day net promoter buy value.
- **`bulk_deal_count_30d`** (int): Number of block/bulk deal transactions > ₹5 Cr in last 30 days.
- **`pledge_change_pct`** (float): Net % change in promoter pledged shares over trailing 90 days.
- **`insider_sentiment_score`** (float, 0–100):
  - Base: 50 (neutral)
  - Net promoter buy > ₹10 Cr → +25 pts
  - Net promoter buy > ₹2 Cr → +15 pts
  - Bulk deal net buy > ₹15 Cr → +15 pts
  - Net promoter sell > ₹10 Cr → -25 pts
  - Net promoter sell > ₹2 Cr → -15 pts
  - Increased promoter pledge (> 5%) → -15 pts
- **`badges`** (list of str):
  - `🔥 PROMOTER BUY` — if 30d net buy > ₹2 Cr
  - `⚠️ PROMOTER SELL` — if 30d net sell > ₹2 Cr
  - `🏛️ BLOCK DEAL` — if 30d bulk deal > ₹5 Cr
  - `🚨 PLEDGE RISK` — if promoter pledged % > 15% or increased > 5%

---

### 3. API Contract

#### `GET /api/v1/insider-transactions/<symbol>`

**Response JSON:**
```json
{
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "insider_score": 75.0,
  "metrics": {
    "net_promoter_buy_30d": 14.50,
    "net_promoter_buy_90d": 32.10,
    "bulk_deal_count_30d": 2,
    "bulk_deal_net_val_30d": 25.00,
    "promoter_pledged_pct": 0.0,
    "pledge_change_pct": 0.0
  },
  "badges": ["🔥 PROMOTER BUY", "🏛️ BLOCK DEAL"],
  "recent_transactions": [
    {
      "insider_name": "Mukesh Ambani / Promoter Group",
      "category": "Promoter",
      "transaction_type": "BUY",
      "mode": "OPEN_MARKET",
      "num_shares": 500000,
      "price": 1280.00,
      "value_cr": 64.00,
      "transaction_date": "2026-01-25"
    }
  ],
  "success": true
}
```

#### `GET /api/v1/insider-transactions/summary`

**Response JSON:** Batch dictionary keyed by symbol for quick screener lookup.

---

### 4. UI Integration

In `templates/index.html` (inside stock side drawer):
- Renders an **"Insider & Promoter Activity"** card displaying:
  - 30d Net Promoter Flow badge (e.g. `+₹14.5 Cr (Buy)`)
  - 30d Block Deal Activity badge
  - Recent transactions table (Date, Insider, Type, Value ₹ Cr)

---

## Testing Strategy

| Test Level | Location | Coverage Target |
|-----------|----------|-----------------|
| **Unit tests** | `tests/unit/test_insider_service.py` | ≥ 90% for classification, filtering, and aggregation |
| **API integration** | `tests/unit/test_insider_api.py` | Single stock and batch endpoints with mocked DB |
| **Regression** | `pytest` | Full suite green |

---

## Boundaries

### Always Do:
- Run `pytest` before committing
- Filter out neutral transaction codes (ESOP exercises, internal family transfers, tax withholding)
- Use defensive `.get()` for all dictionary lookups
- Log errors via `logger.error()`

### Ask First:
- Modifying existing SQLAlchemy models other than adding `InsiderTransaction`
- Altering existing institutional score calculation in `app/services/scoring/institutional.py`

### Never Do:
- Store hardcoded API keys or external credentials
- Make real network calls during unit test runs
- Remove failing test assertions

---

## Success Criteria

- [ ] `InsiderTransaction` model created and migratable in SQLite/SQLAlchemy
- [ ] `insider_service.py` correctly parses raw disclosures and filters out non-market transfers (ESOPs, internal transfers)
- [ ] 30d/90d net buy values, bulk deal counts, and pledge changes match expected math
- [ ] `GET /api/v1/insider-transactions/<symbol>` returns HTTP 200 with full metrics, badges, and recent transactions
- [ ] `GET /api/v1/insider-transactions/summary` returns batch dictionary for fast screener lookup
- [ ] Stock side drawer in web UI displays the "Insider & Promoter Activity" card
- [ ] Test coverage for new service ≥ 90%
- [ ] Full pytest test suite passes cleanly with 0 failures
