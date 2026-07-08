import time
import logging
from typing import List, Union, Dict, Any
from urllib.error import HTTPError
from .base import BaseDataProvider
from .marketaux import MarketauxProvider
from .google_rss import GoogleRSSProvider
from .nse_rss import NSERSSProvider
from ..schemas.normalized_event import NormalizedArticle, NormalizedEvent
from app.models import NewsFetchLog
from app.extensions import db

logger = logging.getLogger(__name__)


class ProviderManager:
    """Manages news and corporate event providers, handling retries, fallbacks, and health state."""

    def __init__(self):
        # Register providers
        self.news_providers: List[BaseDataProvider] = [
            MarketauxProvider(),
            GoogleRSSProvider()
        ]
        self.event_providers: List[BaseDataProvider] = [
            NSERSSProvider()
        ]

        # Health tracking state
        self.failure_counts: Dict[str, int] = {}
        self.disabled_until: Dict[str, float] = {}
        self.provider_stats: Dict[str, Dict[str, Union[int, list, float, None]]] = {
            "Marketaux": {"successes": 0, "failures": 0, "latencies": [], "last_failure_at": None, "last_success_at": None},
            "GoogleRSS": {"successes": 0, "failures": 0, "latencies": [], "last_failure_at": None, "last_success_at": None},
            "NSERSS": {"successes": 0, "failures": 0, "latencies": [], "last_failure_at": None, "last_success_at": None}
        }

    def fetch_news(self, symbol: str) -> List[NormalizedArticle]:
        """Fetch news articles from healthy providers, falling back sequentially on error."""
        errors = []
        for provider in self.news_providers:
            if not self._is_provider_healthy(provider.name):
                logger.warning(f"Provider {provider.name} is temporarily disabled due to health issues.")
                continue

            try:
                articles = self._fetch_with_retry_and_metrics(provider, symbol)
                # Success resets failure counter
                self.failure_counts[provider.name] = 0
                return articles
            except Exception as e:
                logger.error(f"Provider {provider.name} failed to fetch news for {symbol}: {e}")
                self._record_failure(provider.name)
                errors.append(f"{provider.name}: {e}")

        logger.error(f"All news providers failed for symbol {symbol}. Errors: {errors}")
        return []

    def fetch_events(self, symbol: str) -> List[NormalizedEvent]:
        """Fetch corporate announcements / actions from event providers."""
        errors = []
        for provider in self.event_providers:
            if not self._is_provider_healthy(provider.name):
                logger.warning(f"Provider {provider.name} is temporarily disabled due to health issues.")
                continue

            try:
                events = self._fetch_with_retry_and_metrics(provider, symbol)
                self.failure_counts[provider.name] = 0
                return events
            except Exception as e:
                logger.error(f"Provider {provider.name} failed to fetch events for {symbol}: {e}")
                self._record_failure(provider.name)
                errors.append(f"{provider.name}: {e}")

        return []

    def _is_provider_healthy(self, name: str) -> bool:
        """Check if provider is not disabled."""
        return time.time() >= self.disabled_until.get(name, 0.0)

    def _record_failure(self, name: str):
        """Record consecutive failure and disable if threshold is reached."""
        self.failure_counts[name] = self.failure_counts.get(name, 0) + 1
        if self.failure_counts[name] >= 5:
            # Disable for 15 minutes
            self.disabled_until[name] = time.time() + 900
            logger.error(f"Provider {name} has failed 5 consecutive times. Disabling for 15 minutes.")

    def _fetch_with_retry_and_metrics(
        self, provider: BaseDataProvider, symbol: str
    ) -> List[Union[NormalizedArticle, NormalizedEvent]]:
        """Execute fetch with exponential backoff on retryable HTTP/network errors."""
        max_retries = 3
        backoff_sec = 1.0
        start_time = time.time()
        status = "SUCCESS"
        error_msg = None
        results = []

        for attempt in range(1, max_retries + 1):
            try:
                results = provider.fetch(symbol)
                break
            except HTTPError as e:
                # Retry on 429 (Too Many Requests), 500 (Internal Server Error), 503 (Service Unavailable)
                if e.code in (429, 500, 503) and attempt < max_retries:
                    logger.warning(f"HTTP Error {e.code} on fetch for {provider.name}. Retrying in {backoff_sec}s...")
                    time.sleep(backoff_sec)
                    backoff_sec *= 2.0
                else:
                    status = "ERROR"
                    error_msg = f"HTTP Error {e.code}: {e.reason}"
                    break
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"Connection error on fetch for {provider.name}: {e}. Retrying in {backoff_sec}s...")
                    time.sleep(backoff_sec)
                    backoff_sec *= 2.0
                else:
                    status = "ERROR"
                    error_msg = str(e)
                    break

        latency_ms = int((time.time() - start_time) * 1000)
        
        # Track provider stats in memory
        p_name = provider.name
        if p_name in self.provider_stats:
            stats = self.provider_stats[p_name]
            if status == "SUCCESS":
                stats["successes"] = stats["successes"] + 1
                stats["last_success_at"] = time.time()
                # Rolling list of last 10 latencies
                stats["latencies"].append(latency_ms)
                if len(stats["latencies"]) > 10:
                    stats["latencies"].pop(0)
            else:
                stats["failures"] = stats["failures"] + 1
                stats["last_failure_at"] = time.time()

        self._log_fetch_to_db(provider.name, symbol, status, latency_ms, error_msg, len(results))

        if status == "ERROR" and error_msg:
            raise RuntimeError(f"Provider {provider.name} failed: {error_msg}")

        return results

    def _log_fetch_to_db(self, provider_name: str, symbol: str, status: str, latency_ms: int, error_msg: str = None, records_count: int = 0):
        """Persist fetch metrics to database."""
        try:
            from flask import has_app_context
            if has_app_context():
                log = NewsFetchLog(
                    provider=provider_name,
                    symbol=symbol,
                    status=status,
                    latency_ms=latency_ms,
                    error_message=error_msg,
                    records_count=records_count
                )
                db.session.add(log)
                db.session.commit()
        except Exception as e:
            logger.error(f"Failed to log provider fetch details: {e}")

    def get_provider_health(self) -> Dict[str, Dict[str, Any]]:
        """Return formatted health metrics summary for all registered providers."""
        health = {}
        for p_name, stats in self.provider_stats.items():
            total = stats["successes"] + stats["failures"]
            success_rate = (stats["successes"] / total) if total > 0 else 1.0
            avg_latency = (sum(stats["latencies"]) / len(stats["latencies"])) if stats["latencies"] else 0.0
            
            # check if currently disabled
            is_healthy = self._is_provider_healthy(p_name)
            
            health[p_name] = {
                "success_rate": round(success_rate, 2),
                "average_latency_ms": round(avg_latency, 2),
                "last_success_at": stats["last_success_at"],
                "last_failure_at": stats["last_failure_at"],
                "consecutive_failures": self.failure_counts.get(p_name, 0),
                "is_healthy": is_healthy
            }
        return health
