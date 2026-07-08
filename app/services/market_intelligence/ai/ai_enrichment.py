import threading
import logging
from flask import current_app
from app.extensions import db
from app.models import NewsArticle, MarketEvent
from app.services.nlp_service import nlp_service

logger = logging.getLogger(__name__)


def _enrich_article_task(app_instance, article_id: int):
    """Worker task running in a background thread to enrich a news article."""
    with app_instance.app_context():
        try:
            article = NewsArticle.query.get(article_id)
            if not article:
                return

            # Call existing nlp_service to classify and analyze sentiment
            nlp_res = nlp_service.process_announcement(article.title, article.summary or "")
            
            # Map sentiment details
            sentiment_map = {
                "sent-positive": "Positive",
                "sent-negative": "Negative",
                "sent-neutral": "Neutral"
            }
            article.sentiment = sentiment_map.get(nlp_res.get("sent"), "Neutral")
            
            # Confidence score (0-100)
            score = nlp_res.get("nlp_sentiment_score", 0.8)
            article.sentiment_confidence = round(abs(score) * 100, 2)
            
            # Importance mapping
            importance_map = {
                "high": "High",
                "medium": "Medium",
                "low": "Low",
                "critical": "Critical"
            }
            article.importance = importance_map.get(nlp_res.get("imp"), "Medium")
            
            # Add "Why it matters" summary explanation
            article.why_it_matters = f"NLP Classification: tagged as '{nlp_res.get('nlp_category', 'General')}' with {article.sentiment} sentiment. {nlp_res.get('reason', '')}"
            
            db.session.commit()
            logger.info(f"Successfully enriched article ID {article_id} in background.")
        except Exception as e:
            logger.error(f"Failed to enrich article {article_id} in background thread: {e}")


def _enrich_event_task(app_instance, event_id: int):
    """Worker task running in a background thread to enrich a market event."""
    with app_instance.app_context():
        try:
            event = MarketEvent.query.get(event_id)
            if not event:
                return

            # Call nlp_service
            nlp_res = nlp_service.process_announcement(event.title, event.details or "")

            sentiment_map = {
                "sent-positive": "Positive",
                "sent-negative": "Negative",
                "sent-neutral": "Neutral"
            }
            event.sentiment = sentiment_map.get(nlp_res.get("sent"), "Neutral")
            
            score = nlp_res.get("nlp_sentiment_score", 0.8)
            event.sentiment_confidence = round(abs(score) * 100, 2)
            
            importance_map = {
                "high": "High",
                "medium": "Medium",
                "low": "Low",
                "critical": "Critical"
            }
            event.importance = importance_map.get(nlp_res.get("imp"), "Medium")
            event.catalyst_score = nlp_res.get("catalyst_score", 0.0)

            # Generate dynamic "Why it matters" explanation based on event type
            why_it_matters_templates = {
                "DIVIDEND": "Dividends represent direct cash distribution to shareholders, signaling financial strength and cash-flow confidence.",
                "EARNINGS": "Quarterly earnings results show operational growth trajectories, impacting price-to-earnings ratios and core valuation.",
                "SPLIT": "Stock splits lower the nominal price per share, increasing market liquidity and retail investor accessibility.",
                "BONUS": "Bonus issues indicate accumulated reserves capitalized by the company, boosting share count without raising cash.",
                "BULK_DEAL": "Bulk and block deals show institutional actions (FII/DII) often signaling strong backing or exit points.",
                "INSIDER": "Insider promoter transactions show confidence levels from executives who possess deep operational knowledge."
            }
            event.why_it_matters = why_it_matters_templates.get(event.event_type, "Corporate actions directly influence price structures and liquidity pools.")

            db.session.commit()
            logger.info(f"Successfully enriched market event ID {event_id} in background.")
        except Exception as e:
            logger.error(f"Failed to enrich event {event_id} in background thread: {e}")


def enrich_article_non_blocking(article_id: int):
    """Spawn a background thread to update the news article with NLP metrics."""
    try:
        app_instance = current_app._get_current_object()
        t = threading.Thread(target=_enrich_article_task, args=(app_instance, article_id))
        t.daemon = True
        t.start()
    except Exception as e:
        logger.error(f"Could not spawn article enrichment thread: {e}")


def enrich_event_non_blocking(event_id: int):
    """Spawn a background thread to update the corporate event with NLP metrics."""
    try:
        app_instance = current_app._get_current_object()
        t = threading.Thread(target=_enrich_event_task, args=(app_instance, event_id))
        t.daemon = True
        t.start()
    except Exception as e:
        logger.error(f"Could not spawn event enrichment thread: {e}")
