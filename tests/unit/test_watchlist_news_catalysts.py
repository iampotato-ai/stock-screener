import pytest
import time
import tempfile
import os
from unittest.mock import patch, MagicMock

# Setup the test DB mock first, before app modules are imported
db_fd, db_path = tempfile.mkstemp()

from app.services.market_intelligence.providers.yahoo_finance import YahooFinanceProvider
from app.services.market_intelligence.providers.manager import ProviderManager
from app.services.ai_service import ai_service
from app.services.news_service import news_service


@pytest.fixture(scope="module", autouse=True)
def cleanup_temp_db():
    from app.database import init_db_standalone
    init_db_standalone(db_path)
    yield
    try:
        os.close(db_fd)
        os.unlink(db_path)
    except OSError:
        pass


class TestWatchlistNewsCatalysts:
    """Unit tests for the Watchlist News & Catalysts features."""

    @pytest.fixture(autouse=True)
    def clear_nim_cache(self):
        """Clear the in-memory NIM cache before each test."""
        ai_service.nim_news_cache.clear()

    @patch("yfinance.Ticker")
    def test_yahoo_finance_provider_filtering(self, mock_ticker):
        """Test YahooFinanceProvider fetches, normalizes, and filters articles correctly."""
        mock_instance = MagicMock()
        mock_ticker.return_value = mock_instance
        
        # Mock raw news array returned by yfinance
        now_ts = int(time.time())
        mock_instance.news = [
            # Matches relatedTickers suffix .NS
            {
                "uuid": "uuid1",
                "title": "Reliance Industries Q1 Results",
                "publisher": "CNBC-TV18",
                "link": "https://example.com/rel1",
                "providerPublishTime": now_ts - 3600,
                "relatedTickers": ["RELIANCE.NS", "RELIANCE"]
            },
            # Matches title regex INFY
            {
                "uuid": "uuid2",
                "title": "Infosys (INFY) shares jump on strong outlook",
                "publisher": "Economic Times",
                "link": "https://example.com/infy1",
                "providerPublishTime": now_ts - 7200,
                "relatedTickers": ["INFY.NS", "INFY"]
            },
            # Unrelated - should be filtered out
            {
                "uuid": "uuid3",
                "title": "Apple launches new iPhone",
                "publisher": "TechCrunch",
                "link": "https://example.com/apple1",
                "providerPublishTime": now_ts - 10800,
                "relatedTickers": ["AAPL"]
            }
        ]

        provider = YahooFinanceProvider()
        
        # Test fetching INFY: should keep the second, filter out others (first has RELIANCE, third Apple)
        articles = provider.fetch("INFY")
        assert len(articles) == 1
        assert articles[0].title == "Infosys (INFY) shares jump on strong outlook"
        assert articles[0].source == "Economic Times"
        assert articles[0].external_id == "yfinance-uuid2"

        # Test fetching RELIANCE: should keep the first, filter out others
        articles_rel = provider.fetch("RELIANCE")
        assert len(articles_rel) == 1
        assert articles_rel[0].title == "Reliance Industries Q1 Results"

    @patch("app.services.market_intelligence.providers.yahoo_finance.YahooFinanceProvider.fetch")
    @patch("app.services.market_intelligence.providers.google_rss.GoogleRSSProvider.fetch")
    def test_news_provider_waterfall_fallback(self, mock_rss_fetch, mock_yf_fetch):
        """Test that ProviderManager falls back correctly in the waterfall."""
        # Primary provider YahooFinance throws an error
        mock_yf_fetch.side_effect = RuntimeError("YFinance Rate Limited")
        
        # Fallback provider GoogleRSS returns a result
        from app.services.market_intelligence.schemas.normalized_event import NormalizedArticle
        import datetime
        mock_rss_fetch.return_value = [
            NormalizedArticle(
                symbol="TCS",
                title="TCS Google RSS News",
                url="https://rss.example.com/tcs",
                published_at=datetime.datetime.now(datetime.timezone.utc),
                source="Google News",
                external_id="googlerss-test1"
            )
        ]

        manager = ProviderManager()
        
        # Check that fetch_news falls back to GoogleRSS and returns its articles
        # (Must mock logging fetch to DB to avoid DB session errors in unit tests)
        with patch.object(manager, "_log_fetch_to_db"):
            articles = manager.fetch_news("TCS")
            assert len(articles) == 1
            assert articles[0].title == "TCS Google RSS News"
            assert articles[0].source == "Google News"

    @patch("app.services.ai_service.AIService.callNvidiaNimWithRetry")
    def test_ai_catalyst_analysis_and_caching(self, mock_nim, flask_app):
        """Test NIM news analysis, caching, and 5-minute expiration."""
        mock_nim.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"sentiment": "sent-positive", "summary": "NIM Catalyst explanation"}'
                    }
                }
            ]
        }

        with flask_app.app_context():
            articles = [{"title": "TCS profit rises", "source": "Reuters", "summary": "TCS reports 10% profit growth"}]
            
            # First call triggers API call
            res1 = ai_service.analyze_news_catalysts("TCS", articles)
            assert res1["sentiment"] == "sent-positive"
            assert res1["summary"] == "NIM Catalyst explanation"
            assert mock_nim.call_count == 1

            # Second call should be served from cache
            res2 = ai_service.analyze_news_catalysts("TCS", articles)
            assert res2["sentiment"] == "sent-positive"
            assert res2["summary"] == "NIM Catalyst explanation"
            assert mock_nim.call_count == 1 # API count is still 1

            # Expire the cache entry manually
            ai_service.nim_news_cache["TCS"]["timestamp"] = time.time() - 301
            
            # Third call should trigger another API call
            res3 = ai_service.analyze_news_catalysts("TCS", articles)
            assert res3["sentiment"] == "sent-positive"
            assert mock_nim.call_count == 2

    @patch("app.services.ai_service.AIService.callNvidiaNimWithRetry")
    @patch("app.services.ai_service.AIService._call_gemini")
    def test_ai_catalyst_fallback_to_gemini(self, mock_gemini, mock_nim, flask_app):
        """Test fallback to Gemini when NVIDIA NIM fails."""
        mock_nim.return_value = None # NIM fails
        mock_gemini.return_value = '{"sentiment": "sent-negative", "summary": "Gemini fallback explanation"}'

        with flask_app.app_context():
            articles = [{"title": "TCS margins contract", "source": "Reuters"}]
            res = ai_service.analyze_news_catalysts("TCS", articles)
            
            assert res["sentiment"] == "sent-negative"
            assert res["summary"] == "Gemini fallback explanation"
            assert mock_nim.call_count == 1
            assert mock_gemini.call_count == 1

    @patch("app.services.news_service.news_service.mi_news_service.get_news_for_symbol")
    @patch("app.services.ai_service.ai_service.analyze_news_catalysts")
    def test_news_service_compatibility_wrapper(self, mock_analyze, mock_get_news):
        """Test news_service returns unified news, sentiment, and summary."""
        from app.models import NewsArticle
        import datetime
        
        # Mock database articles returned by MI news service
        mock_get_news.return_value = [
            NewsArticle(
                id=123,
                symbol="INFY",
                external_id="yf-1",
                title="Infosys Q1 results",
                url="https://example.com/infy",
                summary="Infosys reports strong growth",
                source="CNBC",
                published_at=datetime.datetime.now()
            )
        ]
        
        # Mock AI analysis response
        mock_analyze.return_value = {
            "sentiment": "sent-positive",
            "summary": "AI synthesized catalyst description"
        }

        # Call compatibility wrapper
        result = news_service.get_news_for_symbol("INFY")
        
        assert result["symbol"] == "INFY"
        assert len(result["news"]) == 1
        assert result["news"][0]["title"] == "Infosys Q1 results"
        assert result["sentiment"] == "sent-positive"
        assert result["summary"] == "AI synthesized catalyst description"
