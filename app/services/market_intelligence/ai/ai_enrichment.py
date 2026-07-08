"""
AI Enrichment controllers exposing non-blocking wrappers around versioned NLP enrichment workers.
"""
import logging
from .executor import ThreadedAIEnrichmentExecutor

logger = logging.getLogger(__name__)

# Default singleton executor (can be swapped/patched in custom settings or test runs)
ai_enrichment_executor = ThreadedAIEnrichmentExecutor()


def enrich_article_non_blocking(article_id: int):
    """Spawn a background task to update the news article with NLP metrics.
    Uses the configured AIEnrichmentExecutor.
    """
    ai_enrichment_executor.execute_article_enrichment(article_id)


def enrich_event_non_blocking(event_id: int):
    """Spawn a background task to update the corporate event with NLP metrics.
    Uses the configured AIEnrichmentExecutor.
    """
    ai_enrichment_executor.execute_event_enrichment(event_id)
