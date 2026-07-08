import logging

logger = logging.getLogger(__name__)

# Investor-friendly explanations templates
EVENT_TEMPLATES = {
    "DIVIDEND": "The company announced a dividend, which indicates direct cash return and confidence in future cash flows.",
    "EARNINGS": "Quarterly earnings results show operational growth trajectories, impacting core valuation.",
    "SPLIT": "Stock split reduces nominal share price, lowering entry barriers to enhance liquidity.",
    "BONUS": "Bonus shares capitalize reserves, increasing share count without draining company cash.",
    "BULK_DEAL": "Institutional transactions indicate large position movements, signaling strong FII/DII action.",
    "BLOCK_DEAL": "Institutional transactions indicate large position movements, signaling strong FII/DII action.",
    "INSIDER": "Insider trading updates show promoter confidence or restructuring levels based on direct operational insights.",
    "BOARD_MEETING": "The board meets to resolve critical corporate actions, strategic plans, or financial reviews.",
    "CORPORATE_ACTION": "Corporate action updates directly influence capital structure and shareholder value."
}

CATEGORY_TEMPLATES = {
    "earnings": "The company reported its financial performance, which influences operational growth perceptions and core valuation.",
    "dividend": "A dividend announcement was released, highlighting cash-flow confidence and returns to shareholders.",
    "merger": "A corporate transaction or deal was announced, signaling strategic expansion or structural restructuring.",
    "board_meeting": "The board of directors is scheduled to meet to decide on key corporate policies or financial results.",
    "insider": "Insider promoter activity was registered, indicating internal sentiment and ownership adjustments.",
    "catalyst": "A key business catalyst or announcement was detected, indicating potential swing momentum."
}

class NLPMapper:
    """Centralizes NLP mapping logic, translations, and templates generation."""

    @staticmethod
    def map_sentiment(nlp_sent: str) -> str:
        """Map raw NLP sentiment keys to friendly UI labels."""
        sentiment_map = {
            "sent-positive": "Positive",
            "sent-negative": "Negative",
            "sent-neutral": "Neutral"
        }
        if not nlp_sent:
            return "Neutral"
        return sentiment_map.get(nlp_sent.strip().lower(), "Neutral")

    @staticmethod
    def map_confidence(score: float) -> float:
        """Round and normalize raw NLP sentiment confidence scores to percentages (0.0-100.0)."""
        if score is None:
            return 100.0
        return round(abs(score) * 100, 2)

    @staticmethod
    def map_importance(nlp_imp: str) -> str:
        """Map raw NLP importance tags to standard levels."""
        importance_map = {
            "high": "High",
            "medium": "Medium",
            "low": "Low",
            "critical": "Critical"
        }
        if not nlp_imp:
            return "Medium"
        return importance_map.get(nlp_imp.strip().lower(), "Medium")

    @staticmethod
    def generate_explanation(event_or_category: str, sentiment: str, category: str = None, reason: str = None) -> str:
        """
        Generate a friendly explanation.
        - For news/articles, attempts to use category or reason tags.
        - For corporate events, maps based on corporate action event_type.
        """
        sentiment_lower = sentiment.lower() if sentiment else "neutral"
        
        # Check event_type templates first
        key = event_or_category.upper()
        if key in EVENT_TEMPLATES:
            return EVENT_TEMPLATES[key]

        # Check category templates
        cat_key = (category or event_or_category).lower()
        if cat_key in CATEGORY_TEMPLATES:
            base_desc = CATEGORY_TEMPLATES[cat_key]
            if reason and len(reason.strip()) > 5:
                return f"{base_desc} Highlight: {reason}"
            return base_desc

        # General news fallback
        sentiment_word = "constructive" if sentiment_lower == "positive" else "cautious" if sentiment_lower == "negative" else "neutral"
        if reason and len(reason.strip()) > 5:
            return f"Market update indicates a {sentiment_word} outlook. Details: {reason}"
            
        return f"Market updates indicate a {sentiment_word} outlook for the stock."
