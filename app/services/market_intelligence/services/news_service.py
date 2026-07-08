import logging
from typing import List
from app.models import NewsArticle
from ..providers.manager import ProviderManager
from ..repositories.news_repository import NewsRepository
from ..deduplicator import DataValidator, Deduplicator

logger = logging.getLogger(__name__)


class NewsService:
    """Orchestrates news article ingestion, validation, deduplication, and database storage."""

    def __init__(self):
        self.provider_manager = ProviderManager()
        self.news_repository = NewsRepository()

    def ingest_news_for_symbol(self, symbol: str) -> int:
        """
        Fetch articles from providers, validate, deduplicate, and persist.
        Returns the number of new articles inserted.
        """
        raw_articles = self.provider_manager.fetch_news(symbol)
        new_count = 0
        
        for item in raw_articles:
            # 1. Validate
            if not DataValidator.validate_article(item):
                continue
                
            # 2. Deduplicate
            if Deduplicator.is_news_duplicate(item):
                continue
                
            # 3. Create DB model & save
            db_article = NewsArticle(
                symbol=item.symbol,
                external_id=item.external_id,
                title=item.title,
                url=item.url,
                summary=item.summary,
                source=item.source,
                published_at=item.published_at,
                sentiment="Neutral",  # Default values until AI enrichment runs
                sentiment_confidence=100.0,
                importance="Medium"
            )
            try:
                self.news_repository.add(db_article)
                new_count += 1
                
                # Trigger AI enrichment (non-blocking hook)
                self._trigger_ai_enrichment(db_article)
            except Exception as e:
                logger.error(f"Failed to persist article '{item.title}': {e}")
                
        if new_count > 0:
            try:
                from ..cache.manager import cache_manager
                cache_manager.delete_pattern(f"timeline:{symbol.upper()}:")
            except Exception as e:
                logger.error(f"Failed to invalidate timeline cache for symbol {symbol}: {e}")

        return new_count

    def get_news_for_symbol(self, symbol: str, limit: int = 10) -> List[NewsArticle]:
        """Fetch stored news from the database. Falls back to immediate ingestion if DB is empty."""
        articles = self.news_repository.get_by_symbol(symbol, limit=limit)
        if not articles:
            # Empty database, trigger instant ingest
            self.ingest_news_for_symbol(symbol)
            articles = self.news_repository.get_by_symbol(symbol, limit=limit)
        return articles

    def _trigger_ai_enrichment(self, article: NewsArticle):
        """Trigger AI enrichment for the article (fully implemented in Phase 4)."""
        try:
            from ..ai.ai_enrichment import enrich_article_non_blocking
            enrich_article_non_blocking(article.id)
        except ImportError:
            # Stubbed until enrichment module is written
            pass
        except Exception as e:
            logger.error(f"Failed to trigger AI enrichment: {e}")
