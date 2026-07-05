"""
Fundamental Analysis Module for Momentum Confidence Score™
Implements fundamental analysis scoring (25 points)
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class FundamentalAnalyzer:
    """
    Analyzes fundamental metrics for company quality.
    Maximum score: 25 points
    """

    def __init__(self):
        """Initialize the fundamental analyzer."""
        pass

    def analyze(self, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze fundamental metrics and return score.

        Args:
            stock_data: Dictionary containing stock fundamental data

        Returns:
            Dictionary with score (0-25) and details about contributing factors
        """
        score = 0
        details = {
            'criteria_met': [],
            'criteria_not_met': [],
            'points_breakdown': {}
        }

        try:
            # 1. Revenue Growth (+4 points)
            revenue_growth = stock_data.get('revenue_growth_yoy', 0)  # YoY growth percentage
            if revenue_growth >= 20:
                score += 4
                details['criteria_met'].append(f'Strong Revenue Growth ({revenue_growth:.1f}%)')
                details['points_breakdown']['revenue_growth'] = 4
            elif revenue_growth >= 10:
                score += 3
                details['criteria_met'].append(f'Good Revenue Growth ({revenue_growth:.1f}%)')
                details['points_breakdown']['revenue_growth'] = 3
            elif revenue_growth >= 0:
                score += 2
                details['criteria_met'].append(f'Positive Revenue Growth ({revenue_growth:.1f}%)')
                details['points_breakdown']['revenue_growth'] = 2
            else:
                details['criteria_not_met'].append(f'Negative Revenue Growth ({revenue_growth:.1f}%)')
                details['points_breakdown']['revenue_growth'] = 0

            # 2. Profit Growth (+4 points)
            profit_growth = stock_data.get('profit_growth_yoy', 0)  # Net profit YoY growth
            if profit_growth >= 25:
                score += 4
                details['criteria_met'].append(f'Strong Profit Growth ({profit_growth:.1f}%)')
                details['points_breakdown']['profit_growth'] = 4
            elif profit_growth >= 15:
                score += 3
                details['criteria_met'].append(f'Good Profit Growth ({profit_growth:.1f}%)')
                details['points_breakdown']['profit_growth'] = 3
            elif profit_growth >= 0:
                score += 2
                details['criteria_met'].append(f'Positive Profit Growth ({profit_growth:.1f}%)')
                details['points_breakdown']['profit_growth'] = 2
            else:
                details['criteria_not_met'].append(f'Negative Profit Growth ({profit_growth:.1f}%)')
                details['points_breakdown']['profit_growth'] = 0

            # 3. ROCE > 20% (+4 points)
            roce = stock_data.get('roce', 0)  # Return on Capital Employed
            if roce >= 25:
                score += 4
                details['criteria_met'].append(f'Excellent ROCE ({roce:.1f}%)')
                details['points_breakdown']['roce'] = 4
            elif roce >= 20:
                score += 3
                details['criteria_met'].append(f'Good ROCE ({roce:.1f}%)')
                details['points_breakdown']['roce'] = 3
            elif roce >= 15:
                score += 2
                details['criteria_met'].append(f'Moderate ROCE ({roce:.1f}%)')
                details['points_breakdown']['roce'] = 2
            elif roce >= 10:
                score += 1
                details['criteria_met'].append(f'Low ROCE ({roce:.1f}%)')
                details['points_breakdown']['roce'] = 1
            else:
                details['criteria_not_met'].append(f'Poor ROCE ({roce:.1f}%)')
                details['points_breakdown']['roce'] = 0

            # 4. ROE > 18% (+3 points)
            roe = stock_data.get('roe', 0)  # Return on Equity
            if roe >= 22:
                score += 3
                details['criteria_met'].append(f'Excellent ROE ({roe:.1f}%)')
                details['points_breakdown']['roe'] = 3
            elif roe >= 18:
                score += 2
                details['criteria_met'].append(f'Good ROE ({roe:.1f}%)')
                details['points_breakdown']['roe'] = 2
            elif roe >= 15:
                score += 1
                details['criteria_met'].append(f'Moderate ROE ({roe:.1f}%)')
                details['points_breakdown']['roe'] = 1
            else:
                details['criteria_not_met'].append(f'Low ROE ({roe:.1f}%)')
                details['points_breakdown']['roe'] = 0

            # 5. Debt < 0.3 (+3 points)
            debt_to_equity = stock_data.get('debt_to_equity', 1)  # Lower is better
            if debt_to_equity <= 0.1:
                score += 3
                details['criteria_met'].append(f'Very Low Debt (D/E: {debt_to_equity:.2f})')
                details['points_breakdown']['debt_low'] = 3
            elif debt_to_equity <= 0.3:
                score += 2
                details['criteria_met'].append(f'Low Debt (D/E: {debt_to_equity:.2f})')
                details['points_breakdown']['debt_low'] = 2
            elif debt_to_equity <= 0.5:
                score += 1
                details['criteria_met'].append(f'Moderate Debt (D/E: {debt_to_equity:.2f})')
                details['points_breakdown']['debt_low'] = 1
            else:
                details['criteria_not_met'].append(f'High Debt (D/E: {debt_to_equity:.2f})')
                details['points_breakdown']['debt_low'] = 0

            # 6. Positive Cash Flow (+3 points)
            operating_cash_flow = stock_data.get('operating_cash_flow', 0)
            if operating_cash_flow > 0:
                score += 3
                details['criteria_met'].append('Positive Operating Cash Flow')
                details['points_breakdown']['positive_cash_flow'] = 3
            else:
                details['criteria_not_met'].append('Negative or Zero Operating Cash Flow')
                details['points_breakdown']['positive_cash_flow'] = 0

            # 7. High Promoter Holding (+2 points)
            promoter_holding = stock_data.get('promoter_holding_pct', 0)  # Percentage
            if promoter_holding >= 60:
                score += 2
                details['criteria_met'].append(f'High Promoter Holding ({promoter_holding:.1f}%)')
                details['points_breakdown']['promoter_holding'] = 2
            elif promoter_holding >= 40:
                score += 1
                details['criteria_met'].append(f'Moderate Promoter Holding ({promoter_holding:.1f}%)')
                details['points_breakdown']['promoter_holding'] = 1
            else:
                details['criteria_not_met'].append(f'Low Promoter Holding ({promoter_holding:.1f}%)')
                details['points_breakdown']['promoter_holding'] = 0

            # 8. No Pledge (+2 points)
            promoter_pledge = stock_data.get('promoter_pledged_pct', 100)  # Percentage of holding pledged
            if promoter_pledge == 0:
                score += 2
                details['criteria_met'].append('No Promoter Shares Pledged')
                details['points_breakdown']['no_pledge'] = 2
            elif promoter_pledge <= 5:
                score += 1
                details['criteria_met'].append(f'Low Promoter Pledge ({promoter_pledge:.1f}%)')
                details['points_breakdown']['no_pledge'] = 1
            else:
                details['criteria_not_met'].append(f'High Promoter Pledge ({promoter_pledge:.1f}%)')
                details['points_breakdown']['no_pledge'] = 0

            # Ensure score doesn't exceed maximum
            score = min(score, 25)

            details['total_score'] = score
            details['max_score'] = 25

            logger.debug(f"Fundamental analysis score: {score}/25")

            return {
                'score': score,
                'max_score': 25,
                'details': details
            }

        except Exception as e:
            logger.error(f"Error in fundamental analysis: {e}")
            return {
                'score': 0,
                'max_score': 25,
                'details': {
                    'error': str(e),
                    'criteria_met': [],
                    'criteria_not_met': ['Error in analysis'],
                    'points_breakdown': {}
                }
            }