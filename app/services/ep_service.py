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
# --- EP model loading helpers ---
from pathlib import Path
from flask import current_app

def _load_ep_cache() -> dict:
    """Load cached EP explanations from on-disk JSON."""
    cache_path = os.path.join(current_app.instance_path if current_app else '.', 'ep_explanations_cache.json')
    if os.path.exists(cache_path):
        try:
            import json
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_ep_cache(cache: dict):
    """Save EP explanations to on-disk JSON."""
    if current_app:
        os.makedirs(current_app.instance_path, exist_ok=True)
        cache_path = os.path.join(current_app.instance_path, 'ep_explanations_cache.json')
    else:
        cache_path = 'ep_explanations_cache.json'
    try:
        import json
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

_MODEL = None
_MANIFEST = None

def _load_ep_model():
    """Load the XGBoost model and its manifest lazily.

    Returns a tuple (model, manifest). Raises FileNotFoundError if missing.
    """
    global _MODEL, _MANIFEST
    if _MODEL is None or _MANIFEST is None:
        model_path = current_app.config.get('EP_MODEL_PATH')
        if not model_path:
            raise FileNotFoundError('EP_MODEL_PATH not configured')
        manifest_path = Path(model_path).with_name(Path(model_path).stem + '_manifest.json')
        if not os.path.exists(model_path) or not os.path.exists(manifest_path):
            raise FileNotFoundError(f"EP model or manifest not found at {model_path}")
        import joblib, json
        _MODEL = joblib.load(model_path)
        with open(manifest_path, 'r') as f:
            _MANIFEST = json.load(f)
    return _MODEL, _MANIFEST

def predict_ep_score(features: dict) -> float:
    """Predict EP score using the loaded model.

    Supports both XGBRegressor (v2.0+) and XGBClassifier (legacy).
    Features dict is ordered according to the manifest's ``feature_order``.
    Returns a score in [0, 1] rounded to three decimals.
    """
    try:
        model, manifest = _load_ep_model()
    except Exception as e:
        # Log and fallback to original hand-crafted score elsewhere
        current_app.logger.warning(f"EP model load failed: {e}")
        raise
    import numpy as np

    # Derive is_short_ep from catalyst_score if not explicitly provided
    if "is_short_ep" not in features:
        catalyst = features.get("catalyst_score", 0.0)
        features["is_short_ep"] = 1.0 if (catalyst is not None and catalyst < 0) else 0.0

    ordered = [features.get(col, 0.0) for col in manifest.get('feature_order', [])]
    arr = np.array([ordered])

    model_type = manifest.get("model_type", "XGBClassifier")
    if model_type == "XGBRegressor" or not hasattr(model, 'predict_proba'):
        # Regression model: predict() returns a continuous score
        raw = float(model.predict(arr)[0])
        score = max(0.0, min(1.0, raw))
    else:
        # Classification model: predict_proba() returns class probabilities
        preds = model.predict_proba(arr)
        preds = np.array(preds)
        score = float(preds[0, 1])

    return round(score, 3)

# Define thresholds as named constants (Issue 5.2)
EP_CONFIDENCE_HIGH = 0.45
EP_CONFIDENCE_MEDIUM = 0.35
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
                 
    # Penalize failed breakouts (closing in the lower half of the daily range)
    if close_loc < 0.50:
        # Scale down smoothly (e.g. close_loc=0.10 becomes 0.2x of original repricing score)
        repricing *= (close_loc / 0.50)
        
    # Penalize red days (closed negative or flat compared to yesterday's close)
    if price_change_pct <= 0:
        repricing *= 0.1
        
    return round(repricing, 3)


