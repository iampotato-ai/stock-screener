"""
Momentum Analysis Module for Momentum Confidence Score™
Implements momentum analysis scoring (20 points)
"""
import logging
from typing import Dict, Any

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

            # Ensure score doesn't exceed maximum
            score = min(score, 20)

            details['total_score'] = score
            details['max_score'] = 20

            logger.debug(f"Momentum analysis score: {score}/20")

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