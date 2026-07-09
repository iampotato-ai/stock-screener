import datetime
from typing import List, Dict, Any, Optional
from app.models import NewsArticle, MarketEvent
from ..repositories.news_repository import NewsRepository
from ..repositories.event_repository import EventRepository
from ..cache.manager import cache_manager


class TimelineService:
    """Aggregates, normalizes, sorts, and groups news and market events into chronological time brackets."""

    def __init__(self):
        self.news_repository = NewsRepository()
        self.event_repository = EventRepository()

    def get_timeline_for_symbol(
        self,
        symbol: str,
        event_types: Optional[List[str]] = None,
        limit: int = 20,
        grouping: str = 'date_bracket',
        sentiment_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves, merges, and groups both news articles and corporate events.
        
        Args:
            symbol: Ticker symbol (e.g. RELIANCE, or ALL, or RELIANCE,INFY)
            event_types: Filter list of event types (e.g. ['news', 'dividend'])
            limit: Limit of entries to pull from DB
            grouping: Chronological grouping format ('date_bracket', 'latest', 'importance', 'sentiment')
            sentiment_filter: Optional filter for positive, negative, or neutral sentiment
            
        Returns:
            Dict containing timeline brackets or grouped items.
        """
        # Fall back safely if grouping is unrecognized
        if grouping not in ('date_bracket', 'latest', 'importance', 'sentiment'):
            grouping = 'date_bracket'

        # Check cache
        event_types_str = ",".join(sorted(event_types)) if event_types else "all"
        cache_key = f"timeline:{symbol.upper()}:{event_types_str}:{limit}:{grouping}:{sentiment_filter or 'none'}"
        cached_result = cache_manager.get(cache_key)
        if cached_result is not None:
            return cached_result

        # Resolve symbols to fetch
        symbol_list = []
        symbol = symbol.strip().upper()
        if symbol == 'ALL':
            from app.models import WatchlistItem, EpWatchlist
            wl_symbols = [w.ticker.upper() for w in WatchlistItem.query.all()]
            ep_symbols = [w.symbol.upper() for w in EpWatchlist.query.filter_by(status='ACTIVE').all()]
            symbol_list = list(set(wl_symbols + ep_symbols))
        elif ',' in symbol:
            symbol_list = [s.strip().upper() for s in symbol.split(',') if s.strip()]
        elif symbol:
            symbol_list = [symbol]

        fetch_news = True
        fetch_events = True
        
        db_event_types = []
        if event_types:
            fetch_news = 'news' in event_types
            db_event_types = [t.upper() for t in event_types if t != 'news']
            fetch_events = len(db_event_types) > 0

        articles = []
        events = []

        if symbol_list:
            # Sync ingestion on-demand ONLY if querying a specific ticker (not symbol list summary) to avoid HTTP timeouts
            trigger_sync_ingest = len(symbol_list) == 1
            try:
                from flask import current_app
                if current_app and current_app.config.get('TESTING'):
                    trigger_sync_ingest = False
            except Exception:
                pass

            if fetch_news:
                from ..services.news_service import NewsService
                ns = NewsService()
                for sym in symbol_list:
                    if trigger_sync_ingest:
                        articles.extend(ns.get_news_for_symbol(sym, limit=limit))
                    else:
                        # Direct DB pull without sync fetch fallback
                        articles.extend(ns.news_repository.get_by_symbol(sym, limit=limit))
                
            if fetch_events:
                from ..services.event_service import EventService
                es = EventService()
                for sym in symbol_list:
                    if trigger_sync_ingest:
                        sym_events = es.get_events_for_symbol(sym, limit=limit)
                    else:
                        sym_events = es.event_repository.get_by_symbol(sym, limit=limit)
                    if db_event_types:
                        sym_events = [e for e in sym_events if e.event_type in db_event_types]
                    events.extend(sym_events)

        merged_list = []
        
        # 1. Normalize news articles
        for a in articles:
            merged_list.append({
                'id': a.id,
                'type': 'news',
                'symbol': a.symbol,
                'title': a.title,
                'description': a.summary,
                'source': a.source or 'News Feed',
                'url': a.url,
                'sentiment': a.sentiment or 'Neutral',
                'sentiment_confidence': a.sentiment_confidence or 100.0,
                'importance': a.importance or 'Medium',
                'why_it_matters': a.why_it_matters or '',
                'date': a.published_at.date() if a.published_at else datetime.date.today(),
                'datetime_sort': a.published_at or datetime.datetime.now()
            })

        # 2. Normalize events
        for e in events:
            dt_sort = datetime.datetime.combine(e.event_date, datetime.time.min)
            merged_list.append({
                'id': e.id,
                'type': e.event_type,  # DIVIDEND, EARNINGS, SPLIT, etc.
                'symbol': e.symbol,
                'title': e.title,
                'description': e.details,
                'source': e.source or 'NSE',
                'url': None,
                'ratio': e.ratio,
                'amount': e.amount,
                'sentiment': e.sentiment or 'Neutral',
                'sentiment_confidence': e.sentiment_confidence or 100.0,
                'importance': e.importance or 'Medium',
                'why_it_matters': e.why_it_matters or '',
                'date': e.event_date,
                'datetime_sort': dt_sort
            })

        # Sort descending by date
        merged_list.sort(key=lambda x: x['datetime_sort'], reverse=True)
        merged_list = merged_list[:limit]

        # Filter by sentiment if sentiment_filter is specified
        if sentiment_filter:
            sf = sentiment_filter.strip().lower()
            merged_list = [item for item in merged_list if item['sentiment'].lower() == sf]

        # Process grouping
        if grouping == 'latest':
            for item in merged_list:
                item_date = item['date']
                item.pop('datetime_sort', None)
                item['date'] = item_date.isoformat()
            timeline = {'latest': merged_list}

        elif grouping == 'importance':
            timeline = {
                'critical': [],
                'high': [],
                'medium': [],
                'low': []
            }
            for item in merged_list:
                item_date = item['date']
                item.pop('datetime_sort', None)
                item['date'] = item_date.isoformat()
                imp = item['importance'].lower()
                if imp in timeline:
                    timeline[imp].append(item)
                else:
                    timeline['medium'].append(item)

        elif grouping == 'sentiment':
            timeline = {
                'positive': [],
                'negative': [],
                'neutral': []
            }
            for item in merged_list:
                item_date = item['date']
                item.pop('datetime_sort', None)
                item['date'] = item_date.isoformat()
                sent = item['sentiment'].lower()
                if sent in timeline:
                    timeline[sent].append(item)
                else:
                    timeline['neutral'].append(item)

        else:
            # default date_bracket grouping
            today_date = datetime.date.today()
            yesterday_date = today_date - datetime.timedelta(days=1)
            one_week_ago = today_date - datetime.timedelta(days=7)

            timeline = {
                'today': [],
                'yesterday': [],
                'last_week': [],
                'earlier': []
            }

            for item in merged_list:
                item_date = item['date']
                item.pop('datetime_sort', None)
                item['date'] = item_date.isoformat()

                if item_date == today_date:
                    timeline['today'].append(item)
                elif item_date == yesterday_date:
                    timeline['yesterday'].append(item)
                elif item_date >= one_week_ago:
                    timeline['last_week'].append(item)
                else:
                    timeline['earlier'].append(item)

        cache_manager.set(cache_key, timeline, timeout=60)
        return timeline
