"""
India-Specific Fear & Greed Service.
Computes a composite Fear & Greed index (0-100) for the Indian stock market (NSE).
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app import db
from app.models import FearGreedHistory, BreadthHistory

logger = logging.getLogger(__name__)


class FearGreedService:
    """Service for calculating, persisting, and querying India Fear & Greed Index."""

    def get_rating_label(self, score: int) -> str:
        """Map a score (0-100) to a Fear & Greed rating category."""
        if score <= 24:
            return "Extreme Fear"
        elif score <= 44:
            return "Fear"
        elif score <= 55:
            return "Neutral"
        elif score <= 75:
            return "Greed"
        else:
            return "Extreme Greed"

    def _fetch_vix_data(self) -> float:
        """Fetch India VIX level and convert to 0-100 score (lower VIX = higher score/greed)."""
        try:
            import yfinance as yf
            ticker = yf.Ticker("^INDIAVIX")
            hist = ticker.history(period="60d")
            if not hist.empty and "Close" in hist.columns and len(hist) >= 5:
                current_vix = float(hist["Close"].iloc[-1])
                sma50 = float(hist["Close"].mean())
                # Low VIX relative to SMA = Greed (high score)
                # High VIX relative to SMA = Fear (low score)
                ratio = current_vix / max(sma50, 1.0)
                # Normal VIX range: ~10 to 30. Ratio ~ 0.7 (greed) to 1.3 (fear)
                score = 50.0 - (ratio - 1.0) * 100.0
                return max(0.0, min(100.0, score))
        except Exception as e:
            logger.warning("Failed to fetch India VIX data: %s", e)

        return 50.0  # Neutral fallback

    def _fetch_nifty_momentum(self) -> float:
        """Calculate Nifty 50 deviation from 125-day SMA and convert to 0-100 score."""
        try:
            import yfinance as yf
            ticker = yf.Ticker("^NSEI")
            hist = ticker.history(period="150d")
            if not hist.empty and "Close" in hist.columns and len(hist) >= 30:
                current_price = float(hist["Close"].iloc[-1])
                sma125 = float(hist["Close"].mean())
                pct_dev = ((current_price - sma125) / max(sma125, 1.0)) * 100.0
                # Deviation typical range: -10% to +10%
                score = 50.0 + (pct_dev * 5.0)
                return max(0.0, min(100.0, score))
        except Exception as e:
            logger.warning("Failed to fetch Nifty momentum data: %s", e)

        return 50.0  # Neutral fallback

    def _fetch_breadth_data(self) -> Dict[str, float]:
        """Fetch stock price strength, breadth, and advance-decline momentum from DB."""
        try:
            latest_breadth = BreadthHistory.query.order_by(
                BreadthHistory.date.desc(),
                BreadthHistory.time.desc()
            ).first()

            if latest_breadth:
                advances = latest_breadth.advances or 0
                declines = latest_breadth.declines or 0
                total = max(advances + declines, 1)

                strength = float(latest_breadth.pct_52high or 50.0)
                breadth = float(latest_breadth.pct_sma50 or 50.0)

                # AD momentum: (Advances - Declines) / Total scaled to 0-100
                ad_ratio = (advances - declines) / total
                ad_momentum = max(0.0, min(100.0, 50.0 + (ad_ratio * 50.0)))

                return {
                    "strength": strength,
                    "breadth": breadth,
                    "ad_momentum": ad_momentum
                }
        except Exception as e:
            logger.warning("Failed to fetch breadth data for Fear & Greed: %s", e)

        return {
            "strength": 50.0,
            "breadth": 50.0,
            "ad_momentum": 50.0
        }

    def compute_fear_greed_index(self) -> Dict[str, Any]:
        """Compute India Fear & Greed Index score and sub-indicator breakdown."""
        vix_score = self._fetch_vix_data()
        nifty_score = self._fetch_nifty_momentum()
        breadth_dict = self._fetch_breadth_data()

        strength_score = breadth_dict["strength"]
        breadth_score = breadth_dict["breadth"]
        ad_score = breadth_dict["ad_momentum"]

        composite = (
            nifty_score * 0.20 +
            strength_score * 0.20 +
            breadth_score * 0.20 +
            vix_score * 0.20 +
            ad_score * 0.20
        )

        composite_score = max(0, min(100, int(round(composite))))
        label = self.get_rating_label(composite_score)

        return {
            "score": composite_score,
            "label": label,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sub_indicators": {
                "momentum": round(nifty_score, 1),
                "strength": round(strength_score, 1),
                "breadth": round(breadth_score, 1),
                "volatility": round(vix_score, 1),
                "ad_momentum": round(ad_score, 1),
            }
        }

    def save_fear_greed_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Persist a computed Fear & Greed snapshot to the database."""
        now_dt = datetime.now(timezone.utc)
        today = now_dt.date()
        now_time = now_dt.time()

        subs = snapshot.get("sub_indicators", {})

        record = FearGreedHistory.query.filter_by(date=today).first()
        if record:
            record.time = now_time
            record.composite_score = int(snapshot["score"])
            record.label = str(snapshot["label"])
            record.momentum_score = float(subs.get("momentum", 50.0))
            record.strength_score = float(subs.get("strength", 50.0))
            record.breadth_score = float(subs.get("breadth", 50.0))
            record.volatility_score = float(subs.get("volatility", 50.0))
            record.ad_score = float(subs.get("ad_momentum", 50.0))
            record.sub_indicators_json = snapshot
        else:
            record = FearGreedHistory(
                date=today,
                time=now_time,
                composite_score=int(snapshot["score"]),
                label=str(snapshot["label"]),
                momentum_score=float(subs.get("momentum", 50.0)),
                strength_score=float(subs.get("strength", 50.0)),
                breadth_score=float(subs.get("breadth", 50.0)),
                volatility_score=float(subs.get("volatility", 50.0)),
                ad_score=float(subs.get("ad_momentum", 50.0)),
                sub_indicators_json=snapshot
            )
            db.session.add(record)

        db.session.commit()

    def get_latest_fear_greed(self) -> Optional[Dict[str, Any]]:
        """Get the most recent Fear & Greed snapshot."""
        record = FearGreedHistory.query.order_by(
            FearGreedHistory.date.desc(),
            FearGreedHistory.time.desc()
        ).first()

        if record:
            return record.to_dict()
        return None


fear_greed_service = FearGreedService()
