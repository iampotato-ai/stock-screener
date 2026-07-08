"""
AI Enrichment controllers exposing non-blocking wrappers around versioned NLP enrichment workers.
"""
import logging
from flask import current_app
from .executor import ThreadedAIEnrichmentExecutor, SyncAIEnrichmentExecutor, AIEnrichmentExecutor

logger = logging.getLogger(__name__)


def get_enrichment_executor() -> AIEnrichmentExecutor:
    """Factory to resolve the active enrichment executor based on application configuration."""
    try:
        # Check if we are inside a Flask context and retrieve config
        if current_app:
            exec_type = current_app.config.get("AI_ENRICHMENT_EXECUTOR", "threaded").strip().lower()
            if exec_type == "sync":
                return SyncAIEnrichmentExecutor()
    except Exception:
        pass
    return ThreadedAIEnrichmentExecutor()


def enrich_article_non_blocking(article_id: int):
    """Spawn a background task to update the news article with NLP metrics.
    Uses the configured AIEnrichmentExecutor.
    """
    get_enrichment_executor().execute_article_enrichment(article_id)


def enrich_event_non_blocking(event_id: int):
    """Spawn a background task to update the corporate event with NLP metrics.
    Uses the configured AIEnrichmentExecutor.
    """
    get_enrichment_executor().execute_event_enrichment(event_id)
