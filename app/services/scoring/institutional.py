"""
Institutional Analysis Module for Momentum Confidence Score™
Implements institutional confidence scoring (15 points)
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class InstitutionalAnalyzer:
    """
    Analyzes institutional activity and confidence signals.
    Maximum score: 15 points
    """

    def __init__(self):
        """Initialize the institutional analyzer."""
        pass

    def analyze(self, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze institutional metrics and return score.

        Args:
            stock_data: Dictionary containing stock institutional data

        Returns:
            Dictionary with score (0-15) and details about contributing factors
        """
        score = 0
        details = {
            'criteria_met': [],
            'criteria_not_met': [],
            'points_breakdown': {}
        }

        try:
            # 1. Mutual Fund Increased Holdings (+5 points)
            mf_holding_change_pct = stock_data.get('mf_holding_change_pct', 0)  # % change in MF holdings
            if mf_holding_change_pct >= 10:
                score += 5
                details['criteria_met'].append(f'Significant MF Buying (+{mf_holding_change_pct:.1f}%)')
                details['points_breakdown']['mf_increased'] = 5
            elif mf_holding_change_pct >= 5:
                score += 4
                details['criteria_met'].append(f'Moderate MF Buying (+{mf_holding_change_pct:.1f}%)')
                details['points_breakdown']['mf_increased'] = 4
            elif mf_holding_change_pct >= 0:
                score += 2
                details['criteria_met'].append(f'MF Holding Stable/Increased (+{mf_holding_change_pct:.1f}%)')
                details['points_breakdown']['mf_increased'] = 2
            else:
                # Outflow
                if mf_holding_change_pct >= -5:
                    score += 1
                    details['criteria_met'].append(f'Small MF Outflow ({mf_holding_change_pct:.1f}%)')
                    details['points_breakdown']['mf_increased'] = 1
                else:
                    details['criteria_not_met'].append(f'Significant MF Selling ({mf_holding_change_pct:.1f}%)')
                    details['points_breakdown']['mf_increased'] = 0

            # 2. FII Buying (+4 points)
            fii_net_buy_cr = stock_data.get('fii_net_buy_cr', 0)  # FII net buying in crores
            fii_holding_pct = stock_data.get('fii_holding_pct', 0)  # FII holding percentage
            if fii_net_buy_cr > 100 or fii_holding_pct > 25:
                score += 4
                details['criteria_met'].append(f'Strong FII Buying (₹{fii_net_buy_cr:.0f}Cr net)')
                details['points_breakdown']['fii_buying'] = 4
            elif fii_net_buy_cr > 50 or fii_holding_pct > 20:
                score += 3
                details['criteria_met'].append(f'Moderate FII Buying (₹{fii_net_buy_cr:.0f}Cr net)')
                details['points_breakdown']['fii_buying'] = 3
            elif fii_net_buy_cr > 10 or fii_holding_pct > 15:
                score += 2
                details['criteria_met'].append(f'Some FII Buying (₹{fii_net_buy_cr:.0f}Cr net)')
                details['points_breakdown']['fii_buying'] = 2
            elif fii_net_buy_cr > 0 or fii_holding_pct > 10:
                score += 1
                details['criteria_met'].append(f'Minimal FII Presence (₹{fii_net_buy_cr:.0f}Cr net)')
                details['points_breakdown']['fii_buying'] = 1
            else:
                details['criteria_not_met'].append(f'FII Selling or Negligible (₹{fii_net_buy_cr:.0f}Cr net)')
                details['points_breakdown']['fii_buying'] = 0

            # 3. Promoter Buying (+3 points)
            promoter_buy_qty = stock_data.get('promoter_buy_qty', 0)  # Number of shares bought
            promoter_holding_change_pct = stock_data.get('promoter_holding_change_pct', 0)  # % change
            if promoter_buy_qty > 100000 or promoter_holding_change_pct > 2:
                score += 3
                details['criteria_met'].append(f'Promoter Buying Activity Detected')
                details['points_breakdown']['promoter_buying'] = 3
            elif promoter_buy_qty > 10000 or promoter_holding_change_pct > 0:
                score += 2
                details['criteria_met'].append(f'Some Promoter Buying')
                details['points_breakdown']['promoter_buying'] = 2
            elif promoter_holding_change_pct == 0:
                score += 1  # Holding steady is neutral-positive
                details['criteria_met'].append(f'Promoter Holding Steady')
                details['points_breakdown']['promoter_buying'] = 1
            else:
                # Promoter selling
                if promoter_holding_change_pct > -2:
                    score += 0  # Neutral
                    details['criteria_met'].append(f'Minor Promoter Selling ({promoter_holding_change_pct:.1f}%)')
                    details['points_breakdown']['promoter_buying'] = 0
                else:
                    details['criteria_not_met'].append(f'Promoter Selling ({promoter_holding_change_pct:.1f}%)')
                    details['points_breakdown']['promoter_buying'] = 0

            # 4. Positive Block Deals (+3 points)
            block_deal_count = stock_data.get('block_deal_count', 0)
            block_deal_buy_ratio = stock_data.get('block_deal_buy_ratio', 0.5)  # Ratio of buy vs sell
            if block_deal_count >= 3 and block_deal_buy_ratio >= 0.7:
                score += 3
                details['criteria_met'].append(f'Strong Block Deal Buying ({block_deal_count} deals, {block_deal_buy_ratio:.0%} buy)')
                details['points_breakdown']['positive_block_deals'] = 3
            elif block_deal_count >= 2 and block_deal_buy_ratio >= 0.6:
                score += 2
                details['criteria_met'].append(f'Moderate Block Deal Buying ({block_deal_count} deals, {block_deal_buy_ratio:.0%} buy)')
                details['points_breakdown']['positive_block_deals'] = 2
            elif block_deal_count >= 1 and block_deal_buy_ratio >= 0.5:
                score += 1
                details['criteria_met'].append(f'Some Block Deal Activity ({block_deal_count} deals)')
                details['points_breakdown']['positive_block_deals'] = 1
            else:
                details['criteria_not_met'].append(f'No Significant Block Deal Buying ({block_deal_count} deals)')
                details['points_breakdown']['positive_block_deals'] = 0

            # Ensure score doesn't exceed maximum
            score = min(score, 15)

            details['total_score'] = score
            details['max_score'] = 15

            logger.debug(f"Institutional analysis score: {score}/15")

            return {
                'score': score,
                'max_score': 15,
                'details': details
            }

        except Exception as e:
            logger.error(f"Error in institutional analysis: {e}")
            return {
                'score': 0,
                'max_score': 15,
                'details': {
                    'error': str(e),
                    'criteria_met': [],
                    'criteria_not_met': ['Error in analysis'],
                    'points_breakdown': {}
                }
            }