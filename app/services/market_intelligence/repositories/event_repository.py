from typing import List, Optional
from app.models import MarketEvent
from app.extensions import db


class EventRepository:
    """Isolates database operations for MarketEvent objects."""

    def get_by_symbol(
        self, symbol: str, event_types: Optional[List[str]] = None, limit: int = 20, offset: int = 0
    ) -> List[MarketEvent]:
        """Fetch latest market events for a symbol, sorted by event date descending."""
        query = MarketEvent.query.filter_by(symbol=symbol)
        if event_types:
            query = query.filter(MarketEvent.event_type.in_(event_types))
        return (
            query.order_by(MarketEvent.event_date.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def add(self, event: MarketEvent) -> MarketEvent:
        """Add and commit a single market event."""
        db.session.add(event)
        db.session.commit()
        return event

    def bulk_add(self, events: List[MarketEvent]):
        """Bulk add and commit multiple events."""
        if not events:
            return
        db.session.add_all(events)
        db.session.commit()