def compute_ep_score(neglect_score, catalyst_score, repricing_score,
                     liquidity_ok=True, has_fundamentals=True, **kwargs):
    """Compute EP score using ML model if available, otherwise fallback to hand‑crafted weighted sum."""
    # Enforce positive price action for positive EPs
    price_change_pct = kwargs.get("price_change_pct")
    if catalyst_score >= 0 and price_change_pct is not None and price_change_pct <= 0:
        return 0.0

    # Attempt model prediction
    try:
        features = {
            "neglect_score": neglect_score,
            "catalyst_score": catalyst_score,
            "repricing_score": repricing_score,
            "liquidity_ok": 1 if liquidity_ok else 0,
            "has_fundamentals": 1 if has_fundamentals else 0,
        }
        features.update(kwargs)
        
        # Ensure any boolean values are mapped to 1/0
        features = {k: (1 if v else 0) if isinstance(v, bool) else v for k, v in features.items()}
                
        return predict_ep_score(features)
    except Exception as e:
        # Log fallback if possible
        try:
            from flask import current_app
            current_app.logger.warning(f"EP model prediction failed ({e}); using fallback scoring.")
        except Exception:
            pass
        # Hand‑crafted fallback logic (original implementation)
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
    # HIGH confidence when EP score meets medium threshold and key components are strong
    if ep_score >= EP_CONFIDENCE_MEDIUM and catalyst_score >= 0.70 and repricing_score >= 0.60:
        return "HIGH"
    # MEDIUM confidence when EP score meets medium threshold (component thresholds not required)
    if ep_score >= EP_CONFIDENCE_MEDIUM:
        return "MEDIUM"
    return "LOW"


