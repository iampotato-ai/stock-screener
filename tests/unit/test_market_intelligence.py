import datetime
import time
import gc
from unittest.mock import MagicMock, patch
import pytest

from app.models import NewsArticle, MarketEvent, NewsFetchLog, WatchlistItem, EpWatchlist, TradeJournal, MomentumScore
from app.extensions import db
from app.services.market_intelligence.deduplicator import DataValidator, Deduplicator
from app.services.market_intelligence.schemas.normalized_event import NormalizedArticle, NormalizedEvent
from app.services.market_intelligence.jobs.priority_queue import PriorityQueueManager
from app.services.market_intelligence.timeline.timeline_service import TimelineService
from app.services.market_intelligence.providers.manager import ProviderManager
from app.services.market_intelligence.services.news_service import NewsService
from app.services.market_intelligence.services.event_service import EventService


@pytest.fixture
def mi_app(temp_db_path):
    """Create a Flask app configured with a shared file-based database for tests."""
    from app import create_app
    app = create_app('testing', overrides={
        'DATABASE': temp_db_path,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{temp_db_path}',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'TESTING': True,
    })
    with app.app_context():
        from app.database import init_db_app
        init_db_app()
        db.create_all()
        yield app
        
        # Clean up database resources to release file locks on Windows
        db.session.remove()
        try:
            db.engine.dispose()
        except Exception:
            pass
        from flask import g
        if hasattr(g, 'db') and g.db:
            try:
                g.db.close()
            except Exception:
                pass
    
    # Run garbage collection to clean up any un-finalized SQLite connections
    gc.collect()


def test_data_validator_article():
    """Test DataValidator.validate_article with valid and invalid inputs."""
    # Test valid article
    valid_art = NormalizedArticle(
        symbol="TATA",
        title="Tata Motors Q1 Result",
        url="https://example.com/tata",
        summary="Tata Motors posts profit",
        source="Reuters",
        published_at=datetime.datetime.now(datetime.timezone.utc),
        external_id="ext-tata-1"
    )
    assert DataValidator.validate_article(valid_art) is True

    # Test invalid article (missing symbol)
    invalid_art = NormalizedArticle(
        symbol="",
        title="Tata Motors Q1 Result",
        url="https://example.com/tata",
        summary="Tata Motors posts profit",
        source="Reuters",
        published_at=datetime.datetime.now(datetime.timezone.utc),
        external_id="ext-tata-1"
    )
    assert DataValidator.validate_article(invalid_art) is False

    # Test invalid article (invalid url)
    invalid_art.symbol = "TATA"
    invalid_art.url = "invalid_url"
    assert DataValidator.validate_article(invalid_art) is False


def test_data_validator_event():
    """Test DataValidator.validate_event with valid and invalid inputs."""
    # Test valid event
    valid_event = NormalizedEvent(
        symbol="INFY",
        event_type="DIVIDEND",
        title="Infosys Dividend",
        details="Infosys declares dividend of Rs 20",
        event_date=datetime.date.today(),
        amount=20.0,
        ratio=None,
        external_id="ext-infy-div"
    )
    assert DataValidator.validate_event(valid_event) is True

    # Test invalid event type
    invalid_event = NormalizedEvent(
        symbol="INFY",
        event_type="LAUNCH",  # Invalid type
        title="Infosys Dividend",
        details="Infosys declares dividend of Rs 20",
        event_date=datetime.date.today(),
        amount=20.0,
        ratio=None,
        external_id="ext-infy-div"
    )
    assert DataValidator.validate_event(invalid_event) is False


