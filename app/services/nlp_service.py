"""
NLP Service for processing corporate announcements.
Provides a clean interface for announcement classification using
FinBERT, zero-shot classification, and summarization models.
"""
from typing import Dict, Optional
from ..utils import helpers


class NLPService:
    """Service for NLP-based announcement processing."""

    def __init__(self):
        """Initialize service - models lazy loaded on first use."""
        self._models_initialized = False

    def _ensure_models(self) -> bool:
        """Ensure NLP models are initialized.
        Returns True if models are available, False otherwise.
        """
        if not self._models_initialized:
            self._models_initialized = helpers.init_nlp_models()
        return self._models_initialized

    def process_announcement(self, desc: str, text: str, attachment_url: str = "") -> Dict:
        """
        Process an announcement using NLP models if available,
        otherwise fall back to keyword-based classification.

        Args:
            desc: Announcement description/title
            text: Announcement body/text
            attachment_url: Optional URL to full announcement document

        Returns:
            Dictionary with classification results compatible with existing API.
        """
        # Check if we should attempt NLP processing
        if not self._ensure_models() or not (
                (desc and len(desc.strip()) > 10) or
                (text and len(text.strip()) > 10)
        ):
            return self._fallback_classify(desc, text)

        try:
            return self._process_with_nlp(desc, text, attachment_url)
        except Exception as e:
            print(f"[NLP Service] NLP processing failed, falling back: {e}")
            return self._fallback_classify(desc, text)

    def _process_with_nlp(self, desc: str, text: str, attachment_url: str) -> Dict:
        """Process announcement using NLP models."""
        # Prepare text for analysis
        full_text = helpers._prepare_text_for_analysis(desc, text, attachment_url)

        # 1. Sentiment analysis
        if helpers.sentiment_analyzer is not None:
            sent_res = helpers._analyze_sentiment(full_text)
            sentiment_label = sent_res["sentiment_label"]
            nlp_sentiment_score = sent_res["nlp_sentiment_score"]
        else:
            # Fallback to keyword-based sentiment (should not happen if models initialized)
            _, _, _, _, s_sent, _, _ = helpers.classify_announcement(desc, text)
            sentiment_label = s_sent.replace("sent-", "")
            nlp_sentiment_score = helpers._map_sentiment_to_score(s_sent)

        # 2. Event category zero-shot classification
        if helpers.event_classifier is not None:
            cat_res = helpers._classify_event_category(full_text)
            event_category = cat_res["event_category"]
            category_confidence = cat_res["category_confidence"]
        else:
            # Fallback to keyword-based category
            s_cat, s_cat_name, _, _, _, _, _ = helpers.classify_announcement(desc, text)
            event_category = s_cat_name.lower()
            category_confidence = 1.0

        # 3. Summarization
        summary = helpers._generate_summary(full_text) if helpers.summarizer is not None else None

        # 4. Catalyst score
        enhanced_catalyst_score = helpers.calculate_base_catalyst_from_nlp(
            sentiment_label, event_category, category_confidence
        )
        cat, cat_name, imp, imp_name = helpers.map_nlp_category_to_standard(event_category)

        sent_mapped = f"sent-{sentiment_label}"
        sent_name_mapped = {
            "positive": "🟢 Positive",
            "neutral": "🟡 Neutral",
            "negative": "🔴 Negative"
        }.get(sentiment_label, "🟡 Neutral")

        reason = f"NLP classification: category='{event_category}' (confidence={category_confidence:.2f}), sentiment='{sentiment_label}' (score={nlp_sentiment_score:.2f})."

        return {
            "cat": cat,
            "cat_name": cat_name,
            "imp": imp,
            "imp_name": imp_name,
            "sent": sent_mapped,
            "sent_name": sent_name_mapped,
            "reason": reason,
            "catalyst_score": round(enhanced_catalyst_score, 3),
            "nlp_sentiment_score": round(nlp_sentiment_score, 3),
            "nlp_category": event_category,
            "summary": summary or (desc or "")[:120],
            "impact_magnitude": round(abs(enhanced_catalyst_score), 3),
        }

    def _fallback_classify(self, desc: str, text: str) -> Dict:
        """Fallback to keyword-based classification."""
        s_cat, s_cat_name, s_imp, s_imp_name, s_sent, s_sent_name, s_reason = helpers.classify_announcement(desc, text)

        nlp_sentiment_score = helpers._map_sentiment_to_score(s_sent)
        catalyst_score = helpers._get_fallback_catalyst_score(s_cat, s_sent)
        impact_magnitude = round(abs(catalyst_score), 3)

        return {
            "cat": s_cat,
            "cat_name": s_cat_name,
            "imp": s_imp,
            "imp_name": s_imp_name,
            "sent": s_sent,
            "sent_name": s_sent_name,
            "reason": s_reason,
            "summary": (desc or "")[:120],  # Consistent with NLP path when no summary
            "nlp_category": s_cat_name.lower(),
            "nlp_sentiment_score": nlp_sentiment_score,
            "catalyst_score": round(catalyst_score, 3),
            "impact_magnitude": impact_magnitude,
        }


# Singleton instance
nlp_service = NLPService()

# Convenience function for direct use
def process_announcement(desc: str, text: str, attachment_url: str = "") -> Dict:
    """Process announcement using the singleton NLP service instance."""
    return nlp_service.process_announcement(desc, text, attachment_url)