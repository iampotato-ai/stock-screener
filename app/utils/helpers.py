"""
Helper functions for NLP processing and announcement classification.
Extracted from app.py to improve modularity.
"""
import os
import re
from typing import Dict, Tuple, Optional, List

# Import constants
from . import constants

# Global NLP models (lazy loaded)
sentiment_analyzer = None
event_classifier = None
summarizer = None

# Constants from constants.py
_NLP_POSITIVE_WORDS = constants._NLP_POSITIVE_WORDS
_NLP_NEGATIVE_WORDS = constants._NLP_NEGATIVE_WORDS

# Fallback catalyst scores for standard categories (used when NLP is unavailable)
_FALLBACK_CATALYST_SCORES = constants._FALLBACK_CATALYST_SCORES

# Base scores for event categories (used in NLP catalyst calculation)
EVENT_BASE_SCORES = constants.EVENT_BASE_SCORES

# NLP category mapping to standard categories
_NLP_CATEGORY_MAPPINGS = constants._NLP_CATEGORY_MAPPINGS

def init_nlp_models() -> bool:
    """Initialize NLP models (FinBERT, zero-shot classifier, DistilBART) if available and enabled."""
    global sentiment_analyzer, event_classifier, summarizer
    if sentiment_analyzer is not None:  # Already initialized
        return True
    # Respect environment toggle
    if os.environ.get('NLP_MODELS_ENABLED', 'True').lower() not in ('1', 'true', 'yes', 'on'):
        return False
    try:
        # Import here to avoid hard dependency if not installed
        from transformers import pipeline

        # Initialize FinBERT for sentiment
        sentiment_analyzer = pipeline(
            "sentiment-analysis",
            model=constants.NLP_MODELS["sentiment"],
            tokenizer=constants.NLP_MODELS["sentiment"],
            return_all_scores=True
        )

        # Initialize zero-shot classifier for event categories
        event_classifier = pipeline(
            "zero-shot-classification",
            model=constants.NLP_MODELS["classifier"]
        )

        # Initialize DistilBART for summarization
        summarizer = pipeline(
            "summarization",
            model=constants.NLP_MODELS["summarizer"]
        )
        return True
    except Exception as e:
        print(f"[NLP Helper] NLP models not available: {e}")
        sentiment_analyzer = None
        event_classifier = None
        summarizer = None
        return False

def _prepare_text_for_analysis(desc: str, text: str, attachment_url: str = "") -> str:
    """Combines description and text inputs, optionally fetching full content."""
    full_text = ""
    if desc:
        full_text += desc + " "
    if text:
        full_text += text

    # Fetch full announcement text if available
    if attachment_url:
        try:
            full_text = fetch_announcement_content(attachment_url) or full_text
        except Exception as e:
            print(f"[NLP Helper] Fetch content error: {e}")
    return full_text

def fetch_announcement_content(raw_url: str) -> Optional[str]:
    """
    Stub function for fetching and extracting text from corporate announcements.
    Currently returns None since PDF parsing libraries are not installed.
    """
    # In a full implementation, this would fetch the URL and extract text
    # based on content type (PDF, HTML, etc.)
    return None

def _analyze_sentiment(text: str) -> Dict:
    """Executes FinBERT sentiment analysis and returns sentiment label and continuous score."""
    global sentiment_analyzer
    if sentiment_analyzer is None:
        # This should not happen if called after init_nlp_models check
        return {"sentiment_label": "neutral", "nlp_sentiment_score": 0.0}

    sentiment_results = sentiment_analyzer(text[:512])  # FinBERT has 512-token limit
    sentiment_label = "neutral"
    max_score = 0.0
    sentiment_scores = {}
    for res in sentiment_results[0]:
        sentiment_scores[res['label']] = res['score']
        if res['score'] > max_score:
            max_score = res['score']
            sentiment_label = res['label']

    pos_score = sentiment_scores.get('positive', 0.0)
    neg_score = sentiment_scores.get('negative', 0.0)
    nlp_sentiment_score = pos_score - neg_score
    return {
        "sentiment_label": sentiment_label,
        "nlp_sentiment_score": nlp_sentiment_score
    }

