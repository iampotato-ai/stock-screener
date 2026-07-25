"""
Momentum Analysis Module for Momentum Confidence Score™
Implements momentum analysis scoring (20 points), enriched with
quant-factor signals ported from HKUDS/Vibe-Trading (MIT License).
"""
import logging
from typing import Dict, Any, List

from app.services.scoring.quant_factors import score_quant_factors

logger = logging.getLogger(__name__)

class MomentumAnalyzer:
    """
    Analyzes momentum metrics for stock strength.
    Maximum score: 20 points
    """

    def __init__(self):
        """Initialize the momentum analyzer."""
        pass

    def analyze(self, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze momentum metrics and return score.

        Args:
            stock_data: Dictionary containing stock momentum data

        Returns:
            Dictionary with score (0-20) and details about contributing factors
        """
        score = 0
        details = {
            'criteria_met': [],
            'criteria_not_met': [],
            'points_breakdown': {}
        }

        try:
            # 1. Relative Strength (+6 points)
            # Using a scale where 0-100 represents percentile rank vs peers
            rs_rating = stock_data.get('relative_strength_rating', 50)  # 0-100 scale
            if rs_rating >= 90:
                score += 6
                details['criteria_met'].append(f'Excellent Relative Strength (RS: {rs_rating})')
                details['points_breakdown']['relative_strength'] = 6
            elif rs_rating >= 80:
                score += 5
                details['criteria_met'].append(f'Very Good Relative Strength (RS: {rs_rating})')
                details['points_breakdown']['relative_strength'] = 5
            elif rs_rating >= 70:
                score += 4
                details['criteria_met'].append(f'Good Relative Strength (RS: {rs_rating})')
                details['points_breakdown']['relative_strength'] = 4
            elif rs_rating >= 60:
                score += 3
                details['criteria_met'].append(f'Fair Relative Strength (RS: {rs_rating})')
                details['points_breakdown']['relative_strength'] = 3
            elif rs_rating >= 50:
                score += 2
                details['criteria_met'].append(f'Average Relative Strength (RS: {rs_rating})')
                details['points_breakdown']['relative_strength'] = 2
            else:
                score += 1  # Even low RS gets 1 point for having some strength
                details['criteria_met'].append(f'Low Relative Strength (RS: {rs_rating})')
                details['points_breakdown']['relative_strength'] = 1  # matches score += 1

            # 2. Volume Breakout (+4 points)
            # Volume ratio compared to average
            volume_ratio = stock_data.get('volume_ratio', 1)  # Current volume / average volume
            if volume_ratio >= 3.0:
                score += 4
                details['criteria_met'].append(f'Strong Volume Breakout ({volume_ratio:.1f}x avg)')
                details['points_breakdown']['volume_breakout'] = 4
            elif volume_ratio >= 2.0:
                score += 3
                details['criteria_met'].append(f'Moderate Volume Breakout ({volume_ratio:.1f}x avg)')
                details['points_breakdown']['volume_breakout'] = 3
            elif volume_ratio >= 1.5:
                score += 2
                details['criteria_met'].append(f'Some Volume Increase ({volume_ratio:.1f}x avg)')
                details['points_breakdown']['volume_breakout'] = 2
            elif volume_ratio >= 1.2:
                score += 1
                details['criteria_met'].append(f'Slight Volume Increase ({volume_ratio:.1f}x avg)')
                details['points_breakdown']['volume_breakout'] = 1
            else:
                details['criteria_not_met'].append(f'Below Average Volume ({volume_ratio:.1f}x avg)')
                details['points_breakdown']['volume_breakout'] = 0

            # 3. Near 52 Week High (+3 points)
            # Percentage of 52-week high (closer to 100 is better)
            pct_of_52w_high = stock_data.get('price_vs_52w_high_pct', 50)  # Percentage
            if pct_of_52w_high >= 95:
                score += 3
                details['criteria_met'].append(f'Near 52-Week High ({pct_of_52w_high:.1f}%)')
                details['points_breakdown']['near_52w_high'] = 3
            elif pct_of_52w_high >= 90:
                score += 2
                details['criteria_met'].append(f'Close to 52-Week High ({pct_of_52w_high:.1f}%)')
                details['points_breakdown']['near_52w_high'] = 2
            elif pct_of_52w_high >= 80:
                score += 1
                details['criteria_met'].append(f'Moderately Near 52-Week High ({pct_of_52w_high:.1f}%)')
                details['points_breakdown']['near_52w_high'] = 1
            else:
                details['criteria_not_met'].append(f'Far from 52-Week High ({pct_of_52w_high:.1f}%)')
                details['points_breakdown']['near_52w_high'] = 0

            # 4. VCP Pattern (+3 points)
            # Volatility Contraction Pattern
            has_vcp = stock_data.get('has_vcp_pattern', False)
            if has_vcp:
                score += 3
                details['criteria_met'].append('VCP Pattern Detected')
                details['points_breakdown']['vcp_pattern'] = 3
            else:
                details['criteria_not_met'].append('No VCP Pattern')
                details['points_breakdown']['vcp_pattern'] = 0

            # 5. Fresh Breakout (+2 points)
            # Price has recently broken above resistance
            is_breakout = stock_data.get('is_breakout', False)
            if is_breakout:
                score += 2
                details['criteria_met'].append('Fresh Breakout Detected')
                details['points_breakdown']['fresh_breakout'] = 2
            else:
                details['criteria_not_met'].append('No Fresh Breakout')
                details['points_breakdown']['fresh_breakout'] = 0

            # 6. Momentum Acceleration (+2 points)
            # Rate of change of momentum (positive acceleration)
            mom_acceleration = stock_data.get('momentum_acceleration', 0)  # Percentage
            if mom_acceleration >= 20:
                score += 2
                details['criteria_met'].append(f'Strong Momentum Acceleration ({mom_acceleration:.1f}%)')
                details['points_breakdown']['momentum_acceleration'] = 2
            elif mom_acceleration >= 10:
                score += 1
                details['criteria_met'].append(f'Moderate Momentum Acceleration ({mom_acceleration:.1f}%)')
                details['points_breakdown']['momentum_acceleration'] = 1
            else:
                details['criteria_not_met'].append(f'Low Momentum Acceleration ({mom_acceleration:.1f}%)')
                details['points_breakdown']['momentum_acceleration'] = 0

            # ── Quant Factor Bonus (0–4 points) ──────────────────────────
            # History is loaded from DailyBar if available; gracefully
            # degrades to single-period signals when DB has no history.
            close_history: List[float] = []
            volume_history: List[int] = []
            open_history: List[float] = []
            try:
                symbol   = stock_data.get('symbol', '')
                exchange = stock_data.get('exchange', 'NSE')
                if symbol:
                    close_history, volume_history, open_history = (
                        self._load_ohlcv_history(symbol, exchange)
                    )
            except Exception as hist_err:
                logger.debug("Could not load OHLCV history for quant factors: %s", hist_err)

            quant_result = score_quant_factors(
                stock_data,
                close_history=close_history or None,
                volume_history=volume_history or None,
                open_history=open_history or None,
            )
            quant_score = quant_result.get('score', 0.0)
            score += quant_score
            details['points_breakdown']['quant_factors'] = round(quant_score, 2)
            details['quant_signals'] = quant_result.get('signal_scores', {})
            if quant_score >= 2.0:
                details['criteria_met'].append(
                    f'Strong Quant Signals ({quant_result["factors_computed"]} factors, +{quant_score:.1f}pt)'
                )
            elif quant_score >= 1.0:
                details['criteria_met'].append(
                    f'Moderate Quant Signals (+{quant_score:.1f}pt)'
                )
            else:
                details['criteria_not_met'].append('Weak Quant Signals')

            # Ensure score doesn't exceed maximum
            score = min(score, 20)

            details['total_score'] = score
            details['max_score'] = 20

            logger.debug("Momentum analysis score: %.1f/20 (quant bonus: %.2f)", score, quant_score)

            return {
                'score': score,
                'max_score': 20,
                'details': details
            }

        except Exception as e:
            logger.error(f"Error in momentum analysis: {e}")
            return {
                'score': 0,
                'max_score': 20,
                'details': {
                    'error': str(e),
                    'criteria_met': [],
                    'criteria_not_met': ['Error in analysis'],
                    'points_breakdown': {}
                }
            }

    @staticmethod
    def _load_ohlcv_history(
        symbol: str, exchange: str, n_bars: int = 20
    ):
        """
        Load last N daily bars from DailyBar table.
        Returns (close_history, volume_history, open_history) lists.
        Falls back to ([], [], []) when DB is unavailable or has no data.
        Tries plain symbol first, then .NS / .BO suffixes.
        """
        try:
            from app.models import DailyBar
            from app.extensions import db

            candidates = [symbol, f"{symbol}.NS", f"{symbol}.BO"]
            bars = []
            for sym in candidates:
                bars = (
                    db.session.query(DailyBar)
                    .filter(DailyBar.symbol == sym)
                    .order_by(DailyBar.trade_date.desc())
                    .limit(n_bars)
                    .all()
                )
                if bars:
                    break

            if not bars:
                return [], [], []

            bars = list(reversed(bars))   # oldest first
            closes  = [float(b.close  or 0) for b in bars]
            volumes = [int(b.volume   or 0) for b in bars]
            opens   = [float(b.open   or 0) for b in bars]
            return closes, volumes, opens

        except Exception as db_err:
            logger.debug("OHLCV history load failed: %s", db_err)
            return [], [], []