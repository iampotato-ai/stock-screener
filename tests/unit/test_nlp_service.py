"""
Unit tests for the NLP service.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.services.nlp_service import nlp_service


class TestNLPService:
    """Test cases for NLPService."""

    @patch('app.services.nlp_service.helpers')
    def test_fallback_classify(self, mock_helpers):
        """Test fallback classification when NLP is disabled."""
        # Mock the helpers.classify_announcement function
        mock_helpers.classify_announcement.return_value = (
            'news', 'News', 'low', 'Low', 'sent-neutral', '🟡 Neutral',
            'Keyword-based classification'
        )

        # Mock nlp_enabled to be False
        with patch('app.services.nlp_service.current_app') as mock_app:
            mock_app.config.get.return_value = False
            with patch('app.services.nlp_service.has_app_context', return_value=True):
                result = nlp_service.process_announcement(
                    desc="Test announcement",
                    text="This is a test announcement"
                )

                # Assertions
                assert result['cat'] == 'news'
                assert result['cat_name'] == 'News'
                assert result['imp'] == 'low'
                assert result['imp_name'] == 'Low'
                assert result['sent'] == 'sent-neutral'
                assert result['sent_name'] == '🟡 Neutral'
                assert 'Keyword-based classification' in result['reason']

    @patch('app.services.nlp_service.helpers')
    @patch('app.services.nlp_service.current_app')
    def test_nlp_processing_success(self, mock_current_app, mock_helpers):
        """Test successful NLP processing."""
        # Mock app context and NLP enabled
        mock_current_app.config.get.return_value = True
        mock_current_app.__bool__.return_value = True

        # Mock helpers.init_nlp_models to return True
        with patch('app.services.nlp_service.helpers.init_nlp_models', return_value=True):
            # Mock the NLP processing functions
            mock_helpers._prepare_text_for_analysis.return_value = "test text"
            mock_helpers._analyze_sentiment.return_value = {
                'sentiment_label': 'positive',
                'nlp_sentiment_score': 0.8
            }
            mock_helpers._classify_event_category.return_value = {
                'event_category': 'earnings',
                'category_confidence': 0.9
            }
            mock_helpers._generate_summary.return_value = "Test summary"
            mock_helpers.calculate_base_catalyst_from_nlp.return_value = 0.75
            mock_helpers.map_nlp_category_to_standard.return_value = (
                'earn', 'Earnings', 'low', 'Low'
            )

            # Ensure the service thinks models are initialized
            nlp_service._models_initialized = True

            result = nlp_service.process_announcement(
                desc="Test announcement",
                text="This is a test announcement"
            )

            # Assertions
            assert result['cat'] == 'earn'
            assert result['cat_name'] == 'Earnings'
            assert result['imp'] == 'low'
            assert result['imp_name'] == 'Low'
            assert result['sent'] == 'sent-positive'
            assert result['sent_name'] == '🟢 Positive'
            assert result['catalyst_score'] == 0.75
            assert result['nlp_sentiment_score'] == 0.8
            assert result['nlp_category'] == 'earnings'
            assert result['summary'] == "Test summary"
            assert result['impact_magnitude'] == 0.75


if __name__ == "__main__":
    pytest.main([__file__])