def _classify_event_category(text: str) -> Dict:
    """Classifies event category using zero-shot classifier."""
    global event_classifier
    event_labels = [
        "financial results", "dividend announcement", "order win",
        "acquisition", "capex expansion", "management change",
        "regulatory issue", "bonus issue", "stock split",
        "analyst upgrade", "analyst downgrade", "guidance raise",
        "guidance cut", "contract win", "plant inauguration", "other"
    ]
    if event_classifier is None:
        # Fallback: treat as other with neutral confidence
        return {"event_category": "other", "category_confidence": 1.0}

    classification = event_classifier(text[:1024], event_labels)
    event_category = classification['labels'][0]
    category_confidence = classification['scores'][0]
    return {
        "event_category": event_category,
        "category_confidence": category_confidence
    }

def _generate_summary(text: str) -> Optional[str]:
    """Generates summary using DistilBART summarizer."""
    global summarizer
    if summarizer is None or len(text) <= 200:
        return None
    try:
        summary_result = summarizer(text[:1024], max_length=100, min_length=30, do_sample=False)
        return summary_result[0]['summary_text']
    except Exception as e:
        print(f"[NLP Helper] Summarization error: {e}")
        return None

def _map_sentiment_to_score(sent: str) -> float:
    """Map string sentiment ('sent-positive', 'sent-negative', 'sent-neutral') to numeric score."""
    if sent == "sent-positive":
        return 1.0
    if sent == "sent-negative":
        return -1.0
    return 0.0

def _get_fallback_catalyst_score(cat: str, sent: str) -> float:
    """Determine catalyst score for standard categories, dampening if sentiment is negative."""
    score = _FALLBACK_CATALYST_SCORES.get(cat, 0.20)
    if sent == "sent-negative" and score > 0:
        score = -abs(score) * 0.5
    return score

def calculate_base_catalyst_from_nlp(sentiment_label: str, event_category: str, confidence: float) -> float:
    """
    Calculate catalyst score based on NLP analysis results.
    """
    base_score = EVENT_BASE_SCORES.get(event_category.lower(), 0.20)

    # Adjust based on sentiment
    sentiment_multiplier = {
        'positive': 1.2,
        'neutral': 1.0,
        'negative': 0.8
    }.get(sentiment_label, 1.0)

    # Apply confidence weighting
    final_score = base_score * sentiment_multiplier * confidence

    # Clamp to reasonable range
    return max(-1.0, min(1.0, final_score))

def map_nlp_category_to_standard(nlp_cat: str) -> Tuple[str, str, str, str]:
    """
    Map an NLP zero-shot classification category back to standard dashboard category codes.
    Returns: (cat_code, cat_name, imp_code, imp_name)
    """
    nlp_cat_l = nlp_cat.lower()
    for keywords, result in _NLP_CATEGORY_MAPPINGS:
        if any(keyword in nlp_cat_l for keyword in keywords):
            return result
    return "cat-other", "Other", "imp-sentiment", "Sentiment only"

