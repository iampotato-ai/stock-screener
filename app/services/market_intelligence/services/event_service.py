import logging
from typing import List
from app.models import MarketEvent
from ..providers.manager import ProviderManager
from ..repositories.event_repository import EventRepository
from ..deduplicator import DataValidator, Deduplicator

logger = logging.getLogger(__name__)


class EventService:
    """Orchestrates market event ingestion, validation, deduplication, and database storage."""

    def __init__(self):
        self.provider_manager = ProviderManager()
        self.event_repository = EventRepository()

    def ingest_events_for_symbol(self, symbol: str) -> int:
        """
        Fetch events from providers, validate, deduplicate, and persist.
        Returns the number of new events inserted.
        """
        raw_events = self.provider_manager.fetch_events(symbol)
        new_count = 0

        for item in raw_events:
            # 1. Validate
            if not DataValidator.validate_event(item):
                continue

            # Compute unique hash
            unique_hash = Deduplicator.generate_event_hash(item)

            # 2. Deduplicate
            if Deduplicator.is_event_duplicate(item, unique_hash):
                continue

            # 3. Create DB model & save
            db_event = MarketEvent(
                symbol=item.symbol,
                external_id=item.external_id,
                event_type=item.event_type,
                event_date=item.event_date,
                title=item.title,
                details=item.details,
                ratio=item.ratio,
                amount=item.amount,
                source=item.source,
                unique_hash=unique_hash,
                sentiment="Neutral",  # Defaults until NLP enrichment runs
                sentiment_confidence=100.0,
                importance="Medium",
                catalyst_score=0.0
            )
            try:
                self.event_repository.add(db_event)
                new_count += 1

                # Trigger AI enrichment (non-blocking hook)
                self._trigger_ai_enrichment(db_event)
            except Exception as e:
                logger.error(f"Failed to persist event '{item.title}': {e}")

        if new_count > 0:
            try:
                from ..cache.manager import cache_manager
                cache_manager.delete_pattern(f"timeline:{symbol.upper()}:")
            except Exception as e:
                logger.error(f"Failed to invalidate timeline cache for symbol {symbol}: {e}")

        return new_count

    def get_events_for_symbol(self, symbol: str, limit: int = 15) -> List[MarketEvent]:
        """Fetch stored events from the database. Falls back to immediate ingestion if DB is empty."""
        events = self.event_repository.get_by_symbol(symbol, limit=limit)
        if not events:
            self.ingest_events_for_symbol(symbol)
            events = self.event_repository.get_by_symbol(symbol, limit=limit)
        return events

    def _trigger_ai_enrichment(self, event: MarketEvent):
        """Trigger AI enrichment for the event (fully implemented in Phase 4)."""
        try:
            from ..ai.ai_enrichment import enrich_event_non_blocking
            enrich_event_non_blocking(event.id)
        except ImportError:
            # Stubbed until enrichment module is written
            pass
        except Exception as e:
            logger.error(f"Failed to trigger AI enrichment for event {event.id}: {e}")
