"""
NLP Service for processing corporate announcements.
Provides a clean interface for announcement classification using
AI models (Nvidia NIM/Gemini) or a heuristic fallback classifier.
"""
import os
from collections import defaultdict
from typing import Dict, Tuple, Optional
from flask import current_app, has_app_context
from ..utils import helpers
from .ai_service import ai_service

# Global counter for AI calls per symbol to enforce limit of 3
AI_CALL_COUNTER = defaultdict(int)

def map_category_to_codes(category: str) -> Tuple[str, str, str, str]:
    """Map nlp_category string back to standard dashboard category and impact codes."""
    cat_lower = category.lower()
    if "dividend" in cat_lower:
        return "cat-dividend", "Dividend", "imp-earnings-st", "Earnings impact (short-term)"
    elif "split" in cat_lower or "sub-division" in cat_lower:
        return "cat-dividend", "Stock Split", "imp-earnings-st", "Earnings impact (short-term)"
    elif "bonus" in cat_lower:
        return "cat-dividend", "Bonus Issue", "imp-earnings-st", "Earnings impact (short-term)"
    elif "buyback" in cat_lower or "buy-back" in cat_lower:
        return "cat-governance", "Buyback", "imp-governance", "Governance signal"
    elif "order" in cat_lower or "contract" in cat_lower or "won" in cat_lower or "agreement" in cat_lower or "mou" in cat_lower or "award" in cat_lower:
        return "cat-order-win", "Order Win", "imp-order-book", "Order book impact"
    elif "earnings" in cat_lower or "results" in cat_lower or "profit" in cat_lower or "revenue" in cat_lower:
        return "cat-results", "Results", "imp-earnings-st", "Earnings impact (short-term)"
    elif "acquisition" in cat_lower or "merger" in cat_lower or "amalgamation" in cat_lower:
        return "cat-acquisition", "Acquisition", "imp-balance-sheet", "Balance sheet impact"
    elif "personnel" in cat_lower or "resignation" in cat_lower or "auditor" in cat_lower or "director" in cat_lower:
        return "cat-governance", "Governance", "imp-governance", "Governance signal"
    elif "regulatory" in cat_lower or "sebi" in cat_lower or "penalty" in cat_lower or "fine" in cat_lower or "tax demand" in cat_lower or "show cause" in cat_lower:
        return "cat-regulatory", "Regulatory", "imp-governance", "Governance signal"
    else:
        return "cat-other", "Other", "imp-sentiment", "Sentiment only"

def getHeuristicCatalystScore(headline: str, text: str) -> dict:
    """Path B: Fallback heuristic keyword router."""
    headline_l = headline.lower() if headline else ""
    text_l = text.lower() if text else ""
    
    # 1. Dividend
    if any(x in headline_l or x in text_l for x in ["dividend", "interim dividend", "special dividend"]):
        return {
            "nlp_category": "Dividend",
            "catalyst_score": 0.75,
            "sentiment": 1,
            "nlp_sentiment_score": 0.6,
            "summary": f"Dividend Action: {headline}"
        }
    
    # 2. Stock Split
    if any(x in headline_l or x in text_l for x in ["split", "sub-division"]):
        return {
            "nlp_category": "Stock Split",
            "catalyst_score": 0.80,
            "sentiment": 1,
            "nlp_sentiment_score": 0.7,
            "summary": f"Stock Split/Sub-division: {headline}"
        }
        
    # 3. Bonus Issue
    if "bonus" in headline_l or "bonus" in text_l:
        return {
            "nlp_category": "Bonus Issue",
            "catalyst_score": 0.85,
            "sentiment": 1,
            "nlp_sentiment_score": 0.8,
            "summary": f"Bonus Issue: {headline}"
        }
        
    # 4. Buyback
    if any(x in headline_l or x in text_l for x in ["buyback", "buy-back"]):
        return {
            "nlp_category": "Buyback",
            "catalyst_score": 0.82,
            "sentiment": 1,
            "nlp_sentiment_score": 0.75,
            "summary": f"Share Buyback: {headline}"
        }
        
    # 5. Order Win
    if any(x in headline_l or x in text_l for x in ["order", "award", "contract", "won", "signed mou", "agreement"]):
        return {
            "nlp_category": "Order Win",
            "catalyst_score": 0.80,
            "sentiment": 1,
            "nlp_sentiment_score": 0.7,
            "summary": f"Order/Contract Win: {headline}"
        }
        
    # 6. Earnings
    if any(x in headline_l or x in text_l for x in ["financial results", "earnings", "profit", "revenue", "audited financial"]):
        return {
            "nlp_category": "Earnings",
            "catalyst_score": 0.70,
            "sentiment": 1,
            "nlp_sentiment_score": 0.4,
            "summary": f"Financial Results: {headline}"
        }
        
    # 7. Acquisition
    if any(x in headline_l or x in text_l for x in ["acquisition", "amalgamation", "merger"]):
        return {
            "nlp_category": "Acquisition",
            "catalyst_score": 0.78,
            "sentiment": 1,
            "nlp_sentiment_score": 0.6,
            "summary": f"M&A Activity: {headline}"
        }
        
    # 8. Personnel Change
    if any(x in headline_l or x in text_l for x in ["resignation", "auditor"]):
        return {
            "nlp_category": "Personnel Change",
            "catalyst_score": 0.35,
            "sentiment": -1,
            "nlp_sentiment_score": -0.5,
            "summary": f"Key Personnel/Auditor Update: {headline}"
        }
        
    # 9. Regulatory
    if any(x in headline_l or x in text_l for x in ["sebi", "penalty", "fine", "tax demand", "show cause"]):
        return {
            "nlp_category": "Regulatory",
            "catalyst_score": 0.30,
            "sentiment": -1,
            "nlp_sentiment_score": -0.7,
            "summary": "Regulatory action, penalty, or tax notice filed."
        }
        
    # 10. Default
    return {
        "nlp_category": "Announcement",
        "catalyst_score": 0.50,
        "sentiment": 0,
        "nlp_sentiment_score": 0.0,
        "summary": f"NSE Filing: {headline}"
    }

