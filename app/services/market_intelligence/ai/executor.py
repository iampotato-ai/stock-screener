import logging
import threading
from abc import ABC, abstractmethod
from flask import current_app
from .worker import EnrichmentWorker

logger = logging.getLogger(__name__)

class AIEnrichmentExecutor(ABC):
    """Abstract executor for executing background AI enrichment tasks."""

    @abstractmethod
    def execute_article_enrichment(self, article_id: int):
        """Trigger background enrichment for a news article."""
        pass

    @abstractmethod
    def execute_event_enrichment(self, event_id: int):
        """Trigger background enrichment for a corporate event."""
        pass


class ThreadedAIEnrichmentExecutor(AIEnrichmentExecutor):
    """Implementation of AIEnrichmentExecutor running tasks in background daemon threads."""

    def __init__(self, worker: EnrichmentWorker = None):
        self.worker = worker or EnrichmentWorker()

    def execute_article_enrichment(self, article_id: int):
        """Spawn a background thread to enrich the article."""
        try:
            app_instance = current_app._get_current_object()
            t = threading.Thread(
                target=self._enrich_article_task,
                args=(app_instance, article_id)
            )
            t.daemon = True
            t.start()
        except Exception as e:
            logger.error(f"ThreadedAIEnrichmentExecutor: Failed to spawn article enrichment thread: {e}")

    def execute_event_enrichment(self, event_id: int):
        """Spawn a background thread to enrich the event."""
        try:
            app_instance = current_app._get_current_object()
            t = threading.Thread(
                target=self._enrich_event_task,
                args=(app_instance, event_id)
            )
            t.daemon = True
            t.start()
        except Exception as e:
            logger.error(f"ThreadedAIEnrichmentExecutor: Failed to spawn event enrichment thread: {e}")

    def _enrich_article_task(self, app_instance, article_id: int):
        """Wrapper task running inside Flask app context."""
        with app_instance.app_context():
            try:
                self.worker.enrich_article(article_id)
            except Exception as e:
                logger.error(f"ThreadedAIEnrichmentExecutor: Background article enrichment failed: {e}")

    def _enrich_event_task(self, app_instance, event_id: int):
        """Wrapper task running inside Flask app context."""
        with app_instance.app_context():
            try:
                self.worker.enrich_event(event_id)
            except Exception as e:
                logger.error(f"ThreadedAIEnrichmentExecutor: Background event enrichment failed: {e}")


class SyncAIEnrichmentExecutor(AIEnrichmentExecutor):
    """Synchronous executor for executing AI enrichment immediately (useful in testing or sync environments)."""

    def __init__(self, worker: EnrichmentWorker = None):
        self.worker = worker or EnrichmentWorker()

    def execute_article_enrichment(self, article_id: int):
        """Immediately enrich the news article synchronously."""
        try:
            self.worker.enrich_article(article_id)
        except Exception as e:
            logger.error(f"SyncAIEnrichmentExecutor: Article enrichment failed: {e}")

    def execute_event_enrichment(self, event_id: int):
        """Immediately enrich the corporate event synchronously."""
        try:
            self.worker.enrich_event(event_id)
        except Exception as e:
            logger.error(f"SyncAIEnrichmentExecutor: Event enrichment failed: {e}")
