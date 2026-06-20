"""
Episodic Pivot (EP) Service for managing EP features, scoring, watchlist triggers, and backtests.
"""
import os
import time
import threading
import sqlite3
import bisect
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from app.extensions import db
from app.models import EpFeature, EpWatchlist, SugarBaby, Fundamental, CorporateEvent, IpoListing, RrgHistory
from app.utils.technical import fetch_historical_prices

# Define thresholds as named constants (Issue 5.2)
EP_CONFIDENCE_HIGH = 0.72
EP_CONFIDENCE_MEDIUM = 0.55
EP_CONFIDENCE_LOW = 0.0

EP_CATALYST_BASE = {
    "BLOWOUT_EARNINGS":  0.90,   # Revenue + profit both 100%+ YoY
    "STRONG_BEAT":       0.70,   # Revenue 40–100% YoY
    "TURNAROUND":        0.80,   # Profit swings from loss to strong profit
    "ORDER_WIN":         0.65,   # Major order announcement (>30% of mktcap)
    "MGMT_CHANGE":       0.55,   # New CEO / promoter buyback
    "THEME_CATALYST":    0.50,   # Government policy, PLI, sector tailwind
    "CAPEX_EXPANSION":   0.45,
    "ABNORMAL_VOLUME":   0.60,   # Volume EP / 9M equivalent (no news yet)
    "BEAT":              0.50,
    "MISS":             -0.30,
    "GUIDANCE_CUT":     -0.80,   # Negative catalyst (Short EP)
    "FRAUD_CONCERN":    -0.90,
    "UNKNOWN":           0.20,
}


def compute_neglect_score(perf_3m, perf_6m, range_60d_pct, avg_vol_rank):
    """
    All inputs normalized/scaled between 0 and 1.
    Higher score indicates greater neglect. Handles None inputs dynamically.
    """
    n_perf_3m = max(0.0, min(1.0, (0.0 - perf_3m) / 40.0 + 0.5)) if perf_3m is not None else None
    n_perf_6m = max(0.0, min(1.0, (0.0 - perf_6m) / 60.0 + 0.5)) if perf_6m is not None else None
    n_range = max(0.0, min(1.0, 1.0 - (range_60d_pct / 40.0))) if range_60d_pct is not None else None
    n_vol_rank = max(0.0, min(1.0, 1.0 - avg_vol_rank)) if avg_vol_rank is not None else None

    weights = []
    vals = []
    if n_perf_3m is not None:
        weights.append(0.35)
        vals.append(n_perf_3m)
    if n_perf_6m is not None:
        weights.append(0.25)
        vals.append(n_perf_6m)
    if n_range is not None:
        weights.append(0.20)
        vals.append(n_range)
    if n_vol_rank is not None:
        weights.append(0.20)
        vals.append(n_vol_rank)

    if not weights:
        return 0.5

    total_w = sum(weights)
    neglect = sum(v * w for v, w in zip(vals, weights)) / total_w
    return round(neglect, 3)


def compute_catalyst_score(event_type, revenue_growth, profit_growth,
                           consecutive_quarters=0, market_cap_cr=None):
    base = EP_CATALYST_BASE.get(event_type, 0.20)
    if base < 0:  # Short EP — return negative value for separation
        return round(base, 3)

    bonus = 0.0
    if revenue_growth and revenue_growth >= 100:
        bonus += 0.10
    elif revenue_growth and revenue_growth >= 50:
        bonus += 0.05

    if profit_growth and profit_growth >= 200:
        bonus += 0.10
    elif profit_growth and profit_growth >= 100:
        bonus += 0.05

    if consecutive_quarters and consecutive_quarters >= 2:
        bonus += 0.05

    if market_cap_cr and market_cap_cr < 5000:
        bonus += 0.05

    return round(min(1.0, base + bonus), 3)


