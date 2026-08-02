"""
Market Brief Service for MomentumScan.
Aggregates market regime, corporate news/announcements, and momentum signals
to generate a daily pre-market brief using Gemini API or a quantitative fallback engine.
"""
from datetime import date, datetime
from typing import Dict, Any, List, Optional
from flask import current_app
from app.extensions import db
from app.models import MarketBrief


class MarketBriefService:
    """Service to aggregate, generate, and store daily morning market briefs."""

    def get_or_create_daily_brief(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetch today's cached MarketBrief or generate a new one.
        If force_refresh is True, re-runs synthesis and updates the DB record.
        """
        today = date.today()

        if not force_refresh:
            existing = MarketBrief.query.filter_by(brief_date=today).first()
            if existing:
                return existing.to_dict()

        context = self._aggregate_market_context()
        
        # 1. Attempt Gemini AI synthesis
        from app.services.ai_service import ai_service
        ai_result = ai_service.generate_daily_market_brief(context)

        is_fallback = False
        if ai_result:
            brief_data = ai_result
        else:
            # 2. Quantitative rule-based fallback if AI is unconfigured or offline
            brief_data = self._generate_quantitative_fallback(context)
            is_fallback = True

        # Save or update record in database
        brief_record = MarketBrief.query.filter_by(brief_date=today).first()
        if not brief_record:
            brief_record = MarketBrief(brief_date=today)

        regime = context.get("regime", {})
        brief_record.regime_score = regime.get("score", 50)
        brief_record.regime_band = regime.get("band", "Neutral")
        brief_record.headline = brief_data.get("headline", "Daily Morning Market Brief")
        brief_record.macro_summary = brief_data.get("regime_summary", "")
        brief_record.sector_catalysts = brief_data.get("sector_catalysts", [])
        brief_record.top_actionable_stocks = brief_data.get("actionable_stocks", [])
        brief_record.key_risks = brief_data.get("key_risks", [])
        brief_record.is_fallback = is_fallback
        brief_record.created_at = datetime.utcnow()

        db.session.add(brief_record)
        db.session.commit()

        return brief_record.to_dict()

    def _aggregate_market_context(self) -> Dict[str, Any]:
        """Aggregate current market intelligence, regime metrics, and top momentum movers."""
        context = {
            "regime": {"score": 50, "band": "Neutral", "advances": 0, "declines": 0, "pct_sma21": 50},
            "news": [],
            "movers": []
        }

        # 1. Market Breadth & Sentiment
        try:
            from app.services.fear_greed_service import fear_greed_service
            fg_data = fear_greed_service.compute_fear_greed_index()
            if fg_data:
                context["regime"] = {
                    "score": fg_data.get("score", 50),
                    "band": fg_data.get("label", "Neutral"),
                    "advances": fg_data.get("sub_indicators", {}).get("ad_momentum", 50.0),
                    "declines": 50.0,
                    "pct_sma21": fg_data.get("sub_indicators", {}).get("breadth", 50.0)
                }
        except Exception as e:
            if current_app:
                current_app.logger.warning(f"Could not load fear greed data for brief: {e}")

        # 2. Market Intelligence News / Filings
        try:
            from app.models import NewsArticle
            articles = NewsArticle.query.order_by(NewsArticle.published_at.desc()).limit(10).all()
            if articles:
                context["news"] = [
                    {
                        "title": a.title,
                        "source": getattr(a, 'source', 'NSE'),
                        "summary": getattr(a, 'summary', a.title)
                    }
                    for a in articles
                ]
        except Exception as e:
            if current_app:
                current_app.logger.warning(f"Could not load market news for brief: {e}")

        # 3. Top Momentum Movers (EP / Bull Snort)
        try:
            from app.models import EpWatchlist
            ep_items = EpWatchlist.query.order_by(EpWatchlist.ep_score.desc()).limit(6).all()
            if ep_items:
                context["movers"] = [
                    {
                        "ticker": h.symbol if hasattr(h, 'symbol') else 'NIFTY',
                        "setupLabel": getattr(h, 'ep_type', 'Episodic Pivot'),
                        "score": int(getattr(h, 'ep_score', 80) or 80)
                    }
                    for h in ep_items
                ]
        except Exception as e:
            if current_app:
                current_app.logger.warning(f"Could not load EP hits for brief: {e}")

        return context



    def _generate_quantitative_fallback(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Rule-based quantitative summary generator when Gemini AI is offline/unconfigured."""
        regime = context.get("regime", {})
        score = regime.get("score", 50)
        band = regime.get("band", "Neutral")
        movers = context.get("movers", [])

        if score >= 65:
            headline = f"Nifty Bullish Momentum Active ({score}/100): High Conviction Swing Setups Dominating"
            regime_summary = (
                f"Market regime score stands at {score}/100 ({band.upper()}). "
                "Strong advance-decline ratio and high percentage of stocks above 21D MA favor long breakout strategies."
            )
            bias = "Bullish"
        elif score <= 40:
            headline = f"Market Caution Advised ({score}/100): Deteriorating Breadth & Volatility Compression"
            regime_summary = (
                f"Market regime score is at {score}/100 ({band.upper()}). "
                "Weak market breadth warrants defensive position sizing and tighter stop loss management."
            )
            bias = "Bearish"
        else:
            headline = f"Mixed Market Breadth ({score}/100): Focus on Selective High-Quality Episodic Pivots"
            regime_summary = (
                f"Market regime score is neutral at {score}/100. "
                "Selectivity is critical — focus exclusively on stocks displaying abnormal volume expansion and catalyst backing."
            )
            bias = "Neutral"

        actionable = []
        for m in movers[:4]:
            actionable.append({
                "symbol": m.get("ticker", "NIFTY"),
                "reason": f"Top Episodic Pivot setup with momentum score of {m.get('score', 0)}."
            })

        if not actionable:
            actionable = [
                {"symbol": "RELIANCE", "reason": "Heavyweight market leader showing consolidation near key MA support."},
                {"symbol": "HDFCBANK", "reason": "Institutional accumulation in banking sector sector leader."}
            ]

        return {
            "headline": headline,
            "regime_summary": regime_summary,
            "sector_catalysts": [
                {"sector": "Nifty 50 Momentum", "bias": bias, "driver": f"Regime score at {score}/100 with active momentum structures."},
                {"sector": "Episodic Pivots", "bias": "Bullish", "driver": f"{len(movers)} active breakout candidates detected in scanner."}
            ],
            "actionable_stocks": actionable,
            "key_risks": [
                "Intraday volatility surrounding global macro & crude oil updates.",
                "Maintain strict trailing stop loss discipline on open swing positions."
            ]
        }


# Singleton instance
market_brief_service = MarketBriefService()
