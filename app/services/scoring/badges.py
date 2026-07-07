"""
Badges Module for Momentum Confidence Score™
Implements badge awarding system
"""
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class BadgeAwarder:
    """
    Awards achievement badges based on score and specific criteria.
    """

    def __init__(self):
        """Initialize the badge awarder."""
        # Define badge criteria
        self.badge_criteria = {
            'elite_momentum': {
                'name': '🏆 Elite Momentum',
                'description': 'Top 1% momentum score',
                'condition': lambda data: data.get('total_score', 0) >= 95
            },
            'fresh_breakout': {
                'name': '🚀 Fresh Breakout',
                'description': 'Recent price breakout with volume',
                'condition': lambda data: data.get('momentum_details', {}).get('points_breakdown', {}).get('fresh_breakout', 0) >= 2
            },
            'smart_money_buying': {
                'name': '💰 Smart Money Buying',
                'description': 'Significant institutional buying',
                'condition': lambda data: (
                    data.get('institutional_details', {}).get('points_breakdown', {}).get('mf_increased', 0) >= 4 or
                    data.get('institutional_details', {}).get('points_breakdown', {}).get('fii_buying', 0) >= 3
                )
            },
            'earnings_winner': {
                'name': '📈 Earnings Winner',
                'description': 'Strong earnings growth',
                'condition': lambda data: data.get('fundamental_details', {}).get('points_breakdown', {}).get('profit_growth', 0) >= 4
            },
            'high_relative_strength': {
                'name': '🔥 High Relative Strength',
                'description': 'RS rating above 80',
                'condition': lambda data: data.get('momentum_details', {}).get('points_breakdown', {}).get('relative_strength', 0) >= 5
            },
            'debt_free': {
                'name': '⭐ Debt Free',
                'description': 'Very low debt levels',
                'condition': lambda data: data.get('fundamental_details', {}).get('points_breakdown', {}).get('debt_low', 0) >= 3
            },
            'high_quality': {
                'name': '💎 High Quality',
                'description': 'Strong fundamentals and low risk',
                'condition': lambda data: (
                    data.get('pillar_scores', {}).get('fundamental', 0) >= 20 and
                    data.get('pillar_scores', {}).get('risk_liquidity', 0) >= 8
                )
            },
            'market_leader': {
                'name': '👑 Market Leader',
                'description': 'Leading in sector with strong institutional backing',
                'condition': lambda data: (
                    data.get('pillar_scores', {}).get('institutional', 0) >= 12 and
                    data.get('total_score', 0) >= 85
                )
            },
            # ── Swing-trader badges ─────────────────────────────────────────────
            'high_vol_breakout': {
                'name': '⚡ High-Vol Breakout',
                'description': 'Fresh 52W-high breakout with RVOL ≥ 2×',
                'condition': lambda data: (
                    data.get('momentum_details', {}).get('points_breakdown', {}).get('fresh_breakout', 0) >= 2 and
                    data.get('momentum_details', {}).get('points_breakdown', {}).get('volume_breakout', 0) >= 3
                )
            },
            'trend_aligned': {
                'name': '📈 Trend Aligned',
                'description': 'Price riding above EMA20 > EMA50 > EMA200',
                'condition': lambda data: (
                    data.get('technical_details', {}).get('points_breakdown', {}).get('above_200_ema', 0) >= 1 and
                    data.get('technical_details', {}).get('points_breakdown', {}).get('above_50_ema', 0) >= 1 and
                    data.get('technical_details', {}).get('points_breakdown', {}).get('golden_cross', 0) >= 1
                )
            },
            'velocity_accelerating': {
                'name': '🔥 Velocity Accelerating',
                'description': 'ADX > 25 with positive momentum acceleration',
                'condition': lambda data: (
                    data.get('technical_details', {}).get('points_breakdown', {}).get('adx_gt_25', 0) >= 1 and
                    data.get('momentum_details', {}).get('points_breakdown', {}).get('momentum_acceleration', 0) >= 1
                )
            }
        }

    def award_badges(self, score_data: Dict[str, Any]) -> List[str]:
        """
        Award badges based on score data.

        Args:
            score_data: Dictionary containing complete score analysis

        Returns:
            List of badge names awarded
        """
        awarded_badges = []

        try:
            for badge_key, badge_info in self.badge_criteria.items():
                try:
                    if badge_info['condition'](score_data):
                        awarded_badges.append(badge_info['name'])
                        logger.debug(f"Awarded badge: {badge_info['name']}")
                except Exception as e:
                    logger.warning(f"Error checking condition for badge {badge_key}: {e}")
                    continue

            logger.info(f"Awarded {len(awarded_badges)} badges: {awarded_badges}")
            return awarded_badges

        except Exception as e:
            logger.error(f"Error awarding badges: {e}")
            return []