def test_deduplicator(mi_app):
    """Test Deduplicator duplicate detection against database state."""
    with mi_app.app_context():
        # Clear existing
        NewsArticle.query.delete()
        MarketEvent.query.delete()
        db.session.commit()

        # Check news duplicate
        art = NormalizedArticle(
            symbol="INFY",
            title="Infosys Q3 Profits",
            url="https://infosys.com/q3",
            summary="Infosys profits beat expectations",
            source="Internal",
            published_at=datetime.datetime.now(datetime.timezone.utc),
            external_id="infy-q3-id"
        )
        assert Deduplicator.is_news_duplicate(art) is False

        # Add to DB
        db_art = NewsArticle(
            symbol=art.symbol,
            external_id=art.external_id,
            title=art.title,
            url=art.url,
            summary=art.summary,
            source=art.source,
            published_at=art.published_at
        )
        db.session.add(db_art)
        db.session.commit()

        # Check duplicate again
        assert Deduplicator.is_news_duplicate(art) is True

        # Check event duplicate
        event = NormalizedEvent(
            symbol="RELIANCE",
            event_type="BOARD_MEETING",
            title="Reliance Board Meet",
            details="To discuss quarterly results",
            event_date=datetime.date.today(),
            amount=None,
            ratio=None,
            external_id="rel-meet-1"
        )
        assert Deduplicator.is_event_duplicate(event) is False

        # Add to DB
        unique_hash = Deduplicator.generate_event_hash(event)
        db_event = MarketEvent(
            symbol=event.symbol,
            external_id=event.external_id,
            event_type=event.event_type,
            event_date=event.event_date,
            title=event.title,
            details=event.details,
            unique_hash=unique_hash
        )
        db.session.add(db_event)
        db.session.commit()

        # Check duplicate again
        assert Deduplicator.is_event_duplicate(event) is True


def test_priority_queue(mi_app):
    """Test PriorityQueueManager priority score and decay logic."""
    with mi_app.app_context():
        # Clear
        WatchlistItem.query.delete()
        EpWatchlist.query.delete()
        MomentumScore.query.delete()
        TradeJournal.query.delete()
        db.session.commit()

        pq = PriorityQueueManager()
        
        # Test Default
        assert pq.get_symbol_priority("TEST1") == 20

        # Test Recently Viewed
        pq.mark_viewed("TEST1")
        assert pq.get_symbol_priority("TEST1") == 70

        # Mock time to test decay
        with patch('time.time', return_value=time.time() + 90000):
            assert pq.get_symbol_priority("TEST1") == 20

        # Test Portfolio Item
        journal = TradeJournal(
            id="trade-1",
            ticker="PORTFOLIO1",
            name="Portfolio Stock",
            date="2024-01-01",
            setupLabel="Test",
            swingband="Strong",
            entry=100.0,
            stop=90.0,
            target1=110.0,
            target2=120.0,
            target3=130.0,
            riskAmount=10.0,
            qty=1,
            status="Active"
        )
        db.session.add(journal)
        db.session.commit()
        assert pq.get_symbol_priority("PORTFOLIO1") == 80

        # Test Momentum Score Item
        score = MomentumScore(
            symbol="MOMENTUM1",
            date=datetime.date.today(),
            total_score=95,
            technical_score=25,
            fundamental_score=20,
            momentum_score=15,
            institutional_score=10,
            risk_liquidity_score=5,
            badges="[]"
        )
        db.session.add(score)
        db.session.commit()
        assert pq.get_symbol_priority("MOMENTUM1") == 90

        # Test Watchlist Item
        section_id = "test-sec"
        # Check if section exists or insert
        from app.database import execute_query
        execute_query("INSERT OR IGNORE INTO watchlist_sections (id, name) VALUES (?, ?)", (section_id, "Test Sec"), commit=True)
        
        wl_item = WatchlistItem(
            section_id=section_id,
            ticker="WATCHLIST1"
        )
        db.session.add(wl_item)
        db.session.commit()
        assert pq.get_symbol_priority("WATCHLIST1") == 100


