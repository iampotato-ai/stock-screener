"""
AI-Powered Stock Analysis with Signal Score.

Public API:
    analyze_stock(symbol, exchange, include_ai, range_str) → TechnicalSnapshot dict

This package computes a comprehensive TechnicalSnapshot per stock including:
- Multi-timeframe MA alignment (SMA 5/10/20/60)
- MACD golden/death cross detection
- Multi-period RSI (6/12/24) with classification
- Volume regime analysis
- Support/resistance level computation
- Trend status classification
- Risk analytics (realized vol, ATR, max drawdown)
- Auto-computed trade levels (stop-loss, take-profit)
- Composite signal score → verdict
- AI overlay with LLM-generated summary
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def analyze_stock(
    symbol: str,
    exchange: str = "NSE",
    include_ai: bool = True,
    range_str: str = "6mo",
) -> Dict[str, Any]:
    """
    Compute a complete TechnicalSnapshot for a single stock.

    Args:
        symbol: Stock ticker (e.g. 'RELIANCE').
        exchange: Exchange code (default 'NSE').
        include_ai: Whether to include the LLM-powered AI overlay.
        range_str: Yahoo Finance range string for historical data (default '6mo').

    Returns:
        TechnicalSnapshot dict with all analysis fields populated.
    """
    from app.utils.technical import fetch_historical_prices
    from app.services.signal_score.ma_alignment import compute_ma_alignment
    from app.services.signal_score.macd_cross import compute_macd_cross
    from app.services.signal_score.rsi_multi import compute_rsi_multi
    from app.services.signal_score.volume_analysis import classify_volume
    from app.services.signal_score.support_resistance import compute_support_resistance
    from app.services.signal_score.trend_classifier import classify_trend
    from app.services.signal_score.risk_analytics import compute_risk_analytics
    from app.services.signal_score.trade_levels import compute_trade_levels
    from app.services.signal_score.composite_signal import compute_composite_signal
    from app.services.signal_score.ai_overlay import generate_ai_overlay

    snapshot: Dict[str, Any] = {
        "symbol": symbol,
        "exchange": exchange,
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
        "success": False,
        "error": None,
    }

    try:
        # ── Fetch OHLCV history ──────────────────────────────────
        history = fetch_historical_prices(symbol, range_str=range_str)
        if not history or len(history) < 20:
            snapshot["error"] = f"Insufficient price history for {symbol} ({len(history) if history else 0} bars)"
            return snapshot

        closes = [day["close"] for day in history]
        highs = [day["high"] for day in history]
        lows = [day["low"] for day in history]
        volumes = [day["volume"] for day in history]
        opens = [day["open"] for day in history]
        current_close = closes[-1]

        # ── Component analyses ───────────────────────────────────
        ma_result = compute_ma_alignment(closes)
        macd_result = compute_macd_cross(closes)
        rsi_result = compute_rsi_multi(closes)
        volume_result = classify_volume(closes, volumes)
        sr_result = compute_support_resistance(highs, lows, closes)
        trend_result = classify_trend(
            ma_score=ma_result.get("alignment_score", 0.0),
            macd_score=macd_result.get("score", 0.0),
            macd_cross=macd_result.get("cross_type", "none"),
            rsi_score=rsi_result.get("composite_score", 0.0),
        )
        risk_result = compute_risk_analytics(closes, highs, lows)
        composite_result = compute_composite_signal(
            ma_score=ma_result.get("alignment_score", 0.0),
            macd_score=macd_result.get("score", 0.0),
            rsi_score=rsi_result.get("composite_score", 0.0),
            volume_score=volume_result.get("score", 0.0),
            trend_score=trend_result.get("trend_score", 0.0),
            risk_score=risk_result.get("risk_score", 0.5),
        )
        trade_result = compute_trade_levels(
            current_close=current_close,
            signal_verdict=composite_result.get("verdict", "Hold"),
            nearest_support=sr_result.get("nearest_support", current_close * 0.95),
            nearest_resistance=sr_result.get("nearest_resistance", current_close * 1.05),
            atr=risk_result.get("atr_14", current_close * 0.02),
        )

        # ── Assemble snapshot ────────────────────────────────────
        snapshot["ma_alignment"] = ma_result
        snapshot["macd_status"] = macd_result
        snapshot["rsi_multi"] = rsi_result
        snapshot["volume_analysis"] = volume_result
        snapshot["support_resistance"] = sr_result
        snapshot["trend_status"] = trend_result.get("trend_label", "Neutral")
        snapshot["risk_analytics"] = risk_result
        snapshot["signal_score"] = composite_result.get("score", 50.0)
        snapshot["signal_verdict"] = composite_result.get("verdict", "Hold")
        snapshot["signal_breakdown"] = composite_result.get("breakdown", {})
        snapshot["trade_levels"] = trade_result

        # ── AI overlay (optional) ────────────────────────────────
        if include_ai:
            try:
                ai_result = generate_ai_overlay(symbol, snapshot)
                snapshot["ai_summary"] = ai_result.get("summary", "")
                snapshot["ai_bull_factors"] = ai_result.get("bull_factors", [])
                snapshot["ai_risk_factors"] = ai_result.get("risk_factors", [])
                snapshot["news_sentiment"] = ai_result.get("news_sentiment", "sent-neutral")
            except Exception as ai_err:
                logger.warning("AI overlay failed for %s: %s", symbol, ai_err)
                snapshot["ai_summary"] = ""
                snapshot["ai_bull_factors"] = []
                snapshot["ai_risk_factors"] = []
                snapshot["news_sentiment"] = "sent-neutral"
        else:
            snapshot["ai_summary"] = ""
            snapshot["ai_bull_factors"] = []
            snapshot["ai_risk_factors"] = []
            snapshot["news_sentiment"] = "sent-neutral"

        snapshot["success"] = True
        logger.info("Signal score for %s.%s: %.1f (%s)", symbol, exchange,
                     snapshot["signal_score"], snapshot["signal_verdict"])

    except Exception as e:
        logger.error("Error computing signal score for %s.%s: %s", symbol, exchange, e)
        snapshot["error"] = str(e)

    return snapshot
