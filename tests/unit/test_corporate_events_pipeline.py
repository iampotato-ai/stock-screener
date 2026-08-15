import pytest
import sqlite3
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from app.services.nlp_service import nlp_service, AI_CALL_COUNTER, getHeuristicCatalystScore
from app.utils.helpers import extract_text_from_pdf, fetch_announcement_content

class TestCorporateEventsPipeline:
    """Test suite for the Corporate Announcements & Events Pipeline."""

    @pytest.fixture(autouse=True)
    def clean_counter(self):
        """Reset the AI call limit counter before each test."""
        AI_CALL_COUNTER.clear()

    @patch("app.utils.helpers.download_pdf")
    @patch("pypdf.PdfReader")
    def test_pdf_parsing(self, mock_reader_class, mock_download):
        """Test PDF downloading and buffer parsing."""
        # Setup mocks
        mock_download.return_value = b"%PDF-1.4 mock data"
        
        mock_reader = MagicMock()
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page 1 Text content with  multiple   spaces."
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page 2 Text content\nwith newlines."
        
        mock_reader.pages = [mock_page1, mock_page2]
        mock_reader_class.return_value = mock_reader

        # Run extraction
        content = fetch_announcement_content("http://nseindia.com/filing.pdf")

        # Verify download and parsing
        mock_download.assert_called_once_with("http://nseindia.com/filing.pdf")
        assert content is not None
        # Verify spaces/newlines are collapsed
        assert "Page 1 Text content with multiple spaces. Page 2 Text content with newlines." in content

    @patch("app.services.nlp_service.ai_service.analyze_announcement")
    @patch("app.services.nlp_service.ai_service._get_api_keys")
    def test_nlp_service_path_a_success(self, mock_keys, mock_analyze):
        """Test successful Path A (AI) announcement evaluation."""
        mock_keys.return_value = ("mock-nim-key", None)
        mock_analyze.return_value = {
            "catalyst_score": 0.88,
            "sentiment": 1,
            "nlp_sentiment_score": 0.9,
            "nlp_category": "Order Win",
            "summary": "Cohesive AI Summary of the win."
        }

        res = nlp_service.process_announcement(
            desc="L&T wins mega order",
            text="L&T secured a contract worth 5000 Cr.",
            symbol="LT"
        )

        assert res["cat"] == "cat-order-win"
        assert res["cat_name"] == "Order Win"
        assert res["sentiment"] == 1
        assert res["catalyst_score"] == 0.88
        assert res["summary"] == "Cohesive AI Summary of the win."
        assert res["reason"] == "LLM deep-reasoning classification & summarization."
        assert AI_CALL_COUNTER["LT"] == 1

    @patch("app.services.nlp_service.ai_service.analyze_announcement")
    @patch("app.services.nlp_service.ai_service._get_api_keys")
    def test_nlp_service_limit_enforcement(self, mock_keys, mock_analyze):
        """Test that AI call limit of 3 per symbol forces fallback to Path B."""
        mock_keys.return_value = ("mock-nim-key", None)
        mock_analyze.return_value = {
            "catalyst_score": 0.85,
            "sentiment": 1,
            "nlp_sentiment_score": 0.8,
            "nlp_category": "Dividend",
            "summary": "Dividend declaration details."
        }

        # First 3 calls should use AI
        for i in range(3):
            res = nlp_service.process_announcement("Dividend declared", "Text", symbol="RELIANCE")
            assert res["reason"] == "LLM deep-reasoning classification & summarization."
            
        assert AI_CALL_COUNTER["RELIANCE"] == 3

        # 4th call should fall back to Heuristics (Path B)
        res_fallback = nlp_service.process_announcement("Dividend declared", "Text", symbol="RELIANCE")
        assert res_fallback["reason"] == "Heuristic keyword-matching fallback."
        assert res_fallback["cat"] == "cat-dividend"
        assert res_fallback["catalyst_score"] == 0.75
        assert AI_CALL_COUNTER["RELIANCE"] == 3  # Did not increment

    def test_path_b_heuristics(self):
        """Test heuristic keyword mapping constraints."""
        res_div = getHeuristicCatalystScore("Board proposes special dividend", "Some details here")
        assert res_div["nlp_category"] == "Dividend"
        assert res_div["catalyst_score"] == 0.75
        assert res_div["sentiment"] == 1

        res_split = getHeuristicCatalystScore("Stock split 1:10", "")
        assert res_split["nlp_category"] == "Stock Split"
        assert res_split["catalyst_score"] == 0.80

        res_reg = getHeuristicCatalystScore("SEBI issues warning and fine", "Lapse detected")
        assert res_reg["nlp_category"] == "Regulatory"
        assert res_reg["catalyst_score"] == 0.30
        assert res_reg["sentiment"] == -1

        res_def = getHeuristicCatalystScore("Standard board meeting update", "Routine disclosure")
        assert res_def["nlp_category"] == "Announcement"
        assert res_def["catalyst_score"] == 0.50
        assert res_def["sentiment"] == 0

    @patch("app.api.v1.legacy_routes.fetch_nse_announcements")
    @patch("app.services.nlp_service.ai_service._get_api_keys")
    def test_announcements_endpoint_pipeline(self, mock_keys, mock_fetch, flask_app):
        """Test get_announcements API endpoint with temporal filtering, caching, and persistence."""
        # Ensure LLM APIs are marked unconfigured so we use the deterministic Path B heuristics
        mock_keys.return_value = (None, None)

        # Mock NSE filings: 1 new (within 6m), 1 old (outside 6m)
        now_dt = datetime.now()
        in_6m_date_str = (now_dt - timedelta(days=10)).strftime("%d-%b-%Y")
        out_6m_date_str = (now_dt - timedelta(days=200)).strftime("%d-%b-%Y")
        
        mock_fetch.return_value = [
            {
                "symbol": "TCS",
                "desc": "TCS wins mega order from US client",
                "attchmntText": "Order win details",
                "attchmntFile": "",
                "an_dt": f"{in_6m_date_str} 10:00:00",
                "sort_date": (now_dt - timedelta(days=10)).strftime("%Y-%m-%d 10:00:00")
            },
            {
                "symbol": "TCS",
                "desc": "Old announcement that should be filtered",
                "attchmntText": "Routine details",
                "attchmntFile": "",
                "an_dt": f"{out_6m_date_str} 09:00:00",
                "sort_date": (now_dt - timedelta(days=200)).strftime("%Y-%m-%d 09:00:00")
            }
        ]

        # Inject clean SQLite tables
        db_path = "scan_history.db"
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS corporate_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT NOT NULL,
                exchange        TEXT NOT NULL,
                event_date      TEXT NOT NULL,
                event_type      TEXT,
                headline        TEXT,
                sentiment       INTEGER,
                catalyst_score  REAL,
                source          TEXT,
                raw_url         TEXT,
                nlp_sentiment_score REAL,
                nlp_category    TEXT,
                summary         TEXT,
                impact_magnitude REAL
            )
        """)
        c.execute("DELETE FROM corporate_events WHERE symbol='TCS'")
        conn.commit()
        conn.close()

        client = flask_app.test_client()

        # Call endpoint (First request: cache miss, fetches and processes)
        resp = client.get("/api/v1/announcements?symbols=NSE:TCS")
        assert resp.status_code == 200
        data = resp.get_json()
        
        announcements = data.get("announcements", [])
        # Verify 6-month temporal filter (the old one was skipped)
        assert len(announcements) == 1
        assert announcements[0]["ticker"] == "TCS"
        assert "TCS wins mega order" in announcements[0]["headline"]
        assert announcements[0]["category"] == "cat-order-win"
        assert announcements[0]["enhanced_catalyst_score"] == 0.80
        
        # Verify DB entry exists
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM corporate_events WHERE symbol='TCS'")
        count = c.fetchone()[0]
        assert count == 1
        
        # Check details of inserted row
        c.execute("SELECT headline, sentiment, catalyst_score, nlp_category FROM corporate_events WHERE symbol='TCS'")
        row = c.fetchone()
        assert "wins mega order" in row[0]
        assert row[1] == 1
        assert row[2] == 0.80
        assert row[3] == "Order Win"
        conn.close()

        # Call again (Second request: cache hit, does not call mock_fetch)
        mock_fetch.reset_mock()
        resp2 = client.get("/api/v1/announcements?symbols=NSE:TCS")
        assert resp2.status_code == 200
        data2 = resp2.get_json()
        assert len(data2.get("announcements", [])) == 1
        mock_fetch.assert_not_called()

    @patch("app.api.v1.legacy_routes.fetch_nse_announcements")
    @patch("app.services.nlp_service.ai_service._get_api_keys")
    def test_announcements_endpoint_self_healing(self, mock_keys, mock_fetch, flask_app):
        """Test that get_announcements auto-updates existing records if they lack a detailed summary."""
        # Ensure Path B heuristics is used
        mock_keys.return_value = (None, None)

        now_dt = datetime.now()
        in_6m_date_str = (now_dt - timedelta(days=5)).strftime("%d-%b-%Y")
        
        # Setup mock fetch to return the same announcement
        mock_fetch.return_value = [
            {
                "symbol": "INFY",
                "desc": "INFY wins mega order",
                "attchmntText": "Details of contract won",
                "attchmntFile": "",
                "an_dt": f"{in_6m_date_str} 10:00:00",
                "sort_date": (now_dt - timedelta(days=5)).strftime("%Y-%m-%d 10:00:00")
            }
        ]

        # Inject an UN-ENRICHED row into the database where summary == headline
        db_path = "scan_history.db"
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS corporate_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT NOT NULL,
                exchange        TEXT NOT NULL,
                event_date      TEXT NOT NULL,
                event_type      TEXT,
                headline        TEXT,
                sentiment       INTEGER,
                catalyst_score  REAL,
                source          TEXT,
                raw_url         TEXT,
                nlp_sentiment_score REAL,
                nlp_category    TEXT,
                summary         TEXT,
                impact_magnitude REAL
            )
        """)
        c.execute("DELETE FROM corporate_events WHERE symbol='INFY'")
        
        # Insert raw/un-enriched event
        c.execute('''
            INSERT INTO corporate_events (
                symbol, exchange, event_date, event_type, headline, sentiment,
                catalyst_score, source, raw_url, nlp_sentiment_score,
                nlp_category, summary, impact_magnitude
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            'INFY', 'NSE', (now_dt - timedelta(days=5)).strftime("%Y-%m-%d"), 'UNKNOWN',
            'INFY wins mega order', 0, 0.20, 'NSE', '', 0.0, 'other',
            'INFY wins mega order', 0.20 # summary is same as headline (un-enriched)
        ))
        conn.commit()
        conn.close()

        client = flask_app.test_client()

        # Trigger fetch and enrichment (the endpoint will run and update the database)
        resp = client.get("/api/v1/announcements?symbols=NSE:INFY")
        assert resp.status_code == 200
        data = resp.get_json()
        
        announcements = data.get("announcements", [])
        assert len(announcements) == 1
        # It should now have the enriched catalyst score and category code from Path B
        assert announcements[0]["enhanced_catalyst_score"] == 0.80
        assert announcements[0]["category"] == "cat-order-win"
        
        # Verify DB entry has been updated (healed)
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT sentiment, catalyst_score, nlp_category, summary FROM corporate_events WHERE symbol='INFY'")
        row = c.fetchone()
        assert row[0] == 1  # sentiment positive
        assert row[1] == 0.80  # score updated from 0.20 to 0.80
        assert row[2] == "Order Win"  # category updated
        assert "Order/Contract Win" in row[3]  # summary updated to the heuristic summary
        conn.close()