def test_timeline_service(mi_app):
    """Test TimelineService grouping events into Today, Yesterday, Last Week, Earlier."""
    with mi_app.app_context():
        # Clear
        NewsArticle.query.delete()
        MarketEvent.query.delete()
        db.session.commit()

        # Insert news and events for different brackets
        today = datetime.datetime.now()
        yesterday = today - datetime.timedelta(days=1)
        three_days_ago = today - datetime.timedelta(days=3)
        ten_days_ago = today - datetime.timedelta(days=10)

        # 1. News
        art1 = NewsArticle(
            symbol="RELIANCE",
            external_id="news-1",
            title="Reliance Q1 Profit Up",
            url="https://example.com/rel1",
            published_at=today
        )
        art2 = NewsArticle(
            symbol="RELIANCE",
            external_id="news-2",
            title="Reliance Launches New Energy Project",
            url="https://example.com/rel2",
            published_at=three_days_ago
        )
        db.session.add_all([art1, art2])

        # 2. Events
        ev1 = MarketEvent(
            symbol="RELIANCE",
            external_id="ev-1",
            event_type="DIVIDEND",
            event_date=yesterday.date(),
            title="Reliance Declares Dividend",
            unique_hash="hash-1"
        )
        ev2 = MarketEvent(
            symbol="RELIANCE",
            external_id="ev-2",
            event_type="BOARD_MEETING",
            event_date=ten_days_ago.date(),
            title="Reliance Board Meeting",
            unique_hash="hash-2"
        )
        db.session.add_all([ev1, ev2])
        db.session.commit()

        ts = TimelineService()
        timeline = ts.get_timeline_for_symbol("RELIANCE")

        # Verify timeline brackets
        assert len(timeline["today"]) == 1
        assert timeline["today"][0]["title"] == "Reliance Q1 Profit Up"

        assert len(timeline["yesterday"]) == 1
        assert timeline["yesterday"][0]["title"] == "Reliance Declares Dividend"

        assert len(timeline["last_week"]) == 1
        assert timeline["last_week"][0]["title"] == "Reliance Launches New Energy Project"

        assert len(timeline["earlier"]) == 1
        assert timeline["earlier"][0]["title"] == "Reliance Board Meeting"


def test_api_endpoints(mi_app):
    """Test API controller endpoints for events and news."""
    client = mi_app.test_client()

    with mi_app.app_context():
        # Clear
        NewsArticle.query.delete()
        MarketEvent.query.delete()
        db.session.commit()

        # Add article and event
        art = NewsArticle(
            symbol="TCS",
            external_id="tcs-news",
            title="TCS News Today",
            url="https://example.com/tcs",
            published_at=datetime.datetime.now()
        )
        ev = MarketEvent(
            symbol="TCS",
            external_id="tcs-ev",
            event_type="EARNINGS",
            event_date=datetime.date.today(),
            title="TCS Q1 Earnings Announcement",
            unique_hash="tcs-hash"
        )
        db.session.add_all([art, ev])
        db.session.commit()

    # Test GET /api/v1/events
    response = client.get('/api/v1/events?symbol=TCS')
    assert response.status_code == 200
    data = response.get_json()
    assert "data" in data
    assert "today" in data["data"]
    assert len(data["data"]["today"]) == 2

    # Test GET /api/v1/news (legacy backward compatibility)
    response_news = client.get('/api/v1/news?symbol=TCS')
    assert response_news.status_code == 200
    data_news = response_news.get_json()
    assert data_news["success"] is True
    assert len(data_news["data"]["news"]) == 1
    assert data_news["data"]["news"][0]["title"] == "TCS News Today"


def test_provider_manager_and_ingestion(mi_app):
    """Test ProviderManager news ingestion and repository persistence."""
    # Mock MarketauxProvider and GoogleRSSProvider
    with patch('app.services.market_intelligence.providers.manager.MarketauxProvider') as mock_marketaux, \
         patch('app.services.market_intelligence.providers.manager.GoogleRSSProvider') as mock_google, \
         patch('app.services.market_intelligence.ai.ai_enrichment.enrich_article_non_blocking') as mock_enrich:
        
        m_inst = mock_marketaux.return_value
        g_inst = mock_google.return_value
        
        # Mock properties and methods
        m_inst.name = "Marketaux"
        g_inst.name = "GoogleRSS"
        
        # primary returns articles
        m_inst.fetch.return_value = [
            NormalizedArticle(
                symbol="WIPRO",
                title="Wipro Expands Operations",
                url="https://wipro.com/news1",
                summary="Wipro grows",
                source="PR",
                published_at=datetime.datetime.now(datetime.timezone.utc),
                external_id="wipro-1"
            )
        ]
        
        with mi_app.app_context():
            ns = NewsService()
            inserted = ns.ingest_news_for_symbol("WIPRO")
            assert inserted == 1

            # Check DB
            saved = NewsArticle.query.filter_by(symbol="WIPRO").all()
            assert len(saved) == 1
            assert saved[0].title == "Wipro Expands Operations"


