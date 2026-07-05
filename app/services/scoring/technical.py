"""
Technical Analysis Module for Momentum Confidence Score™
Implements technical analysis scoring (30 points)
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class TechnicalAnalyzer:
    """
    Analyzes technical indicators for stock strength.
    Maximum score: 30 points
    """

    def __init__(self):
        """Initialize the technical analyzer."""
        pass

    def analyze(self, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze technical indicators and return score.

        Args:
            stock_data: Dictionary containing stock data including technical indicators

        Returns:
            Dictionary with score (0-30) and details about contributing factors
        """
        score = 0
        details = {
            'criteria_met': [],
            'criteria_not_met': [],
            'points_breakdown': {}
        }

        try:
            # 1. Price above 200 EMA (+5 points)
            if stock_data.get('price', 0) > stock_data.get('ema_200', 0):
                score += 5
                details['criteria_met'].append('Price above 200 EMA')
                details['points_breakdown']['above_200_ema'] = 5
            else:
                details['criteria_not_met'].append('Price below 200 EMA')
                details['points_breakdown']['above_200_ema'] = 0

            # 2. Price above 50 EMA (+3 points)
            if stock_data.get('price', 0) > stock_data.get('ema_50', 0):
                score += 3
                details['criteria_met'].append('Price above 50 EMA')
                details['points_breakdown']['above_50_ema'] = 3
            else:
                details['criteria_not_met'].append('Price below 50 EMA')
                details['points_breakdown']['above_50_ema'] = 0

            # 3. Golden Cross (50 EMA > 200 EMA) (+4 points)
            if stock_data.get('ema_50', 0) > stock_data.get('ema_200', 0):
                score += 4
                details['criteria_met'].append('Golden Cross (50 EMA > 200 EMA)')
                details['points_breakdown']['golden_cross'] = 4
            else:
                details['criteria_not_met'].append('No Golden Cross (50 EMA <= 200 EMA)')
                details['points_breakdown']['golden_cross'] = 0

            # 4. Near 52 Week High (+4 points)
            # Within 10% of 52-week high
            price_vs_52w_high = stock_data.get('price_vs_52w_high', 0)
            if price_vs_52w_high >= 0.90:  # Within 90%+ of 52-week high
                score += 4
                details['criteria_met'].append('Near 52 Week High (within 10%)')
                details['points_breakdown']['near_52w_high'] = 4
            elif price_vs_52w_high >= 0.80:  # Within 20% of 52-week high
                score += 2
                details['criteria_met'].append('Moderately near 52 Week High (within 20%)')
                details['points_breakdown']['near_52w_high'] = 2
            else:
                details['criteria_not_met'].append('Far from 52 Week High (<80% of high)')
                details['points_breakdown']['near_52w_high'] = 0

            # 5. Higher Highs Pattern (+4 points)
            if stock_data.get('higher_highs', False):
                score += 4
                details['criteria_met'].append('Higher Highs Pattern')
                details['points_breakdown']['higher_highs'] = 4
            else:
                details['criteria_not_met'].append('No Higher Highs Pattern')
                details['points_breakdown']['higher_highs'] = 0

            # 6. ADX > 25 (+3 points)
            adx = stock_data.get('adx', 0)
            if adx > 25:
                score += 3
                details['criteria_met'].append(f'ADX > 25 (ADX: {adx:.1f})')
                details['points_breakdown']['adx_gt_25'] = 3
            elif adx > 20:
                score += 1
                details['criteria_met'].append(f'ADX > 20 (ADX: {adx:.1f})')
                details['points_breakdown']['adx_gt_20'] = 1
            else:
                details['criteria_not_met'].append(f'ADX <= 20 (ADX: {adx:.1f})')
                details['points_breakdown']['adx_gt_25'] = 0

            # 7. Supertrend Buy Signal (+3 points)
            # Price above Supertrend and Supertrend direction is up (1)
            price = stock_data.get('price', 0)
            supertrend = stock_data.get('supertrend', 0)
            supertrend_direction = stock_data.get('supertrend_direction', -1)
            if price > supertrend and supertrend_direction == 1:
                score += 3
                details['criteria_met'].append('Supertrend Buy Signal')
                details['points_breakdown']['supertrend_buy'] = 3
            else:
                details['criteria_not_met'].append('No Supertrend Buy Signal')
                details['points_breakdown']['supertrend_buy'] = 0

            # 8. Healthy RSI (+2 points)
            # RSI between 40 and 80 (not overbought/oversold)
            rsi = stock_data.get('rsi', 50)
            if 40 <= rsi <= 80:
                score += 2
                details['criteria_met'].append(f'Healthy RSI (RSI: {rsi:.1f})')
                details['points_breakdown']['healthy_rsi'] = 2
            elif rsi > 80:
                # Overbought - still get 1 point for strength
                score += 1
                details['criteria_met'].append(f'RSI Overbought but strong (RSI: {rsi:.1f})')
                details['points_breakdown']['healthy_rsi'] = 1
            else:
                details['criteria_not_met'].append(f'RSI too low (RSI: {rsi:.1f})')
                details['points_breakdown']['healthy_rsi'] = 0

            # Trend Stability proxy (+2 points)
            # NOTE: ADX > 20 is used as a proxy for a trending (non-choppy) market.
            # This is a placeholder for true ATR-based volatility contraction scoring;
            # do not confuse with ATR magnitude. Real implementation should compare
            # current ATR against its own N-period average.
            adx = stock_data.get('adx', 0)
            if adx > 20:
                score += 2
                details['criteria_met'].append('Trending Market (ADX > 20 proxy for stability)')
                details['points_breakdown']['atr_stable'] = 2
            else:
                details['criteria_not_met'].append('Weak/Choppy Market (ADX <= 20)')
                details['points_breakdown']['atr_stable'] = 0

            # Ensure score doesn't exceed maximum
            score = min(score, 30)

            details['total_score'] = score
            details['max_score'] = 30

            logger.debug(f"Technical analysis score: {score}/30")

            return {
                'score': score,
                'max_score': 30,
                'details': details
            }

        except Exception as e:
            logger.error(f"Error in technical analysis: {e}")
            return {
                'score': 0,
                'max_score': 30,
                'details': {
                    'error': str(e),
                    'criteria_met': [],
                    'criteria_not_met': ['Error in analysis'],
                    'points_breakdown': {}
                }
            }