def classify_announcement(desc: str, text: str) -> Tuple[str, str, str, str, str, str, str]:
    """
    Keyword-based classifier for NSE corporate announcements.
    Returns: (cat, cat_name, imp, imp_name, sent, sent_name, reason)
    """
    desc_l = desc.lower() if desc else ""
    text_l = text.lower() if text else ""

    # Defaults
    cat = "cat-other"
    cat_name = "Other"
    imp = "imp-sentiment"
    imp_name = "Sentiment only"
    sent = "sent-neutral"
    sent_name = "🟡 Neutral"
    reason = "This is a standard corporate disclosure or newspaper publication required by listing regulations. It contains administrative or routine information without a material technical impact."

    # 1. Dividend
    if "dividend" in desc_l or "dividend" in text_l or "book closure" in desc_l or "book closure" in text_l or "record date" in desc_l or "record date" in text_l:
        cat = "cat-dividend"
        cat_name = "Dividend"
        imp = "imp-earnings-st"
        imp_name = "Earnings impact (short-term)"
        sent = "sent-positive"
        sent_name = "🟢 Positive"
        reason = "Dividends distribute corporate earnings directly to shareholders. This indicates positive cash flows, stable earnings, and strong management confidence in shareholder returns."

    # 2. Results
    elif any(x in desc_l or x in text_l for x in ["results", "financial result", "audited", "unaudited", "earnings", "balance sheet"]):
        cat = "cat-results"
        cat_name = "Results"
        imp = "imp-earnings-st"
        imp_name = "Earnings impact (short-term)"
        if any(x in desc_l or x in text_l for x in ["loss", "fall", "decline", "down", "decrease"]):
            sent = "sent-negative"
            sent_name = "🔴 Negative"
            reason = "Financial results highlight a decline, fall, decrease, or net loss in key metrics (revenue, profit, or margins), signaling short-term financial stress or operational headwinds."
        else:
            sent = "sent-positive"
            sent_name = "🟢 Positive"
            reason = "Financial results show positive revenue/profit growth and margin expansion, with no indicators of declining performance, signaling strong operational momentum."

    # 3. Order Win
    elif any(x in desc_l or x in text_l for x in ["order", "contract", "bagged", "secured", "won", "award"]):
        cat = "cat-order-win"
        cat_name = "Order Win"
        imp = "imp-order-book"
        imp_name = "Order book impact"
        sent = "sent-positive"
        sent_name = "🟢 Positive"
        reason = "Securing a new order, contract, or client award expands the company's order book, directly boosts future revenue visibility, and strengthens market leadership."

    # 4. Acquisition / Sale
    elif any(x in desc_l or x in text_l for x in ["acquisition", "acquire", "merger", "amalgamation", "takeover", "disposal", "slump sale", "disinvestment", "divestment"]):
        cat = "cat-acquisition"
        cat_name = "Acquisition"
        imp = "imp-balance-sheet"
        imp_name = "Balance sheet impact"
        sent = "sent-positive"
        sent_name = "🟢 Positive"
        reason = "Acquisitions or mergers increase business scale, acquire new technology or assets, expand geographic footprint, and signal positive inorganic growth prospects."

    # 5. Capex / Expansion
    elif any(x in desc_l or x in text_l for x in ["capex", "capacity", "expansion", "facility", "plant", "commission", "setting up", "inauguration"]):
        cat = "cat-capex"
        cat_name = "Capex"
        imp = "imp-earnings-lt"
        imp_name = "Earnings impact (long-term)"
        sent = "sent-positive"
        sent_name = "🟢 Positive"
        reason = "Capital expenditure for capacity expansion, new manufacturing plants, or facility commissioning indicates strong long-term demand and a growth-oriented corporate strategy."

    # 6. Regulatory
    elif any(x in desc_l or x in text_l for x in ["sebi", "rbi", "penalty", "fine", "warning", "show cause", "adjudication", "regulatory", "notice", "litigation", "summon"]):
        cat = "cat-regulatory"
        cat_name = "Regulatory"
        imp = "imp-governance"
        imp_name = "Governance signal"
        sent = "sent-negative"
        sent_name = "🔴 Negative"
        reason = "Regulatory actions, warnings, penalties, or compliance notices from regulatory bodies (SEBI, RBI, exchanges) represent compliance lapses or operational risks that warrant caution."

    # 7. Governance / Appointment
    elif any(x in desc_l or x in text_l for x in ["director", "board", "appointment", "resignation", "ceo", "cfo", "auditor", "governance", "promoter", "kmp", "key managerial"]):
        cat = "cat-governance"
        cat_name = "Governance"
        imp = "imp-governance"
        imp_name = "Governance signal"
        if "resignation" in desc_l or "resignation" in text_l:
            sent = "sent-neutral"
            sent_name = "🟡 Neutral"
            reason = "Resignations of key managerial personnel (KMPs) or auditors represent administrative changes but are classified as neutral to prompt closer review of management stability."
        else:
            sent = "sent-positive"
            sent_name = "🟢 Positive"
            reason = "Appointments of directors, CEOs, CFOs, or updates to audit committees represent standard, routine corporate governance adjustments aimed at reinforcing leadership."

    return cat, cat_name, imp, imp_name, sent, sent_name, reason