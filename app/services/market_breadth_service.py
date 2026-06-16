"""
Market breadth service for managing breadth data and calculations.
"""
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.database import get_db


class MarketBreadthService:
    """Service for market breadth-related operations."""

    def save_breadth_snapshot(self, advances: int, declines: int, unchanged: int,
                            pct_sma21: float, pct_sma50: float, pct_52high: float,
                            avg_recommend: float, regime_score: int, regime_band: str) -> None:
        """Save a market breadth snapshot to the database."""
        conn = get_db()
        try:
            c = conn.cursor()
            today, now_time = datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%H:%M')
            c.execute(
                """
                INSERT OR REPLACE INTO breadth_history
                (date, time, advances, declines, unchanged, pct_sma21, pct_sma50,
                 pct_52high, avg_recommend, regime_score, regime_band)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (today, now_time, advances, declines, unchanged,
                 pct_sma21, pct_sma50, pct_52high, avg_recommend, regime_score, regime_band)
            )
            conn.commit()
        finally:
            pass

    def get_breadth_history(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Get market breadth history with optional limit."""
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute(
                """
                SELECT date, time, advances, declines, unchanged,
                       pct_sma21, pct_sma50, pct_52high,
                       regime_score, regime_band, avg_recommend
                FROM breadth_history
                ORDER BY date DESC, time DESC
                LIMIT ?
                """,
                (limit,)
            )
            rows = c.fetchall()
            cols = ['date', 'time', 'advances', 'declines', 'unchanged',
                   'pct_sma21', 'pct_sma50', 'pct_52high',
                   'regime_score', 'regime_band', 'avg_recommend']
            return [dict(zip(cols, row)) for row in rows]
        finally:
            pass

    def get_latest_breadth_snapshot(self) -> Optional[Dict[str, Any]]:
        """Get the most recent market breadth snapshot."""
        history = self.get_breadth_history(limit=1)
        return history[0] if history else None

    def calculate_sector_scores(self, universe_stocks: List[Dict[str, Any]]) -> tuple:
        """
        Calculate sector scores for a universe of stocks.
        This replicates the calculate_backend_sector_scores function from app.py.
        Returns: (sector_scores, uni_median_w, uni_median_m, uni_median_3m)
        """
        import statistics

        # Group stocks by sector
        sectors_map = {}
        for s in universe_stocks:
            sec = s.get("sector")
            if not sec:
                continue
            if sec not in sectors_map:
                sectors_map[sec] = []
            sectors_map[sec].append(s)

        # Get all valid perf_w, perf_m, perf_3m
        universe_w = [s["perf_w"] for s in universe_stocks if s.get("perf_w") is not None]
        universe_m = [s["perf_m"] for s in universe_stocks if s.get("perf_m") is not None]
        universe_3m = [s["perf_3m"] for s in universe_stocks if s.get("perf_3m") is not None]

        uni_median_w = statistics.median(universe_w) if universe_w else 0.0
        uni_median_m = statistics.median(universe_m) if universe_m else 0.0
        uni_median_3m = statistics.median(universe_3m) if universe_3m else 0.0

        sector_scores = {}
        for sector, sector_stocks in sectors_map.items():
            count = len(sector_stocks)

            # 1. Relative Strength vs Universe/Market (40 points)
            w_vals = [s["perf_w"] for s in sector_stocks if s.get("perf_w") is not None]
            m_vals = [s["perf_m"] for s in sector_stocks if s.get("perf_m") is not None]
            m3_vals = [s["perf_3m"] for s in sector_stocks if s.get("perf_3m") is not None]

            avg_sector_w = statistics.median(w_vals) if w_vals else 0.0
            avg_sector_m = statistics.median(m_vals) if m_vals else 0.0
            avg_sector_3m = statistics.median(m3_vals) if m3_vals else 0.0

            diff_w = avg_sector_w - uni_median_w
            diff_m = avg_sector_m - uni_median_m
            diff_3m = avg_sector_3m - uni_median_3m

            combined_rs = (diff_m * 1.5) + (diff_3m * 1.0)
            rs_score = max(0.0, min(40.0, 20.0 + (combined_rs * 2.0)))

            # 2. Breadth: Advances vs Declines (25 points)
            advances = sum(1 for s in sector_stocks if s.get("change", 0.0) > 0.0)
            breadth_pct = (advances / count) if count > 0 else 0.5
            breadth_score = breadth_pct * 25.0

            # 3. Trend: close above SMA21 and SMA50 (20 points)
            in_trend = sum(1 for s in sector_stocks if s.get("close", 0.0) > s.get("SMA21", 0.0) and s.get("close", 0.0) > s.get("SMA50", 0.0))
            trend_pct = (in_trend / count) if count > 0 else 0.5
            trend_score = trend_pct * 20.0

            # 4. Leadership: stocks near 52W high (15 points)
            leaders = sum(1 for s in sector_stocks if s.get("price52weekhigh", 0.0) > 0.0 and s.get("close", 0.0) >= (s.get("price52weekhigh", 0.0) * 0.96))
            leadership_pct = (leaders / count) if count > 0 else 0.2
            leadership_score = leadership_pct * 15.0

            total_score = round(rs_score + breadth_score + trend_score + leadership_score)

            # Quadrant
            if diff_m > 0 and diff_w > 0:
                quadrant = 'Leading'
            elif diff_m <= 0 and diff_w > 0:
                quadrant = 'Improving'
            elif diff_m > 0 and diff_w <= 0:
                quadrant = 'Weakening'
            else:
                quadrant = 'Lagging'

            sector_scores[sector] = {
                "score": total_score,
                "advances": advances,
                "declines": count - advances,
                "count": count,
                "avg1W": avg_sector_w,
                "avg1M": avg_sector_m,
                "avg3M": avg_sector_3m,
                "delta1W": diff_w,
                "delta1M": diff_m,
                "quadrant": quadrant
            }

        return sector_scores, uni_median_w, uni_median_m, uni_median_3m


# Singleton instance
market_breadth_service = MarketBreadthService()