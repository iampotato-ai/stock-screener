from typing import List
from app.models import NewsArticle
from app.extensions import db


class NewsRepository:
    """Isolates database operations for NewsArticle objects."""

    def get_by_symbol(self, symbol: str, limit: int = 20, offset: int = 0) -> List[NewsArticle]:
        """Fetch latest news articles for a symbol, sorted by publication date descending."""
        return (
            NewsArticle.query.filter_by(symbol=symbol)
            .order_by(NewsArticle.published_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def add(self, article: NewsArticle) -> NewsArticle:
        """Add and commit a single news article."""
        db.session.add(article)
        db.session.commit()
        return article

    def bulk_add(self, articles: List[NewsArticle]):
        """Bulk add and commit multiple articles."""
        if not articles:
            return
        db.session.add_all(articles)
        db.session.commit()