def compute_repricing_score(gap_pct, rel_volume, close_loc, price_change_pct,
                            intraday_range_pct):
    n_gap = max(0.0, min(1.0, gap_pct / 20.0))
    n_vol = max(0.0, min(1.0, (rel_volume - 1.0) / 9.0))
    n_close = max(0.0, min(1.0, close_loc))
    n_strength = max(0.0, min(1.0, (price_change_pct * 0.7 + intraday_range_pct * 0.3) / 15.0))

    repricing = (0.30 * n_gap +
                 0.35 * n_vol +
                 0.20 * n_close +
                 0.15 * n_strength)
    return round(repricing, 3)


def compute_ep_score(neglect_score, catalyst_score, repricing_score,
                     liquidity_ok=True, has_fundamentals=True):
    raw = (0.25 * neglect_score +
           0.35 * abs(catalyst_score) +
           0.30 * repricing_score +
           0.10 * (1.0 if has_fundamentals else 0.0))

    liquidity_adj = 0.0 if liquidity_ok else -0.10
    ep_score = round(max(0.0, min(1.0, raw + liquidity_adj)), 3)
    return ep_score


def assign_ep_type(catalyst_score, event_type, rel_volume, gap_pct,
                   revenue_growth=0, profit_growth=0, day1_messy=False,
                   is_negative_catalyst=False):
    if is_negative_catalyst or catalyst_score < 0:
        return "Short EP"
    if event_type in ("ABNORMAL_VOLUME", "UNKNOWN"):
        return "Volume EP"
    if day1_messy:
        return "Delayed EP"
    if event_type in ("BLOWOUT_EARNINGS", "STRONG_BEAT", "BEAT") and revenue_growth >= 100:
        return "Growth EP"
    if event_type == "TURNAROUND":
        return "Turnaround EP"
    if event_type in ("THEME_CATALYST", "ORDER_WIN", "MGMT_CHANGE", "CAPEX_EXPANSION"):
        return "Story EP"
    if event_type in ("BLOWOUT_EARNINGS", "STRONG_BEAT", "BEAT", "MISS"):
        return "Growth EP"
    return "Growth EP"


def assign_confidence(ep_score, neglect_score, catalyst_score, repricing_score):
    if ep_score >= EP_CONFIDENCE_HIGH and catalyst_score >= 0.70 and repricing_score >= 0.60:
        return "HIGH"
    if ep_score >= EP_CONFIDENCE_MEDIUM:
        return "MEDIUM"
    return "LOW"


