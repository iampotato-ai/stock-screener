import time
import logging
from typing import Dict, List, Set
from flask import has_app_context
from app.models import WatchlistItem, EpWatchlist, TradeJournal, MomentumScore

logger = logging.getLogger(__name__)


class PriorityQueueManager:
    """Manages ingestion scheduling priorities for stock symbols with decay logic."""

    def __init__(self):
        # In-memory store for recently viewed symbol timestamps
        self.recently_viewed: Dict[str, float] = {}

    def mark_viewed(self, symbol: str):
        """Mark a symbol as recently viewed by updating its timestamp in memory."""
        clean_symbol = symbol.split(':')[-1].upper() if ':' in symbol else symbol.upper()
        self.recently_viewed[clean_symbol] = time.time()
        logger.debug(f"Symbol {clean_symbol} marked as recently viewed.")

    def get_symbol_priority(self, symbol: str) -> int:
        """
        Calculate scheduling priority score for a symbol.
        Scores:
        - Active Watchlist item: 100
        - Momentum/Screen result: 90
        - Portfolio (active TradeJournal): 80
        - Recently Viewed (< 24h): 70
        - Default: 20
        """
        clean_symbol = symbol.split(':')[-1].upper() if ':' in symbol else symbol.upper()
        
        # Check Flask app context for DB operations
        if not has_app_context():
            return self._get_memory_priority(clean_symbol)

        try:
            # 1. Watchlist (100)
            wl_exists = WatchlistItem.query.filter_by(ticker=clean_symbol).first() is not None
            if not wl_exists:
                wl_exists = EpWatchlist.query.filter_by(symbol=clean_symbol, status='ACTIVE').first() is not None
            if wl_exists:
                return 100

            # 2. Momentum/Screen Results (90)
            momentum_exists = MomentumScore.query.filter_by(symbol=clean_symbol).first() is not None
            if momentum_exists:
                return 90

            # 3. Portfolio Trade Journal (80)
            trade_exists = TradeJournal.query.filter_by(ticker=clean_symbol).first() is not None
            if trade_exists:
                return 80

            # 4. Recently Viewed with 24h decay (70 -> 20)
            if clean_symbol in self.recently_viewed:
                view_time = self.recently_viewed[clean_symbol]
                if time.time() - view_time < 86400:
                    return 70

        except Exception as e:
            logger.error(f"Error checking DB priorities for {clean_symbol}: {e}")

        # 5. Default/Other tracked symbol
        return 20

    def _get_memory_priority(self, symbol: str) -> int:
        """Fallback check using memory structure if no DB context is active."""
        if symbol in self.recently_viewed:
            if time.time() - self.recently_viewed[symbol] < 86400:
                return 70
        return 20

    def get_all_priority_symbols(self) -> List[str]:
        """Fetch all tracked symbols across database tables, sorted descending by priority score."""
        symbols: Set[str] = set()
        if not has_app_context():
            return list(self.recently_viewed.keys())

        try:
            # Pull from watchlist
            for w in WatchlistItem.query.all():
                symbols.add(w.ticker.upper())
            for w in EpWatchlist.query.filter_by(status='ACTIVE').all():
                symbols.add(w.symbol.upper())
            # Pull from portfolio
            for t in TradeJournal.query.all():
                symbols.add(t.ticker.upper())
            # Pull from momentum scores
            for m in MomentumScore.query.with_entities(MomentumScore.symbol).distinct().all():
                symbols.add(m.symbol.upper())
        except Exception as e:
            logger.error(f"Error querying tracked symbols for priorities: {e}")

        # Add recently viewed
        for s in self.recently_viewed.keys():
            symbols.add(s)

        # Map to (symbol, priority) and sort
        prioritized = [(s, self.get_symbol_priority(s)) for s in symbols]
        prioritized.sort(key=lambda x: x[1], reverse=True)

        return [x[0] for x in prioritized]


# Singleton instance
priority_queue = PriorityQueueManager()
