"""
News service compatibility wrapper routing legacy operations to the new Market Intelligence module.
"""
from typing import List, Dict, Any
from app.services.market_intelligence.services.news_service import NewsService as MINewsService


class NewsService:
    """Compatibility wrapper routing legacy news operations to the new Market Intelligence module."""

    def __init__(self):
        self.mi_news_service = MINewsService()

    def get_news_for_symbol(self, symbol: str) -> Dict[str, Any]:
        """Fetch news for a symbol using the new Market Intelligence module."""
        if symbol.startswith("NSE:"):
            symbol = symbol[4:]
        symbol = symbol.strip().upper()
        if not symbol:
            return {"symbol": symbol, "news": []}

        # Mark viewed in priority queue for scheduling priority decay
        from app.services.market_intelligence.jobs.priority_queue import priority_queue
        priority_queue.mark_viewed(symbol)

        # Query database/providers via the new MI NewsService
        articles = self.mi_news_service.get_news_for_symbol(symbol)
        
        # Format back to legacy dictionary structure for compatibility
        legacy_list = []
        for a in articles:
            legacy_list.append({
                'title': a.title,
                'link': a.url,
                'pub_date': a.published_at.strftime('%Y-%m-%d %H:%M:%S') if a.published_at else '',
                'source': a.source
            })
            
        return {"symbol": symbol, "news": legacy_list}


# Singleton instance for backward compatibility
news_service = NewsService()