class EPService:
    """Service encapsulating business logic for Episodic Pivot (EP) Screener."""

    def __init__(self):
        self.ep_refresh_lock = threading.Lock()
        self.last_ep_refresh_time = 0.0
        self.ep_backtest_prep_lock = threading.Lock()
        self.ep_backtest_prep_status = {
            "running": False,
            "processed": 0,
            "total": 0,
            "current_symbol": "",
            "error": None
        }

    def get_ep_today(self, ep_type: str = 'all', confidence: str = 'all',
                     min_score: float = 0.55, min_mktcap: float = 0.0,
                     max_mktcap: float = 999999.0, exchange: str = 'all',
                     limit: Optional[int] = None, offset: Optional[int] = None) -> Dict[str, Any]:
        """Get latest EP features based on filters and pagination."""
        latest_date = db.session.query(db.func.max(EpFeature.feature_date)).scalar()
        if not latest_date:
            return {"listings": [], "total": 0, "summary": {"HIGH": 0, "MEDIUM": 0, "LOW": 0}, "latest_date": None}

        query = db.session.query(EpFeature).filter(EpFeature.feature_date == latest_date)
        query = query.filter(EpFeature.ep_score >= min_score)

        if ep_type != 'all':
            query = query.filter(EpFeature.ep_type == ep_type)
        if confidence != 'all':
            query = query.filter(EpFeature.confidence == confidence)
        if min_mktcap > 0.0:
            query = query.filter(EpFeature.market_cap_cr >= min_mktcap)
        if max_mktcap < 999999.0:
            query = query.filter(EpFeature.market_cap_cr <= max_mktcap)
        if exchange != 'all':
            query = query.filter(EpFeature.exchange == exchange)

        total_count = query.count()

        # Build summary
        summary = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        summary_query = db.session.query(EpFeature.confidence, db.func.count(EpFeature.id))\
                                  .filter(EpFeature.feature_date == latest_date)\
                                  .group_by(EpFeature.confidence).all()
        for conf, cnt in summary_query:
            if conf in summary:
                summary[conf] = cnt

        # Sorting & pagination
        query = query.order_by(EpFeature.ep_score.desc())
        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)

        listings = []
        for feat in query.all():
            item = feat.to_dict()
            if item.get("price_change_pct") is None:
                item["price_change_pct"] = item.get("gap_pct") or 0.0
                
            # Issue 4.5: Query historical EP score to show trend delta
            # We look for the previous EP record for the same symbol
            prev_feat = EpFeature.query.filter(
                EpFeature.symbol == feat.symbol,
                EpFeature.feature_date < latest_date
            ).order_by(EpFeature.feature_date.desc()).first()
            if prev_feat:
                item["prev_ep_score"] = prev_feat.ep_score
            else:
                item["prev_ep_score"] = None
                
            listings.append(item)

        return {
            "listings": listings,
            "total": total_count,
            "summary": summary,
            "latest_date": latest_date.strftime('%Y-%m-%d')
        }

    def get_ep_detail(self, symbol: str) -> Dict[str, Any]:
        """Fetch detailed analytics for a single stock."""
        symbol_upper = symbol.upper().strip()
        feat = EpFeature.query.filter_by(symbol=symbol_upper).order_by(EpFeature.feature_date.desc()).first()
        if not feat:
            raise ValueError(f"Symbol {symbol} features not found")

        detail = feat.to_dict()

        # Price history
        ticker = f"{symbol_upper}.NS"
        history = fetch_historical_prices(ticker, range_str="6mo")
        detail["history"] = history or []

        # Corporate events
        events = CorporateEvent.query.filter_by(symbol=symbol_upper).order_by(CorporateEvent.event_date.desc()).limit(10).all()
        detail["corporate_events"] = [ev.to_dict() for ev in events]

        # Fundamentals
        funds = Fundamental.query.filter_by(symbol=symbol_upper).order_by(Fundamental.result_date.desc()).limit(8).all()
        detail["fundamentals"] = [f.to_dict() for f in funds]

        # Issue 5.3: Calculate QoQ trend indicators based on Net Profit & Revenue YoY
        for f_dict in detail["fundamentals"]:
            rev_yoy = f_dict.get("revenue_yoy_pct")
            prof_yoy = f_dict.get("net_profit_yoy_pct")
            f_dict["revenue_trend"] = "▲" if (rev_yoy and rev_yoy > 0) else ("▼" if (rev_yoy and rev_yoy < 0) else "—")
            f_dict["profit_trend"] = "▲" if (prof_yoy and prof_yoy > 0) else ("▼" if (prof_yoy and prof_yoy < 0) else "—")

        # Stale data refresh check
        needs_refresh = not detail["fundamentals"]
        if detail["fundamentals"]:
            try:
                latest_res_date = datetime.strptime(detail["fundamentals"][0]["result_date"], "%Y-%m-%d")
                if (datetime.now() - latest_res_date).days > 180:
                    needs_refresh = True
            except Exception:
                pass

        if needs_refresh:
            try:
                from app.api.v1.legacy_routes import fetch_screener_fundamentals, compute_yoy_metrics
                quarters_data = fetch_screener_fundamentals(symbol_upper)
                if quarters_data:
                    quarters_data = compute_yoy_metrics(quarters_data)
                    Fundamental.query.filter_by(symbol=symbol_upper).delete()
                    for q in quarters_data:
                        new_f = Fundamental(
                            symbol=symbol_upper,
                            exchange=detail.get('exchange', 'NSE'),
                            result_date=datetime.strptime(q.get('result_date') or q['date_key'], "%Y-%m-%d").date(),
                            quarter=q['quarter'],
                            revenue=q['revenue'],
                            revenue_yoy_pct=q['revenue_yoy_pct'],
                            net_profit=q['net_profit'],
                            net_profit_yoy_pct=q['net_profit_yoy_pct'],
                            eps=q['eps'],
                            eps_yoy_pct=q.get('eps_yoy_pct'),
                            surprise_type=q.get('surprise_type', 'UNKNOWN'),
                            consecutive_quarters_growth=q.get('consecutive_quarters_growth', 0),
                            source=q.get('source', 'unknown')
                        )
                        db.session.add(new_f)
                    db.session.commit()
                    # Re-query
                    funds = Fundamental.query.filter_by(symbol=symbol_upper).order_by(Fundamental.result_date.desc()).limit(8).all()
                    detail["fundamentals"] = [f.to_dict() for f in funds]
                    for f_dict in detail["fundamentals"]:
                        rev_yoy = f_dict.get("revenue_yoy_pct")
                        prof_yoy = f_dict.get("net_profit_yoy_pct")
                        f_dict["revenue_trend"] = "▲" if (rev_yoy and rev_yoy > 0) else ("▼" if (rev_yoy and rev_yoy < 0) else "—")
                        f_dict["profit_trend"] = "▲" if (prof_yoy and prof_yoy > 0) else ("▼" if (prof_yoy and prof_yoy < 0) else "—")
            except Exception as ref_ex:
                print(f"[EP Detail] Lazy refresh failed for {symbol_upper}: {ref_ex}")

        # Watchlist info
        wl = EpWatchlist.query.filter_by(symbol=symbol_upper).order_by(EpWatchlist.id.desc()).first()
        if wl:
            detail["watchlist_status"] = wl.status
            detail["watchlist_stop"] = wl.stop_price
            detail["watchlist_notes"] = wl.notes
        else:
            detail["watchlist_status"] = None
            detail["watchlist_stop"] = None
            detail["watchlist_notes"] = None

        # Sugar baby info
        sb = SugarBaby.query.filter_by(symbol=symbol_upper, is_active=1).first()
        detail["is_sugar_baby"] = 1 if sb else 0

        return detail

    def get_ep_themes(self, types_param: str = '') -> List[Dict[str, Any]]:
        """Group latest EP candidates into themes/sectors."""
        latest_date = db.session.query(db.func.max(EpFeature.feature_date)).scalar()
        if not latest_date:
            return []

        if types_param.lower() == "all":
            allowed_types = ['Story EP', 'Volume EP', 'Growth EP', 'Turnaround EP']
        elif types_param:
            allowed_types = [t.strip() for t in types_param.split(',')]
        else:
            allowed_types = ['Story EP', 'Volume EP']

        features = EpFeature.query.filter(
            EpFeature.feature_date == latest_date,
            EpFeature.ep_type.in_(allowed_types)
        ).all()

        themes_map = {}
        for feat in features:
            sym = feat.symbol
            listing = IpoListing.query.filter_by(ticker=sym).first()
            sect = listing.sector if (listing and listing.sector) else "General Markets"
            themes_map.setdefault(sect, []).append(feat.to_dict())

        themes = []
        for sect, items in themes_map.items():
            avg_score = sum(item["ep_score"] for item in items) / len(items)
            themes.append({
                "theme": sect,
                "count": len(items),
                "avg_score": round(avg_score, 2),
                "symbols": [item["symbol"] for item in items]
            })

        themes.sort(key=lambda x: x["count"], reverse=True)
        return themes

    def get_ep_sector_rotation(self) -> List[Dict[str, Any]]:
        """Get sector rotation details blended with active EP watchlist counts."""
        watchlist_symbols = [r.symbol for r in EpWatchlist.query.filter_by(status='ACTIVE').all()]
        sectors = [r[0] for r in db.session.query(RrgHistory.sector).distinct().all()]

        sector_rotation_list = []
        for sector in sectors:
            row = RrgHistory.query.filter_by(sector=sector).order_by(RrgHistory.snapped_at.desc()).first()
            if not row:
                continue

            sector_wl_count = 0
            for sym in watchlist_symbols:
                listing = IpoListing.query.filter_by(ticker=sym).first()
                if listing and listing.sector == sector:
                    sector_wl_count += 1

            sector_rotation_list.append({
                "sector": sector,
                "quadrant": row.quadrant,
                "score": row.score,
                "jdk_rs": round(row.jdk_rs, 2),
                "jdk_rs_momentum": round(row.jdk_rs_momentum, 2),
                "active_ep_count": sector_wl_count,
                "week": row.week
            })

        sector_rotation_list.sort(key=lambda x: x["score"], reverse=True)
        return sector_rotation_list

    def get_ep_sugar_babies(self) -> List[Dict[str, Any]]:
        """Fetch active sugar babies list."""
        babies = SugarBaby.query.filter_by(is_active=1).order_by(SugarBaby.symbol.asc()).all()
        return [b.to_dict() for b in babies]

    def add_to_sugar_babies(self, symbol: str, exchange: str = 'NSE',
                            notes: str = '', is_active: int = 1) -> bool:
        """Add or update an active Sugar Baby."""
        symbol_upper = symbol.upper().strip()
        if not symbol_upper:
            raise ValueError("Symbol is required")

        sb = SugarBaby.query.filter_by(symbol=symbol_upper).first()
        episode_count = EpFeature.query.filter(EpFeature.symbol == symbol_upper, EpFeature.ep_score >= 0.55).count()

        if sb:
            sb.notes = notes
            sb.is_active = is_active
            sb.exchange = exchange
            sb.episode_count = episode_count
        else:
            sb = SugarBaby(
                symbol=symbol_upper,
                exchange=exchange,
                added_date=datetime.now().date(),
                avg_burst_pct=0.0,
                avg_burst_days=0.0,
                episode_count=episode_count,
                notes=notes,
                is_active=is_active
            )
            db.session.add(sb)

        db.session.commit()
        return True

    def refresh_ep_screener(self) -> bool:
        """Trigger background EP screening."""
        with self.ep_refresh_lock:
            current_time = time.time()
            if current_time - self.last_ep_refresh_time < 60:
                return False
            self.last_ep_refresh_time = current_time

        def _bg_refresh():
            with self.ep_refresh_lock:
                try:
                    from app.api.v1.legacy_routes import refresh_ep_screener as legacy_refresh
                    legacy_refresh()
                except Exception as e:
                    print(f"Error in background EP refresh: {e}")

        t = threading.Thread(target=_bg_refresh)
        t.start()
        return True

    def prep_backtest(self, start_date: str = "2019-01-01", end_date: str = "2025-12-31",
                      symbols_str: str = "") -> bool:
        """Trigger background historical backfill for backtesting preparation."""
        with self.ep_backtest_prep_lock:
            if self.ep_backtest_prep_status["running"]:
                return False

            symbols = None
            if symbols_str and symbols_str.lower() != "all" and symbols_str.strip():
                symbols = [s.strip().upper() for s in symbols_str.split(',') if s.strip()]

            self.ep_backtest_prep_status.update({
                "running": True,
                "error": None,
                "processed": 0,
                "total": 0,
                "current_symbol": ""
            })

        def _bg_prep():
            try:
                from app.api.v1.legacy_routes import run_historical_backfill
                # Capture progress updates by writing directly to self.ep_backtest_prep_status in backfill,
                # but since backfill uses the global state in legacy_routes, let's bind them
                import app.api.v1.legacy_routes as lr
                lr.ep_backtest_prep_status = self.ep_backtest_prep_status
                run_historical_backfill(symbols, start_date, end_date)
            except Exception as e:
                self.ep_backtest_prep_status["error"] = str(e)
            finally:
                self.ep_backtest_prep_status["running"] = False

        t = threading.Thread(target=_bg_prep)
        t.start()
        return True


# Singleton instance
ep_service = EPService()