def test_nlp_mapper():
    """Test NLPMapper translations, rounding, and investor-friendly summary generation."""
    from app.services.market_intelligence.ai.mapper import NLPMapper
    
    # Sentiment mappings
    assert NLPMapper.map_sentiment("sent-positive") == "Positive"
    assert NLPMapper.map_sentiment("sent-negative") == "Negative"
    assert NLPMapper.map_sentiment("sent-neutral") == "Neutral"
    assert NLPMapper.map_sentiment(None) == "Neutral"

    # Confidence rounding
    assert NLPMapper.map_confidence(0.8543) == 85.43
    assert NLPMapper.map_confidence(-0.5) == 50.0
    assert NLPMapper.map_confidence(None) == 100.0

    # Importance mappings
    assert NLPMapper.map_importance("high") == "High"
    assert NLPMapper.map_importance("critical") == "Critical"
    assert NLPMapper.map_importance(None) == "Medium"

    # Explanations
    assert "dividend" in NLPMapper.generate_explanation("DIVIDEND", "Positive").lower()
    assert "liquidity" in NLPMapper.generate_explanation("SPLIT", "Neutral").lower()
    assert "earnings" in NLPMapper.generate_explanation("EARNINGS", "Positive").lower()
    assert "structural restructuring" in NLPMapper.generate_explanation("NEWS", "Positive", category="merger").lower()
    assert "outlook" in NLPMapper.generate_explanation("NEWS", "Positive", reason="Strong Q3").lower()


def test_enrichment_worker(mi_app):
    """Test EnrichmentWorker decoupled NLP extraction and metadata versioning."""
    from app.services.market_intelligence.ai.worker import EnrichmentWorker
    
    with mi_app.app_context():
        # Insert a raw article and raw event
        art = NewsArticle(
            symbol="INFY",
            external_id="infy-raw-1",
            title="Infosys announces huge news",
            url="https://example.com/infy-raw",
            published_at=datetime.datetime.now()
        )
        ev = MarketEvent(
            symbol="INFY",
            external_id="infy-raw-ev-1",
            event_type="DIVIDEND",
            event_date=datetime.date.today(),
            title="Infosys massive payout",
            unique_hash="hash-infy-raw-ev"
        )
        db.session.add_all([art, ev])
        db.session.commit()

        # Mock NLP Service
        mock_nlp = MagicMock()
        mock_nlp.process_announcement.return_value = {
            "sent": "sent-positive",
            "nlp_sentiment_score": 0.95,
            "imp": "high",
            "nlp_category": "catalyst",
            "reason": "Expanding into cloud sector",
            "catalyst_score": 8.5
        }

        # Run worker
        worker = EnrichmentWorker(session=db.session, nlp=mock_nlp)
        worker.enrich_article(art.id)
        worker.enrich_event(ev.id)

        # Refresh from DB
        db.session.refresh(art)
        db.session.refresh(ev)

        # Asserts
        assert art.sentiment == "Positive"
        assert art.sentiment_confidence == 95.0
        assert art.importance == "High"
        assert "confidence" in ev.why_it_matters.lower() # DIVIDEND template description
        assert art.ai_version == "v1"
        assert ev.ai_version == "v1"
        assert ev.catalyst_score == 8.5


