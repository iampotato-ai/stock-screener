from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class NormalizedArticle:
    """Type-safe container for normalized news articles from any provider."""
    symbol: str
    title: str
    url: str
    published_at: datetime
    summary: Optional[str] = None
    source: Optional[str] = None
    external_id: Optional[str] = None


@dataclass
class NormalizedEvent:
    """Type-safe container for normalized corporate actions and market events from any provider."""
    symbol: str
    event_type: str  # EARNINGS, DIVIDEND, SPLIT, BONUS, BULK_DEAL, INSIDER, etc.
    event_date: date
    title: str
    details: Optional[str] = None
    ratio: Optional[str] = None  # for stock splits or bonuses
    amount: Optional[float] = None  # for dividends
    external_id: Optional[str] = None
    source: str = "NSE"  # default source