class EPService:
    """Service encapsulating business logic for Episodic Pivot (EP) Screener."""

    def __init__(self):
        self.ep_refresh_lock = threading.Lock()
        self.last_ep_refresh_time = 0.0
        self.last_refresh_datetime = None
        self.is_refreshing = False
        self.ep_backtest_prep_lock = threading.Lock()
        self.ep_backtest_prep_status = {
            "running": False,
            "processed": 0,
            "total": 0,
            "current_symbol": "",
            "error": None
        }

    def get_ep_today(self, ep_type: str = 'all', confidence: str = 'all',
                     min_score: float = 0.10, min_mktcap: float = 0.0,
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
        """Fetch detailed analytics for a single stock.

        Falls back to EpWatchlist when no EpFeature row exists (e.g. stock was
        added on a previous scan day and is no longer in today's EP results).
        """
        symbol_upper = symbol.upper().strip()
        feat = EpFeature.query.filter_by(symbol=symbol_upper).order_by(EpFeature.feature_date.desc()).first()
        if not feat:
            # Try to build a minimal response from the watchlist entry
            wl_entry = EpWatchlist.query.filter_by(symbol=symbol_upper).order_by(EpWatchlist.id.desc()).first()
            if not wl_entry:
                raise ValueError(f"Symbol {symbol} not found in EP features or watchlist")
            detail: Dict[str, Any] = {
                "symbol": symbol_upper,
                "exchange": wl_entry.exchange or "NSE",
                "ep_type": wl_entry.ep_type or "Unknown",
                "ep_score": wl_entry.ep_score,
                "confidence": "—",
                "feature_date": str(wl_entry.catalyst_date) if wl_entry.catalyst_date else None,
                "catalyst_score": None, "neglect_score": None, "repricing_score": None,
                "close_location": None, "rvol": None, "avg_volume": None,
                "mktcap_cr": None, "sector": None,
                "watchlist_status": wl_entry.status,
                "watchlist_stop": wl_entry.stop_price,
                "watchlist_notes": wl_entry.notes,
                "ep_score_prev": None,
                "history": [], "corporate_events": [], "fundamentals": [],
            }
            history = fetch_historical_prices(f"{symbol_upper}.NS", range_str="6mo")
            detail["history"] = history or []
            # Safe corporate events query (avoids SQLAlchemy date parse failure)
            try:
                rows = db.session.execute(
                    db.text("SELECT id, symbol, exchange, event_date, event_type, headline, sentiment, catalyst_score, raw_url, nlp_sentiment_score, nlp_category, summary, impact_magnitude FROM corporate_events WHERE symbol = :s ORDER BY id DESC LIMIT 10"),
                    {"s": symbol_upper}
                ).fetchall()
                detail["corporate_events"] = [dict(r._mapping) for r in rows]
            except Exception:
                detail["corporate_events"] = []
            funds = Fundamental.query.filter_by(symbol=symbol_upper).order_by(Fundamental.result_date.desc()).limit(8).all()
            detail["fundamentals"] = [f.to_dict() for f in funds]
            for f_dict in detail["fundamentals"]:
                rev_yoy = f_dict.get("revenue_yoy_pct")
                prof_yoy = f_dict.get("net_profit_yoy_pct")
                f_dict["revenue_trend"] = "▲" if (rev_yoy and rev_yoy > 0) else ("▼" if (rev_yoy and rev_yoy < 0) else "—")
                f_dict["profit_trend"] = "▲" if (prof_yoy and prof_yoy > 0) else ("▼" if (prof_yoy and prof_yoy < 0) else "—")
            sb = SugarBaby.query.filter_by(symbol=symbol_upper, is_active=1).first()
            detail["is_sugar_baby"] = 1 if sb else 0
            return detail

        detail = feat.to_dict()

        # Price history
        ticker = f"{symbol_upper}.NS"
        history = fetch_historical_prices(ticker, range_str="6mo")
        detail["history"] = history or []

        # Corporate events — use raw SQL ORDER BY id to avoid SQLAlchemy crashing
        # on 'DD-Mon-YYYY' date strings that may exist in the event_date column.
        try:
            rows = db.session.execute(
                db.text("SELECT id, symbol, exchange, event_date, event_type, headline, sentiment, catalyst_score, raw_url, nlp_sentiment_score, nlp_category, summary, impact_magnitude FROM corporate_events WHERE symbol = :s ORDER BY id DESC LIMIT 10"),
                {"s": symbol_upper}
            ).fetchall()
            detail["corporate_events"] = [dict(r._mapping) for r in rows]
        except Exception:
            detail["corporate_events"] = []

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

        # AI Thesis & Reasoning
        feature_date = detail.get("feature_date") or "no_date"
        cache_key = f"{symbol_upper}_{feature_date}"
        
        # Avoid circular import by importing inside
        from app.services.ai_service import ai_service
        
        cache = _load_ep_cache()
        if cache_key in cache:
            detail["ai_thesis"] = cache[cache_key].get("thesis")
            detail["ai_reasoning"] = cache[cache_key].get("reasoning")
        else:
            # Generate new thesis & reasoning
            technicals = {
                "ep_score": detail.get("ep_score"),
                "neglect_score": detail.get("neglect_score"),
                "catalyst_score": detail.get("catalyst_score"),
                "repricing_score": detail.get("repricing_score"),
                "market_cap_cr": detail.get("market_cap_cr") or detail.get("mktcap_cr"),
                "rel_volume": detail.get("rel_volume") or detail.get("rvol"),
                "close_loc": detail.get("close_loc") or detail.get("close_location"),
                "price_change_pct": detail.get("price_change_pct"),
            }
            financials = detail.get("fundamentals", [])
            announcements = detail.get("corporate_events", [])
            
            ai_res = ai_service.generate_thesis_and_reasoning(
                symbol_upper, technicals, financials, announcements
            )
            
            detail["ai_thesis"] = ai_res.get("thesis")
            detail["ai_reasoning"] = ai_res.get("reasoning")
            
            # Save to cache
            cache[cache_key] = {
                "thesis": ai_res.get("thesis"),
                "reasoning": ai_res.get("reasoning")
            }
            _save_ep_cache(cache)

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
            if self.is_refreshing:
                return False
            current_time = time.time()
            if current_time - self.last_ep_refresh_time < 60:
                return False
            self.last_ep_refresh_time = current_time
            self.is_refreshing = True

        def _bg_refresh():
            try:
                from app.api.v1.legacy_routes import refresh_ep_screener as legacy_refresh
                legacy_refresh()
                self.last_refresh_datetime = datetime.now().isoformat()
            except Exception as e:
                print(f"Error in background EP refresh: {e}")
            finally:
                with self.ep_refresh_lock:
                    self.is_refreshing = False

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
