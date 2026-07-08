import hashlib
import logging
import datetime
from typing import Optional
from app.models import NewsArticle, MarketEvent
from .schemas.normalized_event import NormalizedArticle, NormalizedEvent

logger = logging.getLogger(__name__)

from .validation.validator import DataValidator, VALID_EVENT_TYPES


class Deduplicator:
    """Handles content hashing and checks database state to ensure duplicate entries are ignored."""

    @staticmethod
    def generate_event_hash(event: NormalizedEvent) -> str:
        """Generate a SHA-256 unique identifier hash for a market event based on its content properties."""
        content_string = f"{event.symbol.upper()}:{event.event_type.upper()}:{event.event_date.isoformat()}:{event.details or ''}"
        return hashlib.sha256(content_string.encode('utf-8')).hexdigest()

    @staticmethod
    def is_news_duplicate(article: NormalizedArticle) -> bool:
        """Check if article already exists in the database by external_id or URL."""
        # Check by external_id
        if article.external_id:
            exists = NewsArticle.query.filter_by(external_id=article.external_id).first() is not None
            if exists:
                return True

        # Fallback to checking by URL
        exists_url = NewsArticle.query.filter_by(url=article.url).first() is not None
        return exists_url

    @staticmethod
    def is_event_duplicate(event: NormalizedEvent, calculated_hash: Optional[str] = None) -> bool:
        """Check if event already exists in database by external_id or unique_hash."""
        if event.external_id:
            exists = MarketEvent.query.filter_by(external_id=event.external_id).first() is not None
            if exists:
                return True

        # Check by computed unique hash
        event_hash = calculated_hash or Deduplicator.generate_event_hash(event)
        exists_hash = MarketEvent.query.filter_by(unique_hash=event_hash).first() is not None
        return exists_hash
