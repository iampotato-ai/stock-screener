"""
Ranking Module for Momentum Confidence Score™
Handles daily stock ranking by score
"""
import logging
from typing import Dict, Any, List
from datetime import datetime, date

logger = logging.getLogger(__name__)

class StockRanker:
    """
    Handles ranking of stocks by Momentum Confidence Score.
    """

    def __init__(self):
        """Initialize the stock ranker."""
        pass

    def rank_stocks(self, scores: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Rank stocks by their Momentum Confidence Score.

        Args:
            scores: List of dictionaries containing score data for each stock

        Returns:
            List of ranked stocks with rank position added
        """
        try:
            # Filter out invalid scores
            valid_scores = [s for s in scores if s.get('total_score') is not None]

            # Sort by total score descending (highest first)
            sorted_scores = sorted(
                valid_scores,
                key=lambda x: x.get('total_score', 0),
                reverse=True
            )

            # Add rank to each stock
            ranked_scores = []
            for i, score_data in enumerate(sorted_scores, 1):
                score_data_with_rank = score_data.copy()
                score_data_with_rank['rank'] = i
                ranked_scores.append(score_data_with_rank)

            logger.debug(f"Ranked {len(ranked_scores)} stocks")
            return ranked_scores

        except Exception as e:
            logger.error(f"Error ranking stocks: {e}")
            # Return original list if ranking fails
            return scores

    def get_top_stocks(self, scores: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top N stocks by score.

        Args:
            scores: List of dictionaries containing score data for each stock
            limit: Maximum number of stocks to return

        Returns:
            List of top ranked stocks
        """
        try:
            ranked_scores = self.rank_stocks(scores)
            return ranked_scores[:limit]
        except Exception as e:
            logger.error(f"Error getting top stocks: {e}")
            return scores[:limit] if scores else []

    def get_stocks_by_score_range(self, scores: List[Dict[str, Any]],
                                 min_score: int, max_score: int) -> List[Dict[str, Any]]:
        """
        Get stocks within a specific score range.

        Args:
            scores: List of dictionaries containing score data for each stock
            min_score: Minimum score (inclusive)
            max_score: Maximum score (inclusive)

        Returns:
            List of stocks within the score range
        """
        try:
            filtered_scores = [
                s for s in scores
                if min_score <= s.get('total_score', 0) <= max_score
            ]
            return self.rank_stocks(filtered_scores)
        except Exception as e:
            logger.error(f"Error filtering stocks by score range: {e}")
            return []

    def get_daily_ranking(self, scores: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate a daily ranking report.

        Args:
            scores: List of dictionaries containing score data for each stock

        Returns:
            Dictionary containing ranking statistics and top stocks
        """
        try:
            if not scores:
                return {
                    'date': date.today().isoformat(),
                    'total_stocks': 0,
                    'ranked_stocks': 0,
                    'average_score': 0,
                    'top_stocks': [],
                    'score_distribution': {}
                }

            ranked_scores = self.rank_stocks(scores)
            total_stocks = len(scores)
            ranked_stocks_with_scores = [s for s in scores if s.get('total_score') is not None]
            average_score = sum(s.get('total_score', 0) for s in ocked_with_scores) / len(ocked_with_scores) if ocked_with_scores else 0

            # Score distribution
            distribution = {
                '95-100': len([s for s in ocked_with_scores if 95 <= s.get('total_score', 0) <= 100]),
                '90-94': len([s for s in ocked_with_scores if 90 <= s.get('total_score', 0) <= 94]),
                '80-89': len([s for s in ocked_with_scores if 80 <= s.get('total_score', 0) <= 89]),
                '70-79': len([s for s in ocked_with_scores if 70 <= s.get('total_score', 0) <= 79]),
                '60-69': len([s for s in ocked_with_scores if 60 <= s.get('total_score', 0) <= 69]),
                '0-59': len([s for s in ocked_with_scores if 0 <= s.get('total_score', 0) <= 59])
            }

            return {
                'date': date.today().isoformat(),
                'total_stocks': total_stocks,
                'ranked_stocks': len(ocked_with_scores),
                'average_score': round(average_score, 2),
                'top_stocks': ranked_scores[:10],  # Top 10
                'score_distribution': distribution
            }

        except Exception as e:
            logger.error(f"Error generating daily ranking: {e}")
            return {
                'date': date.today().isoformat(),
                'error': str(e)
            }


# Convenience functions for external use
def rank_stocks(scores: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convenience function to rank stocks by score.

    Args:
        scores: List of dictionaries containing score data for each stock

    Returns:
        List of ranked stocks with rank position added
    """
    ranker = StockRanker()
    return ranker.rank_stocks(scores)


def get_top_stocks(scores: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    """
    Convenience function to get top N stocks by score.

    Args:
        scores: List of dictionaries containing score data for each stock
        limit: Maximum number of stocks to return

    Returns:
        List of top ranked stocks
    """
    ranker = StockRanker()
    return ranker.get_top_stocks(scores, limit)


def get_daily_ranking(scores: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convenience function to generate a daily ranking report.

    Args:
        scores: List of dictionaries containing score data for each stock

    Returns:
        Dictionary containing ranking statistics and top stocks
    """
    ranker = StockRanker()
    return ranker.get_daily_ranking(scores)