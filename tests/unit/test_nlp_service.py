"""
Unit tests for the new NLP service.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.services.nlp_service import nlp_service, AI_CALL_COUNTER


class TestNLPService:
    """Test cases for NLPService."""

    @pytest.fixture(autouse=True)
    def clean_counter(self):
        """Reset the AI call limit counter before each test."""
        AI_CALL_COUNTER.clear()

    def test_fallback_classify_heuristics(self, flask_app):
        """Test heuristic fallback classification when NLP is disabled."""
        # Configure app to disable NLP enrichment and run in app context
        flask_app.config['ENABLE_NLP_ENRICHMENT'] = False
        with flask_app.app_context():
            result = nlp_service.process_announcement(
                desc="Board declares interim dividend",
                text="Dividend details",
                symbol="TCS"
            )

            # Assertions
            assert result['cat'] == 'cat-dividend'
            assert result['cat_name'] == 'Dividend'
            assert result['imp'] == 'imp-earnings-st'
            assert result['sent'] == 'sent-positive'
            assert result['sent_name'] == '🟢 Positive'
            assert result['sentiment'] == 1
            assert result['catalyst_score'] == 0.75
            assert result['reason'] == "Heuristic keyword-matching fallback."

    @patch("app.services.nlp_service.ai_service.analyze_announcement")
    @patch("app.services.nlp_service.ai_service._get_api_keys")
    def test_nlp_processing_success(self, mock_keys, mock_analyze, flask_app):
        """Test successful NLP processing (Path A) when keys are available."""
        mock_keys.return_value = ("mock-nim-key", None)
        mock_analyze.return_value = {
            'catalyst_score': 0.85,
            'sentiment': 1,
            'nlp_sentiment_score': 0.8,
            'nlp_category': 'Dividend',
            'summary': "Test summary"
        }

        # Configure app to enable NLP enrichment
        flask_app.config['ENABLE_NLP_ENRICHMENT'] = True

        with flask_app.app_context():
            result = nlp_service.process_announcement(
                desc="Test announcement",
                text="This is a test announcement",
                symbol="TCS"
            )

            # Assertions
            assert result['cat'] == 'cat-dividend'
            assert result['cat_name'] == 'Dividend'
            assert result['sent'] == 'sent-positive'
            assert result['sent_name'] == '🟢 Positive'
            assert result['catalyst_score'] == 0.85
            assert result['nlp_sentiment_score'] == 0.8
            assert result['nlp_category'] == 'Dividend'
            assert result['summary'] == "Test summary"
            assert result['impact_magnitude'] == 0.85
            assert result['reason'] == "LLM deep-reasoning classification & summarization."
            assert AI_CALL_COUNTER["TCS"] == 1