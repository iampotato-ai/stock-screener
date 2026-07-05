"""
Explanations Module for Momentum Confidence Score™
Generates human-readable explanations for scores
"""
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ExplanationGenerator:
    """
    Generates human-readable explanations for Momentum Confidence Scores.
    """

    def __init__(self):
        """Initialize the explanation generator."""
        pass

    def generate_explanation(self, score_data: Dict[str, Any]) -> str:
        """
        Generate a human-readable explanation for the score.

        Args:
            score_data: Dictionary containing complete score analysis

        Returns:
            Formatted explanation string
        """
        try:
            symbol = score_data.get('symbol', 'UNKNOWN')
            total_score = score_data.get('total_score', 0)

            # Get pillar scores and weighted scores
            pillar_scores = score_data.get('pillar_scores', {})
            weighted_scores = score_data.get('weighted_scores', {})
            badges = score_data.get('badges', [])

            # Start building explanation
            lines = []
            lines.append(f"{symbol}")
            lines.append("")
            lines.append(f"Momentum Confidence")
            lines.append(f"{'█' * min(int(total_score / 5), 20)}{'░' * (20 - min(int(total_score / 5), 20))} {total_score}/100")

            # Add rating based on score
            rating = self._get_score_rating(total_score)
            lines.append(f"{'★' * 5} {rating}")
            lines.append("")

            lines.append("Top Reasons")

            # Add top reasons from each pillar
            reasons_added = 0
            max_reasons = 6  # Limit to top 6 reasons

            # Technical reasons
            tech_reasons = self._get_top_technical_reasons(score_data)
            for reason in tech_reasons:
                if reasons_added >= max_reasons:
                    break
                lines.append(f"✓ {reason}")
                reasons_added += 1

            # Fundamental reasons
            fund_reasons = self._get_top_fundamental_reasons(score_data)
            for reason in fund_reasons:
                if reasons_added >= max_reasons:
                    break
                lines.append(f"✓ {reason}")
                reasons_added += 1

            # Momentum reasons
            mom_reasons = self._get_top_momentum_reasons(score_data)
            for reason in mom_reasons:
                if reasons_added >= max_reasons:
                    break
                lines.append(f"✓ {reason}")
                reasons_added += 1

            # Institutional reasons
            inst_reasons = self._get_top_institutional_reasons(score_data)
            for reason in inst_reasons:
                if reasons_added >= max_reasons:
                    break
                lines.append(f"✓ {reason}")
                reasons_added += 1

            # Risk/Liquidity reasons
            risk_reasons = self._get_top_risk_reasons(score_data)
            for reason in risk_reasons:
                if reasons_added >= max_reasons:
                    break
                lines.append(f"✓ {reason}")
                reasons_added += 1

            # Add badges if any
            if badges:
                lines.append("")
                lines.append("Badges")
                for badge in badges:
                    lines.append(f"{badge}")

            lines.append("")
            lines.append("[Analyze]")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            return f"{score_data.get('symbol', 'ERROR')}\n\nMomentum Confidence\n░░░░░░░░░░░░░░░░░░░░░░░ 0/100\n\n★★★★★ Error\n\nTop Reasons\n✓ Unable to generate explanation\n\n[Analyze]"

    def _get_score_rating(self, score: int) -> str:
        """Get text rating based on score."""
        if score >= 95:
            return "Elite Opportunity"
        elif score >= 90:
            return "Very Strong"
        elif score >= 80:
            return "Strong"
        elif score >= 70:
            return "Good"
        elif score >= 60:
            return "Average"
        else:
            return "Weak"

    def _get_top_technical_reasons(self, score_data: Dict[str, Any]) -> List[str]:
        """Extract top technical reasons."""
        reasons = []
        try:
            details = score_data.get('technical_details', {}).get('points_breakdown', {})

            # Map point breakdowns to readable reasons
            reason_map = {
                'above_200_ema': ('Price above 200 EMA', lambda pts: pts >= 5),
                'above_50_ema': ('Price above 50 EMA', lambda pts: pts >= 3),
                'golden_cross': ('Golden Cross', lambda pts: pts >= 4),
                'near_52w_high': ('Near 52 Week High', lambda pts: pts >= 4),
                'higher_highs': ('Higher Highs Pattern', lambda pts: pts >= 4),
                'adx_gt_25': ('ADX > 25', lambda pts: pts >= 3),
                'supertrend_buy': ('Supertrend Buy Signal', lambda pts: pts >= 3),
                'healthy_rsi': ('Healthy RSI', lambda pts: pts >= 2),
                'atr_stable': ('ATR Stable', lambda pts: pts >= 2)
            }

            for key, (reason_text, condition) in reason_map.items():
                points = details.get(key, 0)
                if condition(points):
                    reasons.append(reason_text)

            return reasons[:3]  # Return top 3
        except Exception as e:
            logger.warning(f"Error extracting technical reasons: {e}")
            return ["Technical analysis completed"]

    def _get_top_fundamental_reasons(self, score_data: Dict[str, Any]) -> List[str]:
        """Extract top fundamental reasons."""
        reasons = []
        try:
            details = score_data.get('fundamental_details', {}).get('points_breakdown', {})

            reason_map = {
                'revenue_growth': ('Strong Revenue Growth', lambda pts: pts >= 4),
                'profit_growth': ('Strong Profit Growth', lambda pts: pts >= 4),
                'roce': ('Excellent ROCE', lambda pts: pts >= 4),
                'roe': ('Good ROE', lambda pts: pts >= 2),
                'debt_low': ('Low Debt Levels', lambda pts: pts >= 3),
                'positive_cash_flow': ('Positive Cash Flow', lambda pts: pts >= 3),
                'promoter_holding': ('High Promoter Holding', lambda pts: pts >= 2),
                'no_pledge': ('No Promoter Pledge', lambda pts: pts >= 2)
            }

            for key, (reason_text, condition) in reason_map.items():
                points = details.get(key, 0)
                if condition(points):
                    reasons.append(reason_text)

            return reasons[:3]
        except Exception as e:
            logger.warning(f"Error extracting fundamental reasons: {e}")
            return ["Fundamental analysis completed"]

    def _get_top_momentum_reasons(self, score_data: Dict[str, Any]) -> List[str]:
        """Extract top momentum reasons."""
        reasons = []
        try:
            details = score_data.get('momentum_details', {}).get('points_breakdown', {})

            reason_map = {
                'relative_strength': ('High Relative Strength', lambda pts: pts >= 5),
                'volume_breakout': ('Volume Breakout', lambda pts: pts >= 4),
                'near_52w_high': ('Near 52-Week High', lambda pts: pts >= 3),
                'vcp_pattern': ('VCP Pattern Detected', lambda pts: pts >= 3),
                'fresh_breakout': ('Fresh Breakout Detected', lambda pts: pts >= 2),
                'momentum_acceleration': ('Momentum Acceleration', lambda pts: pts >= 2)
            }

            for key, (reason_text, condition) in reason_map.items():
                points = details.get(key, 0)
                if condition(points):
                    reasons.append(reason_text)

            return reasons[:3]
        except Exception as e:
            logger.warning(f"Error extracting momentum reasons: {e}")
            return ["Momentum analysis completed"]

    def _get_top_institutional_reasons(self, score_data: Dict[str, Any]) -> List[str]:
        """Extract top institutional reasons."""
        reasons = []
        try:
            details = score_data.get('institutional_details', {}).get('points_breakdown', {})

            reason_map = {
                'mf_increased': ('Mutual Fund Increased Holdings', lambda pts: pts >= 5),
                'fii_buying': ('FII Buying Activity', lambda pts: pts >= 4),
                'promoter_buying': ('Promoter Buying Activity', lambda pts: pts >= 3),
                'positive_block_deals': ('Positive Block Deals', lambda pts: pts >= 3)
            }

            for key, (reason_text, condition) in reason_map.items():
                points = details.get(key, 0)
                if condition(points):
                    reasons.append(reason_text)

            return reasons[:3]
        except Exception as e:
            logger.warning(f"Error extracting institutional reasons: {e}")
            return ["Institutional analysis completed"]

    def _get_top_risk_reasons(self, score_data: Dict[str, Any]) -> List[str]:
        """Extract top risk/liquidity reasons."""
        reasons = []
        try:
            details = score_data.get('risk_details', {}).get('points_breakdown', {})

            reason_map = {
                'high_liquidity': ('High Liquidity', lambda pts: pts >= 4),
                'healthy_volume': ('Healthy Trading Volume', lambda pts: pts >= 2),
                'low_spread': ('Low Bid-Ask Spread', lambda pts: pts >= 2),
                'low_operator_risk': ('Low Operator Risk', lambda pts: pts >= 2)
            }

            for key, (reason_text, condition) in reason_map.items():
                points = details.get(key, 0)
                if condition(points):
                    reasons.append(reason_text)

            return reasons[:2]  # Return top 2 for risk/liquidity
        except Exception as e:
            logger.warning(f"Error extracting risk reasons: {e}")
            return ["Risk analysis completed"]


# Convenience function for external use
def generate_explanation(score_data: Dict[str, Any]) -> str:
    """
    Convenience function to generate explanation.

    Args:
        score_data: Dictionary containing complete score analysis

    Returns:
        Formatted explanation string
    """
    generator = ExplanationGenerator()
    return generator.generate_explanation(score_data)