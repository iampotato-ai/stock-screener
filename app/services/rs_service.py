"""
Service for calculating Relative Strength (RS) scores.
"""
from typing import List, Dict, Any
from app.utils.calculation import (
    calculate_weighted_return,
    calculate_percentile_rank,
    safe_float_conversion,
    safe_get_return
)
import logging

logger = logging.getLogger(__name__)


class RSService:
    """Service for calculating Relative Strength scores."""
    
    def __init__(self):
        # Available data from TradingView: 1W, 1M, 3M
        # We'll use these to calculate a momentum score
        # Note: Full RS calculation ideally uses 3M, 6M, 9M, 12M returns
        # but we work with what's available from the screener
        self.weights = {
            '3m': 0.40,
            '6m': 0.20,
            '9m': 0.20,
            '12m': 0.20,
        }
        self.available_periods = ['3m', '6m', '9m', '12m']
    
    def get_default_weights(self) -> dict:
        """Return a copy of the default period weights.

        The returned dict can be mutated by callers without affecting the
        service's internal configuration.
        """
        return self.weights.copy()

    def has_sufficient_data(self, returns_dict: dict) -> bool:
        """Determine if *returns_dict* contains any usable numeric period data.

        At least one of the configured period keys must be present with a
        value that can be safely converted to ``float``. ``None`` or a non‑
        numeric string is considered insufficient.
        """
        for period in self.weights.keys():
            if period in returns_dict:
                # Use safe_float_conversion to test convertibility
                try:
                    if isinstance(returns_dict[period], (int, float)):
                        return True
                    # Attempt conversion for strings
                    float(returns_dict[period])
                    return True
                except (TypeError, ValueError):
                    continue
        return False
    def calculate_momentum_score(self, returns_dict: dict) -> float:
        """
        Calculate weighted momentum score from available returns.
        
        Args:
            returns_dict: Dictionary with period keys matching the service's
                configured weights (e.g. ``'3m'``, ``'6m'``, ``'9m'``, ``'12m'``)
                containing percentage returns.
            Weighted momentum score
        """
        return calculate_weighted_return(returns_dict, self.weights)
    
    def calculate_rs_scores(self, stocks_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Calculate RS scores (percentile rankings) for a list of stocks.
        
        Args:
            stocks_data: List of stock dictionaries with returns data
            
        Returns:
            List of stocks with added 'rs_score' field (1-99)
        """
        if not stocks_data:
            return stocks_data
        
        # Calculate momentum scores for all stocks
        scored_stocks = []
        for stock in stocks_data:
            stock_copy = stock.copy()
            returns = {}
            # Directly use period keys present in the stock dict (e.g., '3m', '6m', ...)
            for period in self.weights.keys():
                if period in stock:
                    returns[period] = safe_get_return(stock, period)
            # Fallback to TradingView keys if direct keys are absent
            if not returns:
                if 'Perf.W' in stock:
                    returns['1w'] = safe_get_return(stock, 'Perf.W')
                if 'Perf.1M' in stock:
                    returns['1m'] = safe_get_return(stock, 'Perf.1M')
                if 'Perf.3M' in stock:
                    returns['3m'] = safe_get_return(stock, 'Perf.3M')
            # Calculate momentum score
            momentum_score = self.calculate_momentum_score(returns)
            stock_copy['momentum_score'] = momentum_score
            stock_copy['returns_used'] = returns
            stock_copy['has_returns_data'] = bool(returns)
            
            scored_stocks.append(stock_copy)
        
        # Extract momentum scores for ranking (only from stocks with data)
        momentum_scores = [
            s.get('momentum_score', 0.0)
            for s in scored_stocks
            if s.get('has_returns_data', False)
        ]
        
        # Calculate RS scores based on percentile ranking
        for stock in scored_stocks:
            if stock.get('has_returns_data', False):
                momentum_score = stock.get('momentum_score', 0.0)
                if momentum_scores:  # Only calculate if we have data to rank against
                    rs_score = calculate_percentile_rank(momentum_scores, momentum_score)
                    stock['rs_score'] = rs_score
                else:
                    stock['rs_score'] = 50  # Default if no comparable data
            else:
                # No returns data available
                stock['rs_score'] = 0  # Indicates insufficient data
                stock['momentum_score'] = 0.0
        
        # Sort by RS score descending (highest first)
        return sorted(scored_stocks, key=lambda x: x.get('rs_score', 0), reverse=True)


# Singleton instance
rs_service = RSService()