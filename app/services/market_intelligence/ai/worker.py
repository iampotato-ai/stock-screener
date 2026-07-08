import logging
from app.models import NewsArticle, MarketEvent
from app.services.nlp_service import nlp_service
from app.extensions import db
from .mapper import NLPMapper

logger = logging.getLogger(__name__)

class EnrichmentWorker:
    """Synchronous worker that performs NLP enrichment on news articles and corporate events.
    Decoupled from Flask globals (like current_app) to facilitate unit testing and custom execution.
    """

    def __init__(self, session=None, nlp=None):
        self.session = session or db.session
        self.nlp = nlp or nlp_service

    def enrich_article(self, article_id: int):
        """Enrich a news article with NLP metrics."""
        try:
            # Query the article using the session.
            # Using session.get() which is SQLAlchemy 2.0 compliant instead of Query.get()
            article = self.session.get(NewsArticle, article_id)
            if not article:
                logger.warning(f"EnrichmentWorker: Article {article_id} not found.")
                return

            # Process news with NLP Service
            nlp_res = self.nlp.process_announcement(article.title, article.summary or "")
            
            # Map parameters
            article.sentiment = NLPMapper.map_sentiment(nlp_res.get("sent"))
            article.sentiment_confidence = NLPMapper.map_confidence(nlp_res.get("nlp_sentiment_score"))
            article.importance = NLPMapper.map_importance(nlp_res.get("imp"))
            
            # Generate friendly summary and track version
            article.why_it_matters = NLPMapper.generate_explanation(
                event_or_category="NEWS",
                sentiment=article.sentiment,
                category=nlp_res.get("nlp_category"),
                reason=nlp_res.get("reason")
            )
            article.ai_version = NLPMapper.AI_VERSION

            self.session.commit()
            logger.info(f"EnrichmentWorker: Successfully enriched news article ID {article_id}.")
        except Exception as e:
            self.session.rollback()
            logger.error(f"EnrichmentWorker: Failed to enrich article {article_id}: {e}")
            raise

    def enrich_event(self, event_id: int):
        """Enrich a corporate event with NLP metrics."""
        try:
            # Query the event using the session
            event = self.session.get(MarketEvent, event_id)
            if not event:
                logger.warning(f"EnrichmentWorker: Event {event_id} not found.")
                return

            # Process event with NLP Service
            nlp_res = self.nlp.process_announcement(event.title, event.details or "")
            
            # Map parameters
            event.sentiment = NLPMapper.map_sentiment(nlp_res.get("sent"))
            event.sentiment_confidence = NLPMapper.map_confidence(nlp_res.get("nlp_sentiment_score"))
            event.importance = NLPMapper.map_importance(nlp_res.get("imp"))
            event.catalyst_score = nlp_res.get("catalyst_score", 0.0)

            # Generate friendly explanation and track version
            event.why_it_matters = NLPMapper.generate_explanation(
                event_or_category=event.event_type,
                sentiment=event.sentiment
            )
            event.ai_version = NLPMapper.AI_VERSION

            self.session.commit()
            logger.info(f"EnrichmentWorker: Successfully enriched market event ID {event_id}.")
        except Exception as e:
            self.session.rollback()
            logger.error(f"EnrichmentWorker: Failed to enrich event {event_id}: {e}")
            raise