class NLPService:
    """Service for NLP-based announcement processing supporting dual-path classification."""

    def __init__(self):
        pass

    def process_announcement(self, desc: str, text: str, attachment_url: str = "", symbol: str = "UNKNOWN") -> Dict:
        """
        Process an announcement using NVIDIA NIM or Gemini (Path A) if key is available
        and symbols limit < 3, otherwise use keyword-based heuristic fallback (Path B).
        """
        # Download and parse PDF attachment if present
        pdf_text = None
        if attachment_url:
            try:
                pdf_text = helpers.fetch_announcement_content(attachment_url)
            except Exception as e:
                print(f"[NLP Service] Error fetching attachment content: {e}")

        # Check if AI keys are available
        nim_key, gemini_key = ai_service._get_api_keys()
        ai_enabled = nim_key or gemini_key

        # Retrieve feature flag check
        nlp_enabled = (
            current_app.config.get('ENABLE_NLP_ENRICHMENT', True)
            if has_app_context()
            else os.environ.get('ENABLE_NLP_ENRICHMENT', 'True').lower() == 'true'
        )

        success = False
        ai_result = None

        if ai_enabled and nlp_enabled and AI_CALL_COUNTER[symbol] < 3:
            try:
                ai_result = ai_service.analyze_announcement(symbol, desc, pdf_text)
                if ai_result and isinstance(ai_result, dict):
                    # Basic keys verification
                    required_keys = ["catalyst_score", "sentiment", "nlp_sentiment_score", "nlp_category", "summary"]
                    if all(k in ai_result for k in required_keys):
                        AI_CALL_COUNTER[symbol] += 1
                        success = True
            except Exception as e:
                print(f"[NLP Service] Path A LLM call failed for {symbol}: {e}")

        if success and ai_result:
            classification = ai_result
            reason = "LLM deep-reasoning classification & summarization."
        else:
            # Path B: Heuristic Fallback
            classification = getHeuristicCatalystScore(desc, pdf_text or text)
            reason = "Heuristic keyword-matching fallback."

        # Map to standard codes
        cat, cat_name, imp, imp_name = map_category_to_codes(classification["nlp_category"])
        
        sent_val = int(classification.get("sentiment", 0))
        sent_mapped = "sent-neutral"
        sent_name_mapped = "🟡 Neutral"
        if sent_val == 1:
            sent_mapped = "sent-positive"
            sent_name_mapped = "🟢 Positive"
        elif sent_val == -1:
            sent_mapped = "sent-negative"
            sent_name_mapped = "🔴 Negative"

        catalyst_score = float(classification.get("catalyst_score", 0.50))
        nlp_sentiment_score = float(classification.get("nlp_sentiment_score", 0.0))
        nlp_cat = classification.get("nlp_category", "Announcement")
        summary = classification.get("summary", f"NSE Filing: {desc}")

        return {
            "cat": cat,
            "cat_name": cat_name,
            "imp": imp,
            "imp_name": imp_name,
            "sent": sent_mapped,
            "sent_name": sent_name_mapped,
            "sentiment": sent_val,
            "reason": reason,
            "catalyst_score": round(catalyst_score, 3),
            "nlp_sentiment_score": round(nlp_sentiment_score, 3),
            "nlp_category": nlp_cat,
            "summary": summary,
            "impact_magnitude": round(abs(catalyst_score), 3),
        }

# Singleton instance
nlp_service = NLPService()

# Convenience function for direct use
def process_announcement(desc: str, text: str, attachment_url: str = "", symbol: str = "UNKNOWN") -> Dict:
    """Process announcement using the singleton NLP service instance."""
    return nlp_service.process_announcement(desc, text, attachment_url, symbol)