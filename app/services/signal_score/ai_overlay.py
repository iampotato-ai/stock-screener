"""
AI overlay: LLM-powered summary with news sentiment, bull/risk factors.

Uses the existing AIService (NIM → Gemini cascade) to generate a
human-readable action summary grounded in the TechnicalSnapshot data.
Falls back to a template-based summary when LLM APIs are unavailable.
"""
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def generate_ai_overlay(
    symbol: str,
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate an AI-powered analysis overlay for a stock.

    Args:
        symbol: Stock ticker (e.g. 'RELIANCE').
        snapshot: Partially-assembled TechnicalSnapshot dict
                  (must already contain signal_verdict, ma_alignment, etc.).

    Returns:
        Dict with:
            summary: str — 2–4 sentence plain-prose action plan
            bull_factors: list[str] — max 3 bullish drivers
            risk_factors: list[str] — max 3 risk items
            news_sentiment: str — "sent-positive" | "sent-neutral" | "sent-negative"
    """
    # Gather news sentiment (optional — may fail silently)
    news_sentiment = _fetch_news_sentiment(symbol)

    # Build the LLM prompt
    prompt = _build_prompt(symbol, snapshot, news_sentiment)

    # Attempt LLM generation
    llm_result = _call_llm(prompt)
    if llm_result:
        return {
            "summary": llm_result.get("summary", ""),
            "bull_factors": llm_result.get("bull_factors", [])[:3],
            "risk_factors": llm_result.get("risk_factors", [])[:3],
            "news_sentiment": news_sentiment,
        }

    # Fallback: template-based summary
    fallback = _generate_fallback(symbol, snapshot, news_sentiment)
    return fallback


def _fetch_news_sentiment(symbol: str) -> str:
    """Fetch news sentiment via AIService. Returns sent-positive/neutral/negative."""
    try:
        from app.services.ai_service import ai_service
        from app.services.news_service import news_service
        articles = news_service.get_news(symbol)
        if articles:
            result = ai_service.analyze_news_catalysts(symbol, articles)
            return result.get("sentiment", "sent-neutral")
    except Exception as e:
        logger.debug("News sentiment fetch failed for %s: %s", symbol, e)
    return "sent-neutral"


def _build_prompt(
    symbol: str,
    snapshot: Dict[str, Any],
    news_sentiment: str,
) -> str:
    """Build the structured prompt for the LLM."""
    verdict = snapshot.get("signal_verdict", "Hold")
    score = snapshot.get("signal_score", 50)
    trend = snapshot.get("trend_status", "Neutral")

    ma = snapshot.get("ma_alignment", {})
    alignment_label = ma.get("alignment_label", "Mixed")

    macd = snapshot.get("macd_status", {})
    cross_type = macd.get("cross_type", "none")

    rsi = snapshot.get("rsi_multi", {})
    rsi_label = rsi.get("composite_label", "Neutral")

    vol = snapshot.get("volume_analysis", {})
    vol_regime = vol.get("regime", "Light Up")

    risk = snapshot.get("risk_analytics", {})
    risk_label = risk.get("risk_label", "Medium")

    trade = snapshot.get("trade_levels", {})
    direction = trade.get("direction", "NEUTRAL")
    sl = trade.get("stop_loss", 0)
    tp = trade.get("take_profit", 0)

    prompt = (
        f"You are a senior institutional equity research analyst covering NSE India.\n"
        f"Generate a concise stock analysis for {symbol} based on these technicals:\n\n"
        f"Signal: {verdict} (Score: {score}/100)\n"
        f"Trend: {trend}\n"
        f"MA Alignment: {alignment_label}\n"
        f"MACD: {cross_type.replace('_', ' ').title()}\n"
        f"RSI: {rsi_label}\n"
        f"Volume: {vol_regime}\n"
        f"Risk: {risk_label}\n"
        f"News Sentiment: {news_sentiment.replace('sent-', '').title()}\n"
        f"Direction: {direction}, SL: {sl}, TP: {tp}\n\n"
        "Return ONLY a valid JSON object with exactly three keys:\n"
        '1) "summary": 2-4 sentence plain prose action plan. No markdown, no bold, no lists.\n'
        '2) "bull_factors": array of max 3 short bullish driver strings.\n'
        '3) "risk_factors": array of max 3 short risk item strings.\n\n'
        "Do NOT include markdown formatting or backticks. Return pure JSON."
    )
    return prompt


def _call_llm(prompt: str) -> Dict[str, Any]:
    """Call the LLM via AIService and parse the structured response."""
    try:
        from app.services.ai_service import ai_service
        import os
        import json

        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        text = ai_service._call_gemini(gemini_model, prompt)
        if text:
            clean = re.sub(r"```json|```", "", text).strip()
            parsed = json.loads(clean)
            if "summary" in parsed:
                return parsed
    except Exception as e:
        logger.warning("LLM call failed for AI overlay: %s", e)
    return {}


def _generate_fallback(
    symbol: str,
    snapshot: Dict[str, Any],
    news_sentiment: str,
) -> Dict[str, Any]:
    """Generate a template-based fallback when LLM is unavailable."""
    verdict = snapshot.get("signal_verdict", "Hold")
    score = snapshot.get("signal_score", 50)
    trend = snapshot.get("trend_status", "Neutral")
    ma = snapshot.get("ma_alignment", {})
    alignment = ma.get("alignment_label", "Mixed")
    risk = snapshot.get("risk_analytics", {})
    risk_label = risk.get("risk_label", "Medium")

    summary = (
        f"{symbol} currently shows a {verdict} signal with a composite score of "
        f"{score:.0f}/100, underpinned by a {trend.lower()} trend with {alignment.lower()} "
        f"moving average alignment. Risk profile is classified as {risk_label.lower()} "
        f"based on realized volatility and drawdown metrics."
    )

    bull_factors: List[str] = []
    risk_factors: List[str] = []

    if verdict in ("Strong Buy", "Buy"):
        bull_factors.append(f"Trend direction is {trend.lower()} with favorable MA alignment")
    if snapshot.get("macd_status", {}).get("cross_type", "") in ("golden_cross", "sustained_bull"):
        bull_factors.append("MACD confirmation via bullish crossover")
    if news_sentiment == "sent-positive":
        bull_factors.append("Positive news sentiment supporting price action")

    if risk_label in ("High", "Very High"):
        risk_factors.append(f"Elevated risk ({risk_label.lower()}) from volatility metrics")
    if snapshot.get("volume_analysis", {}).get("regime", "").startswith("Shrink"):
        risk_factors.append("Low volume participation suggests weak conviction")
    if snapshot.get("rsi_multi", {}).get("composite_label", "") == "Overbought":
        risk_factors.append("RSI in overbought territory — potential for mean reversion")

    # Ensure at least one item in each
    if not bull_factors:
        bull_factors.append("Composite signal is within normal parameters")
    if not risk_factors:
        risk_factors.append("No major risk factors identified at current levels")

    return {
        "summary": summary,
        "bull_factors": bull_factors[:3],
        "risk_factors": risk_factors[:3],
        "news_sentiment": news_sentiment,
    }