def test_cache_providers():
    """Test MemoryCacheProvider, NoCacheProvider, and CacheManager abstraction."""
    from app.services.market_intelligence.cache.memory import MemoryCacheProvider
    from app.services.market_intelligence.cache.no_cache import NoCacheProvider
    from app.services.market_intelligence.cache.manager import CacheManager

    # Memory Cache Provider
    mem = MemoryCacheProvider()
    mem.set("test_key", "hello", timeout=1)
    assert mem.get("test_key") == "hello"
    
    # Expiration
    with patch('time.time', return_value=time.time() + 5):
        assert mem.get("test_key") is None

    # No Cache Provider
    no_c = NoCacheProvider()
    no_c.set("test_key", "hello")
    assert no_c.get("test_key") is None

    # Cache Manager
    cm = CacheManager(provider=mem)
    cm.set("mgr_key", "mgr_val")
    assert cm.get("mgr_key") == "mgr_val"
    cm.delete("mgr_key")
    assert cm.get("mgr_key") is None


def test_provider_health_metrics(mi_app):
    """Test ProviderManager records successes, failures, latencies, and exposes get_provider_health."""
    with mi_app.app_context(), \
         patch('app.services.market_intelligence.providers.manager.MarketauxProvider') as mock_marketaux, \
         patch('app.services.market_intelligence.providers.manager.GoogleRSSProvider') as mock_google:
         
         m_inst = mock_marketaux.return_value
         g_inst = mock_google.return_value
         m_inst.name = "Marketaux"
         g_inst.name = "GoogleRSS"

         # Successful fetch
         m_inst.fetch.return_value = []
         
         pm = ProviderManager()
         # force run fetch inside the retry wrapper
         pm._fetch_with_retry_and_metrics(m_inst, "RELIANCE")

         # Failed fetch
         g_inst.fetch.side_effect = Exception("Network Down")
         try:
             pm._fetch_with_retry_and_metrics(g_inst, "RELIANCE")
         except RuntimeError:
             pass
         pm._record_failure(g_inst.name)

         health = pm.get_provider_health()
         
         # Assert Marketaux is successful
         assert health["Marketaux"]["success_rate"] == 1.0
         assert health["Marketaux"]["consecutive_failures"] == 0
         assert health["Marketaux"]["is_healthy"] is True

         # Assert GoogleRSS has failure
         assert health["GoogleRSS"]["success_rate"] == 0.0
         assert health["GoogleRSS"]["consecutive_failures"] == 1


def test_timeline_grouping_and_filtering(mi_app):
    """Test TimelineService custom grouping and sentiment filtering options."""
    with mi_app.app_context():
        # Clear
        NewsArticle.query.delete()
        MarketEvent.query.delete()
        db.session.commit()

        # Insert mixed items
        art1 = NewsArticle(
            symbol="INFY",
            external_id="infy-1",
            title="Infosys Up on Positive Q3",
            url="https://example.com/infy-1",
            sentiment="Positive",
            importance="High",
            published_at=datetime.datetime.now()
        )
        art2 = NewsArticle(
            symbol="INFY",
            external_id="infy-2",
            title="Infosys Down on Layoffs",
            url="https://example.com/infy-2",
            sentiment="Negative",
            importance="Critical",
            published_at=datetime.datetime.now()
        )
        db.session.add_all([art1, art2])
        db.session.commit()

        ts = TimelineService()

        # Test Sentiment Filtering
        res_pos = ts.get_timeline_for_symbol("INFY", sentiment_filter="positive")
        assert len(res_pos["today"]) == 1
        assert res_pos["today"][0]["title"] == "Infosys Up on Positive Q3"

        res_neg = ts.get_timeline_for_symbol("INFY", sentiment_filter="negative")
        assert len(res_neg["today"]) == 1
        assert res_neg["today"][0]["title"] == "Infosys Down on Layoffs"

        # Test Importance Grouping
        res_imp = ts.get_timeline_for_symbol("INFY", grouping="importance")
        assert len(res_imp["high"]) == 1
        assert len(res_imp["critical"]) == 1
        assert res_imp["critical"][0]["title"] == "Infosys Down on Layoffs"

        # Test Latest Grouping
        res_latest = ts.get_timeline_for_symbol("INFY", grouping="latest")
        assert "latest" in res_latest
        assert len(res_latest["latest"]) == 2

