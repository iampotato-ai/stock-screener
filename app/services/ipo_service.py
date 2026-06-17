"""
IPO service for managing IPO listings and metrics.
"""
from typing import List, Dict, Any, Optional
from app.database import get_db
import sqlite3
import time
import threading
from datetime import datetime
from app import (
    fetch_historical_prices,
    compute_swing_score,
    classify_technical_pattern,
    classify_momentum_phase,
    _calculate_rsi
)
from app.utils.journal_math import compute_pnl_and_r


class IPOService:
    """Service for IPO-related operations."""

    def __init__(self):
        self.refresh_lock = threading.Lock()
        self.last_refresh_time = 0.0

    def get_ipo_listings(self, exchange_param: str = 'all', days_param: str = 'all',
                        phase_param: str = 'all', volume_alert_param: str = 'all',
                        min_volume_param: str = 'all', limit: Optional[int] = None,
                        offset: Optional[int] = None, sort_by: str = 'listing_date',
                        order: str = 'DESC') -> Dict[str, Any]:
        """
        Get IPO listings with filtering and pagination.

        Returns:
            Dictionary containing listings, total count, and summary
        """
        conn = None
        try:
            where_clauses = []
            params = []

            # Volume alert filters
            if volume_alert_param != 'all' and volume_alert_param != '':
                selected_alerts = volume_alert_param.split(',')
                alert_clauses = []
                for alert in selected_alerts:
                    if alert == 'ppv':
                        alert_clauses.append("is_blue_bar = 1")
                    elif alert == 'vol-surge':
                        alert_clauses.append("is_green_bar = 1")
                    elif alert == 'dry-vol':
                        alert_clauses.append("is_orange_bar = 1")
                if alert_clauses:
                    where_clauses.append(f"({ ' OR '.join(alert_clauses) })")

            # Minimum volume filter
            min_vol = self._parse_volume_param(min_volume_param)
            if min_vol is not None:
                where_clauses.append("volume >= ?")
                params.append(min_vol)

            # Exchange filter
            if exchange_param != 'all':
                if exchange_param == 'NSE':
                    where_clauses.append("exchange = 'NSE'")
                elif exchange_param == 'BSE':
                    where_clauses.append("exchange = 'BSE'")

            # Days filter
            if days_param != 'all':
                max_days = None
                if days_param == '1m': max_days = 30
                elif days_param == '3m': max_days = 90
                elif days_param == '6m': max_days = 180
                elif days_param == '1y': max_days = 365
                elif days_param == '18m': max_days = 548
                else:
                    try:
                        max_days = int(days_param)
                    except ValueError:
                        pass
                if max_days is not None:
                    where_clauses.append("days_since_listing <= ?")
                    params.append(max_days)

            # Phase filter
            if phase_param != 'all':
                where_clauses.append("momentum_phase = ?")
                params.append(phase_param)

            where_str = ""
            if where_clauses:
                where_str = f" WHERE {' AND '.join(where_clauses)}"

            conn = sqlite3.connect('scan_history.db', timeout=30.0)
            c = conn.cursor()

            # Count total recent IPOs (avoid double counting when exchange is 'all')
            if exchange_param == 'all':
                c.execute(f"SELECT COUNT(DISTINCT company_name) FROM ipo_metrics_cache{where_str}", tuple(params))
            else:
                c.execute(f"SELECT COUNT(*) FROM ipo_metrics_cache{where_str}", tuple(params))
            total_count = c.fetchone()[0]

            # Calculate summary phase counts
            summary_clauses = []
            summary_params = []
            if exchange_param != 'all':
                if exchange_param == 'NSE':
                    summary_clauses.append("exchange = 'NSE'")
                elif exchange_param == 'BSE':
                    summary_clauses.append("exchange = 'BSE'")
            if days_param != 'all':
                max_days = None
                if days_param == '1m': max_days = 30
                elif days_param == '3m': max_days = 90
                elif days_param == '6m': max_days = 180
                elif days_param == '1y': max_days = 365
                elif days_param == '18m': max_days = 548
                else:
                    try:
                        max_days = int(days_param)
                    except ValueError:
                        pass
                if max_days is not None:
                    summary_clauses.append("days_since_listing <= ?")
                    summary_params.append(max_days)

            if volume_alert_param != 'all' and volume_alert_param != '':
                selected_alerts = volume_alert_param.split(',')
                alert_clauses = []
                for alert in selected_alerts:
                    if alert == 'ppv':
                        alert_clauses.append("is_blue_bar = 1")
                    elif alert == 'vol-surge':
                        alert_clauses.append("is_green_bar = 1")
                    elif alert == 'dry-vol':
                        alert_clauses.append("is_orange_bar = 1")
                if alert_clauses:
                    summary_clauses.append(f"({ ' OR '.join(alert_clauses) })")

            if min_vol is not None:
                summary_clauses.append("volume >= ?")
                summary_params.append(min_vol)

            summary_where = ""
            if summary_clauses:
                summary_where = f" WHERE {' AND '.join(summary_clauses)}"

            if exchange_param == 'all':
                c.execute(f"SELECT momentum_phase, COUNT(DISTINCT company_name) FROM ipo_metrics_cache{summary_where} GROUP BY momentum_phase", tuple(summary_params))
            else:
                c.execute(f"SELECT momentum_phase, COUNT(*) FROM ipo_metrics_cache{summary_where} GROUP BY momentum_phase", tuple(summary_params))

            summary_rows = c.fetchall()
            summary = {"HOT": 0, "STABLE": 0, "FADING": 0, "BROKEN": 0}
            for phase, cnt in summary_rows:
                if phase in summary:
                    summary[phase] = cnt

            # Sorting
            allowed_sort_cols = [
                'ticker', 'company_name', 'listing_date', 'exchange', 'sector', 'issue_price',
                'listing_gain_pct', 'current_vs_issue_pct', 'current_vs_listing_pct', 'days_since_listing',
                'rvol_ratio', 'above_listing_high', 'drawdown_from_ath', 'swing_score', 'pattern_name',
                'momentum_phase', 'current_price', 'volume', 'change_pct', 'day_low', 'day_high',
                'is_blue_bar', 'is_green_bar', 'is_orange_bar', 'day_range_pct'
            ]
            if sort_by not in allowed_sort_cols:
                sort_by = 'listing_date'

            order_by_expr = sort_by
            if sort_by == 'day_range_pct':
                order_by_expr = "CASE WHEN (day_high - day_low) > 0 THEN ((current_price - day_low) * 100.0 / (day_high - day_low)) ELSE -1.0 END"

            query = f"""
                SELECT ticker, company_name, listing_date, exchange, sector, issue_price,
                       listing_gain_pct, current_vs_issue_pct, current_vs_listing_pct, days_since_listing,
                       rvol_ratio, above_listing_high, drawdown_from_ath, swing_score, pattern_name,
                       momentum_phase, current_price, volume, change_pct, day_low, day_high,
                       is_blue_bar, is_green_bar, is_orange_bar, cached_at
                FROM ipo_metrics_cache
                {where_str}
                ORDER BY {order_by_expr} {order}
            """

            limit_offset_params = list(params)
            if limit is not None:
                try:
                    limit_val = int(limit)
                    query += " LIMIT ?"
                    limit_offset_params.append(limit_val)
                    if offset is not None:
                        try:
                            offset_val = int(offset)
                            query += " OFFSET ?"
                            limit_offset_params.append(offset_val)
                        except ValueError:
                            pass
                except ValueError:
                    pass

            c.execute(query, tuple(limit_offset_params))
            rows = c.fetchall()

            cols = [
                'ticker', 'company_name', 'listing_date', 'exchange', 'sector', 'issue_price',
                'listing_gain_pct', 'current_vs_issue_pct', 'current_vs_listing_pct', 'days_since_listing',
                'rvol_ratio', 'above_listing_high', 'drawdown_from_ath', 'swing_score', 'pattern_name',
                'momentum_phase', 'current_price', 'volume', 'change_pct', 'day_low', 'day_high',
                'is_blue_bar', 'is_green_bar', 'is_orange_bar', 'cached_at'
            ]

            listings = []
            for r in rows:
                ipo = dict(zip(cols, r))
                # Recalculate days_since_listing dynamically so it never goes stale
                try:
                    lst_dt = datetime.strptime(ipo["listing_date"], "%Y-%m-%d")
                    ipo["days_since_listing"] = (datetime.now() - lst_dt).days
                except Exception:
                    pass  # keep DB value if parsing fails
                listings.append(ipo)

            return {
                "listings": listings,
                "total": total_count,
                "summary": summary
            }
        except Exception as e:
            raise e
        finally:
            if conn:
                conn.close()

    def get_ipo_detail(self, ticker: str) -> Dict[str, Any]:
        """
        Get detailed information for a specific IPO ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary containing IPO detail and history
        """
        conn = None
        try:
            conn = sqlite3.connect('scan_history.db', timeout=30.0)
            c = conn.cursor()
            c.execute("SELECT * FROM ipo_metrics_cache WHERE ticker = ?", (ticker,))
            row = c.fetchone()

            if not row:
                # Check if exists in ipo_listings at least
                c.execute("SELECT ticker FROM ipo_listings WHERE ticker = ?", (ticker,))
                exists = c.fetchone()
                if not exists:
                    raise ValueError(f"Ticker {ticker} not found in IPO listings")
                else:
                    raise ValueError(f"Ticker {ticker} is not cached yet")

            cols = [description[0] for description in c.description]
            detail = dict(zip(cols, row))

            # Get price history
            history = fetch_historical_prices(ticker, range_str="1y")
            detail["history"] = history or []

            return detail
        except Exception as e:
            raise e
        finally:
            if conn:
                conn.close()

    def refresh_ipo_metrics(self) -> bool:
        """
        Refresh IPO metrics cache from listings.

        Returns:
            True if refresh started, False if cooldown active
        """
        current_time = time.time()
        if current_time - self.last_refresh_time < 60:
            return False  # Cooldown active

        # Start background thread to refresh cache asynchronously
        def _bg_refresh():
            with self.refresh_lock:
                try:
                    self._refresh_ipo_metrics_internal()
                except Exception as e:
                    print(f"Error in background IPO refresh: {e}")

        t = threading.Thread(target=_bg_refresh)
        t.start()

        self.last_refresh_time = current_time
        return True

    def _refresh_ipo_metrics_internal(self):
        """Internal method to refresh IPO metrics."""
        conn = None
        try:
            conn = sqlite3.connect('scan_history.db')
            c = conn.cursor()
            c.execute("DELETE FROM ipo_metrics_cache WHERE ticker NOT IN (SELECT ticker FROM ipo_listings)")
            conn.commit()
            c.execute("SELECT ticker, company_name, listing_date, issue_price, listing_close, exchange, sector FROM ipo_listings")
            listings = c.fetchall()
            conn.close()

            from datetime import datetime

            def _update_single(row):
                ticker, company_name, listing_date, issue_price, listing_close, exchange, sector = row
                try:
                    # Fetch history
                    history = fetch_historical_prices(ticker, range_str="2y")
                    if not history:
                        return

                    closes  = [float(h["close"])  for h in history]
                    highs   = [float(h["high"])   for h in history]
                    volumes = [float(h["volume"]) for h in history]
                    lows    = [float(h["low"])    for h in history]

                    if not closes:
                        return

                    current_price = closes[-1]
                    current_vol   = volumes[-1]
                    # lows/highs are always populated when closes is non-empty (same Yahoo response);
                    # the 'else' branch is a safety net for unexpected edge cases only.
                    current_low  = lows[-1]  if lows  else current_price
                    current_high = highs[-1] if highs else current_price
                    avg_vol_20d  = sum(volumes[-20:]) / len(volumes[-20:]) if volumes else 1.0

                    # Listing close
                    lst_close = listing_close if listing_close else closes[0]

                    # Calculations
                    listing_gain_pct        = ((lst_close - issue_price) / issue_price * 100) if issue_price else 0.0
                    current_vs_issue_pct    = ((current_price - issue_price) / issue_price * 100) if issue_price else 0.0
                    current_vs_listing_pct  = ((current_price - lst_close) / lst_close * 100) if lst_close else 0.0

                    # Days since listing
                    try:
                        lst_dt = datetime.strptime(listing_date, "%Y-%m-%d").date()
                        days_since = (datetime.now().date() - lst_dt).days
                    except Exception:
                        days_since = 0

                    rvol_ratio = (current_vol / avg_vol_20d) if avg_vol_20d > 0 else 1.0
                    ath = max(highs) if highs else current_price
                    above_listing_high = 1 if current_price >= max(closes) * 0.98 else 0
                    drawdown_from_ath  = ((current_price - ath) / ath * 100) if ath else 0.0

                    # Calculate volume indicators
                    # 50-period Volume SMA
                    vols = [float(h["volume"]) for h in history if h.get("volume") is not None]
                    if len(vols) >= 50:
                        volume_sma_50 = sum(vols[-50:]) / 50.0
                    elif vols:
                        volume_sma_50 = sum(vols) / len(vols)
                    else:
                        volume_sma_50 = 0.0

                    # Highest down-day volume of the last 10 down-days
                    down_day_vols = []
                    for i in range(1, len(history)):
                        current_close = float(history[i]["close"])
                        prev_close = float(history[i-1]["close"])
                        if current_close < prev_close:
                            down_day_vols.append(float(history[i]["volume"]))

                    if len(down_day_vols) >= 10:
                        max_down_vol_10 = max(down_day_vols[-10:])
                    elif down_day_vols:
                        max_down_vol_10 = max(down_day_vols)
                    else:
                        max_down_vol_10 = 0.0

                    # Determine bar flags
                    is_up_day = closes[-1] > closes[-2] if len(closes) >= 2 else False
                    is_blue = 1 if (is_up_day and max_down_vol_10 > 0 and current_vol > max_down_vol_10) else 0
                    is_green = 1 if (is_up_day and volume_sma_50 > 0 and current_vol > volume_sma_50 and not is_blue) else 0
                    is_orange = 1 if (volume_sma_50 > 0 and current_vol <= volume_sma_50 / 5.0) else 0

                    # Calculate actual indicators for swing score
                    sma10 = sum(closes[-10:]) / len(closes[-10:]) if len(closes) >= 10 else current_price
                    sma21 = sum(closes[-21:]) / len(closes[-21:]) if len(closes) >= 21 else current_price
                    sma50 = sum(closes[-50:]) / len(closes[-50:]) if len(closes) >= 50 else current_price

                    change   = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2  else 0.0
                    perf_w   = ((closes[-1] - closes[-5]) / closes[-5] * 100) if len(closes) >= 5  else ((closes[-1] - closes[0]) / closes[0] * 100)
                    perf_1m  = ((closes[-1] - closes[-21]) / closes[-21] * 100) if len(closes) >= 21 else ((closes[-1] - closes[0]) / closes[0] * 100)
                    perf_3m  = ((closes[-1] - closes[-63]) / closes[-63] * 100) if len(closes) >= 63 else ((closes[-1] - closes[0]) / closes[0] * 100)

                    # Bug #3 fix — use module-level _calculate_rsi() instead of a nested function
                    # Bug #7 note — key is 'RSI' (uppercase) to match compute_swing_score() lookup
                    rsi = _calculate_rsi(closes)

                    # Bug #8 note — 'relative_volume' key matches the lookup in compute_swing_score()
                    stock_dict = {
                        "ticker":             ticker,
                        "clean_ticker":       ticker.replace(".NS", "").replace(".BO", ""),
                        "close":              current_price,
                        "SMA10":              sma10,
                        "SMA21":              sma21,
                        "SMA50":              sma50,
                        "price_52_week_high": max(highs) if highs else current_price,
                        "price_52_week_low":  min(lows)  if lows  else current_price,
                        "average_volume":     avg_vol_20d,
                        "relative_volume":    rvol_ratio,   # matches compute_swing_score() key
                        "Recommend.All":      0.5,
                        "sector":             sector,
                        "Perf.W":             perf_w,
                        "Perf.1M":            perf_1m,
                        "Perf.3M":            perf_3m,
                        "change":             change,
                        "RSI":                rsi,           # uppercase — matches compute_swing_score() key
                    }

                    swing_res   = compute_swing_score(stock_dict)
                    swing_score = swing_res.get("swingscore", 0) if isinstance(swing_res, dict) else 0
                    pattern_res = classify_technical_pattern(history)
                    pattern_name = "None"
                    if isinstance(pattern_res, dict):
                        pattern_name = pattern_res.get("pattern", "None")
                    elif isinstance(pattern_res, str):
                        pattern_name = pattern_res

                    phase = classify_momentum_phase(days_since, current_vs_issue_pct, current_vs_listing_pct)

                    # Write to cache
                    conn2 = sqlite3.connect('scan_history.db')
                    c2 = conn2.cursor()
                    c2.execute('''
                        INSERT OR REPLACE INTO ipo_metrics_cache (
                            ticker, company_name, listing_date, exchange, sector, issue_price,
                            listing_gain_pct, current_vs_issue_pct, current_vs_listing_pct, days_since_listing,
                            rvol_ratio, above_listing_high, drawdown_from_ath, swing_score, pattern_name,
                            momentum_phase, current_price, volume, change_pct, day_low, day_high,
                            is_blue_bar, is_green_bar, is_orange_bar, cached_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ''', (
                        ticker, company_name, listing_date, exchange, sector, issue_price,
                        round(listing_gain_pct, 2), round(current_vs_issue_pct, 2), round(current_vs_listing_pct, 2), days_since,
                        round(rvol_ratio, 2), above_listing_high, round(drawdown_from_ath, 2), swing_score, pattern_name,
                        phase, current_price, current_vol, round(change, 2), round(current_low, 2), round(current_high, 2),
                        is_blue, is_green, is_orange
                    ))
                    conn2.commit()
                    conn2.close()
                except Exception as e:
                    print(f"Error computing IPO metrics for {ticker}: {e}")

            # Run in parallel
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=8) as executor:
                executor.map(_update_single, listings)

            print("IPO metrics cache refreshed successfully.")
        except Exception as e:
            print(f"Error in IPO metrics refresh: {e}")
            raise e
        finally:
            if conn:
                conn.close()

    @staticmethod
    def _parse_volume_param(val_str):
        """Parse a volume string like '100k', '1m', '500' into a float.
        Returns None if the string is empty, 'all', or unparseable."""
        if not val_str or val_str.lower() == 'all':
            return None
        try:
            s = val_str.lower().strip()
            multiplier = 1
            if s.endswith('k'):
                multiplier = 1_000
                s = s[:-1]
            elif s.endswith('m'):
                multiplier = 1_000_000
                s = s[:-1]
            return float(s) * multiplier
        except ValueError:
            return None


# Singleton instance
ipo_service = IPOService()