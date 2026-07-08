import hashlib
import logging
import datetime
from typing import Optional
from app.models import NewsArticle, MarketEvent
from .schemas.normalized_event import NormalizedArticle, NormalizedEvent

logger = logging.getLogger(__name__)

# Allowed event types matching spec
VALID_EVENT_TYPES = {
    "EARNINGS",
    "DIVIDEND",
    "SPLIT",
    "BONUS",
    "BULK_DEAL",
    "BLOCK_DEAL",
    "INSIDER",
    "CORPORATE_ACTION",
    "BOARD_MEETING"
}


class DataValidator:
    """Validates normalized news and event objects before they are processed or persisted."""

    @staticmethod
    def validate_article(article: NormalizedArticle) -> bool:
        """Validate a news article."""
        if not article.symbol or len(article.symbol.strip()) == 0:
            logger.warning("Article validation failed: missing symbol.")
            return False
        if not article.title or len(article.title.strip()) < 3:
            logger.warning("Article validation failed: title too short or missing.")
            return False
        if not article.url or not article.url.startswith("http"):
            logger.warning(f"Article validation failed: invalid URL format '{article.url}'.")
            return False
        if not isinstance(article.published_at, datetime.datetime):
            logger.warning("Article validation failed: published_at is not a datetime object.")
            return False
        
        # Date sanity check (not in distant future or > 1 year in past)
        now = datetime.datetime.now(datetime.timezone.utc)
        if article.published_at > now + datetime.timedelta(days=2):
            logger.warning(f"Article validation failed: future publication date '{article.published_at}'.")
            return False
        if (now - article.published_at).days > 365:
            logger.warning(f"Article validation failed: date is older than 1 year '{article.published_at}'.")
            return False

        return True

    @staticmethod
    def validate_event(event: NormalizedEvent) -> bool:
        """Validate a corporate actions or market event."""
        if not event.symbol or len(event.symbol.strip()) == 0:
            logger.warning("Event validation failed: missing symbol.")
            return False
        if event.event_type not in VALID_EVENT_TYPES:
            logger.warning(f"Event validation failed: unrecognized event type '{event.event_type}'.")
            return False
        if not event.title or len(event.title.strip()) < 3:
            logger.warning("Event validation failed: title too short or missing.")
            return False
        if not isinstance(event.event_date, datetime.date):
            logger.warning("Event validation failed: event_date is not a date object.")
            return False

        # Date sanity check
        today = datetime.date.today()
        if event.event_date > today + datetime.timedelta(days=365):
            logger.warning(f"Event validation failed: event date is > 1 year in future '{event.event_date}'.")
            return False
        if (today - event.event_date).days > 365:
            logger.warning(f"Event validation failed: event date is > 1 year in past '{event.event_date}'.")
            return False

        # Custom rules based on type
        if event.event_type == "DIVIDEND" and event.amount is not None:
            if event.amount <= 0:
                logger.warning(f"Event validation warning: dividend amount is <= 0 ({event.amount}).")
        
        return True


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
