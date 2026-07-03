"""
Risk & Liquidity Analysis Module for Momentum Confidence Score™
Implements risk and liquidity analysis scoring (10 points)
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class RiskAnalyzer:
    """
    Analyzes risk and liquidity factors.
    Maximum score: 10 points
    """

    def __init__(self):
        """Initialize the risk analyzer."""
        pass

    def analyze(self, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze risk and liquidity metrics and return score.

        Args:
            stock_data: Dictionary containing stock risk and liquidity data

        Returns:
            Dictionary with score (0-10) and details about contributing factors
        """
        score = 0
        details = {
            'criteria_met': [],
            'criteria_not_met': [],
            'points_breakdown': {}
        }

        try:
            # 1. High Liquidity (+4 points)
            # Based on average daily volume
            avg_volume = stock_data.get('avg_daily_volume', 0)  # Shares per day
            if avg_volume >= 2000000:  # 2M+ shares daily
                score += 4
                details['criteria_met'].append(f'Very High Liquidity ({avg_volume:,.0f} shares/day)')
                details['points_breakdown']['high_liquidity'] = 4
            elif avg_volume >= 1000000:  # 1M+ shares daily
                score += 3
                details['criteria_met'].append(f'High Liquidity ({avg_volume:,.0f} shares/day)')
                details['points_breakdown']['high_liquidity'] = 3
            elif avg_volume >= 500000:  # 500K+ shares daily
                score += 2
                details['criteria_met'].append(f'Moderate Liquidity ({avg_volume:,.0f} shares/day)')
                details['points_breakdown']['high_liquidity'] = 2
            elif avg_volume >= 100000:  # 100K+ shares daily
                score += 1
                details['criteria_met'].append(f'Low Liquidity ({avg_volume:,.0f} shares/day)')
                details['points_breakdown']['high_liquidity'] = 1
            else:
                details['criteria_not_met'].append(f'Very Low Liquidity ({avg_volume:,.0f} shares/day)')
                details['points_breakdown']['high_liquidity'] = 0

            # 2. Healthy Volume (+2 points)
            # Today's volume vs average volume
            volume_ratio = stock_data.get('volume_ratio', 1)  # Today's volume / avg volume
            if volume_ratio >= 2.0:
                score += 2
                details['criteria_met'].append(f'Very High Volume ({volume_ratio:.1f}x average)')
                details['points_breakdown']['healthy_volume'] = 2
            elif volume_ratio >= 1.5:
                score += 1
                details['criteria_met'].append(f'Above Average Volume ({volume_ratio:.1f}x average)')
                details['points_breakdown']['healthy_volume'] = 1
            else:
                details['criteria_not_met'].append(f'Below Average Volume ({volume_ratio:.1f}x average)')
                details['points_breakdown']['healthy_volume'] = 0

            # 3. Low Spread (+2 points)
            # Bid-ask spread as percentage of price
            bid_ask_spread_pct = stock_data.get('bid_ask_spread_pct', 1.0)  # Percentage
            if bid_ask_spread_pct <= 0.05:  # Very tight spread
                score += 2
                details['criteria_met'].append(f'Very Low Spread ({bid_ask_spread_pct:.2f}%)')
                details['points_breakdown']['low_spread'] = 2
            elif bid_ask_spread_pct <= 0.15:  # Tight spread
                score += 1
                details['criteria_met'].append(f'Low Spread ({bid_ask_spread_pct:.2f}%)')
                details['points_breakdown']['low_spread'] = 1
            else:
                details['criteria_not_met'].append(f'Wide Spread ({bid_ask_spread_pct:.2f}%)')
                details['points_breakdown']['low_spread'] = 0

            # 4. Low Operator Risk (+2 points)
            # Qualitative assessment of operator/promoter risk
            operator_risk = stock_data.get('operator_risk', 'medium')  # low, medium, high
            if operator_risk == 'low':
                score += 2
                details['criteria_met'].append('Low Operator/Risk Promoter')
                details['points_breakdown']['low_operator_risk'] = 2
            elif operator_risk == 'medium':
                score += 1
                details['criteria_met'].append('Moderate Operator/Risk Promoter')
                details['points_breakdown']['low_operator_risk'] = 1
            else:  # high
                details['criteria_not_met'].append('High Operator/Risk Promoter')
                details['points_breakdown']['low_operator_risk'] = 0

            # Ensure score doesn't exceed maximum
            score = min(score, 10)

            details['total_score'] = score
            details['max_score'] = 10

            logger.debug(f"Risk & liquidity analysis score: {score}/10")

            return {
                'score': score,
                'max_score': 10,
                'details': details
            }

        except Exception as e:
            logger.error(f"Error in risk analysis: {e}")
            return {
                'score': 0,
                'max_score': 10,
                'details': {
                    'error': str(e),
                    'criteria_met': [],
                    'criteria_not_met': ['Error in analysis'],
                    'points_breakdown': {}
                }
            }