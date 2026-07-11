"""
Service for calculating Relative Strength (RS) scores.
"""
from typing import List, Dict, Any
from app.utils.calculation import (
    calculate_weighted_return,
    calculate_percentile_rank,
    safe_float_conversion,
    safe_get_return,
    DEFAULT_RS_WEIGHTS,
)
import logging

logger = logging.getLogger(__name__)


class RSService:
    """Service for calculating Relative Strength scores."""

    def __init__(self):
        # Weights are the authoritative source — defined once in calculation.py
        # as DEFAULT_RS_WEIGHTS and shared here to avoid duplication.
        # Full RS ideally uses 3M, 6M, 9M, 12M returns; we work with what
        # the screener provides. The 3M period carries the most weight (40%)
        # because recent outperformance is the strongest predictor of an EP.
        self.weights = DEFAULT_RS_WEIGHTS.copy()
        self.available_periods = list(self.weights.keys())

    def get_default_weights(self) -> dict:
        """Return a copy of the default period weights.

        The returned dict can be mutated by callers without affecting the
        service's internal configuration.
        """
        return self.weights.copy()

    def calculate_momentum_score(self, returns_dict: dict) -> float:
        """
        Calculate weighted momentum score from available returns.

        Args:
            returns_dict: Dictionary with period keys matching the service's
                configured weights (e.g. ``'3m'``, ``'6m'``, ``'9m'``, ``'12m'``)
                containing percentage returns.

        Returns:
            Weighted momentum score
        """
        return calculate_weighted_return(returns_dict, self.weights)

    def calculate_rs_scores(self, stocks_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Calculate RS scores (percentile rankings) for a list of stocks.

        Each stock is assigned an ``rs_score`` in the range 1–99 representing
        its percentile rank within this universe based on a weighted momentum
        score (3M return weighted most heavily). Stocks without any returns
        data receive ``rs_score = 0`` to distinguish them from ranked stocks.

        The output list preserves the same order as the input. Sorting by RS
        is a display concern and is handled by the frontend.

        Args:
            stocks_data: List of stock dictionaries with returns data.

        Returns:
            List of stocks (same order as input) with added fields:
              - ``rs_score`` (int): 1–99 percentile, or 0 if no returns data
              - ``momentum_score`` (float): raw weighted return used for ranking
              - ``returns_used`` (dict): which period returns were consumed
              - ``has_returns_data`` (bool): False when no period data found
        """
        if not stocks_data:
            return stocks_data

        # Calculate momentum scores for all stocks
        scored_stocks = []
        for stock in stocks_data:
            stock_copy = stock.copy()
            returns = {}

            # Primary: use period keys directly present in the stock dict
            # (e.g. '3m', '6m' pre-populated by the screener pipeline)
            for period in self.weights.keys():
                if period in stock:
                    returns[period] = safe_get_return(stock, period)

            # Fallback: map TradingView field names when direct keys are absent
            if not returns:
                if 'Perf.3M' in stock:
                    returns['3m'] = safe_get_return(stock, 'Perf.3M')
                # Note: Perf.W ('1w') and Perf.1M ('1m') are NOT in self.weights
                # and therefore do not contribute to the momentum score. They are
                # intentionally omitted here to avoid adding data that is silently
                # ignored downstream. If weekly/monthly returns are needed, add
                # '1w' and '1m' to DEFAULT_RS_WEIGHTS in calculation.py first.
                if 'Perf.W' in stock or 'Perf.1M' in stock:
                    logger.debug(
                        "RSService: Stock '%s' has Perf.W/Perf.1M TradingView keys "
                        "but these periods are not in the configured weights %s. "
                        "Only Perf.3M contributes to RS. Add '1w'/'1m' to "
                        "DEFAULT_RS_WEIGHTS in calculation.py if weekly/monthly "
                        "returns should be factored in.",
                        stock.get('ticker', stock.get('symbol', '?')),
                        list(self.weights.keys()),
                    )

            momentum_score = self.calculate_momentum_score(returns)
            stock_copy['momentum_score'] = momentum_score
            stock_copy['returns_used'] = returns
            stock_copy['has_returns_data'] = bool(returns)

            scored_stocks.append(stock_copy)

        # Build the pool of scores to rank against — only stocks with data
        momentum_scores = [
            s.get('momentum_score', 0.0)
            for s in scored_stocks
            if s.get('has_returns_data', False)
        ]

        # Assign percentile ranks
        for stock in scored_stocks:
            if stock.get('has_returns_data', False):
                momentum_score = stock.get('momentum_score', 0.0)
                if momentum_scores:
                    stock['rs_score'] = calculate_percentile_rank(momentum_scores, momentum_score)
                else:
                    stock['rs_score'] = 50  # No peers to rank against
            else:
                # Distinguish "unranked / no data" from a genuine percentile
                stock['rs_score'] = 0
                stock['momentum_score'] = 0.0

        # Return in input order — sorting by RS is a display/frontend concern
        return scored_stocks


# Singleton instance
rs_service = RSService()