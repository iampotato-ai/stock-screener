"""
Unit tests for RS calculation utilities.
"""
import unittest
from app.utils.calculation import (
    calculate_weighted_return,
    calculate_percentile_rank,
    calculate_rs_scores_from_returns,
    safe_float_conversion,
    safe_get_return
)


class TestCalculationUtils(unittest.TestCase):
    
    def test_calculate_weighted_return_default_weights(self):
        """Test weighted return calculation with default weights."""
        returns = {
            '3m': 10.0,   # 10%
            '6m': 20.0,   # 20%
            '9m': 30.0,   # 30%
            '12m': 40.0   # 40%
        }
        # Expected: 0.4*10 + 0.2*20 + 0.2*30 + 0.2*40 = 4 + 4 + 6 + 8 = 22
        result = calculate_weighted_return(returns)
        self.assertEqual(result, 22.0)
    
    def test_calculate_weighted_return_custom_weights(self):
        """Test weighted return calculation with custom weights."""
        returns = {
            '3m': 10.0,
            '6m': 20.0,
            '9m': 30.0,
            '12m': 40.0
        }
        weights = {
            '3m': 0.5,
            '6m': 0.3,
            '9m': 0.1,
            '12m': 0.1
        }
        # Expected: 0.5*10 + 0.3*3*0.1*30 + 0.1*40 = 5 + 6 + 3 + 4 = 18
        result = calculate_weighted_return(returns, weights)
        self.assertEqual(result, 18.0)
    
    def test_calculate_weighted_return_partial_data(self):
        """Test weighted return with missing data."""
        returns = {
            '3m': 10.0,
            '6m': 20.0
            # Missing 9m and 12m
        }
        # With default weights, only 3m and 6m contribute
        # Total weight used = 0.4 + 0.2 = 0.6
        # Weighted sum = 0.4*10 + 0.2*20 = 4 + 4 = 8
        # Normalized = 8 / 0.6 = 13.333...
        result = calculate_weighted_return(returns)
        self.assertAlmostEqual(result, 13.333, places=3)
    
    def test_calculate_weighted_return_no_data(self):
        """Test weighted return with no data returns with no data."""
        returns = {}
        result = calculate_weighted_return(returns)
        self.assertEqual(result, 0.0)
    
    def test_calculate_percentile_rank_basic(self):
        """Test percentile ranking with basic data."""
        values = [10, 20, 30, 40, 50]  # Sorted desc: [50, 40, 30, 20, 10]
        
        # Highest value should rank 99th percentile (close to 100)
        self.assertEqual(calculate_percentile_rank(values, 50), 99)
        
        # Lowest value should rank 1st percentile
        self.assertEqual(calculate_percentile_rank(values, 10), 1)
        
        # Middle value
        self.assertEqual(calculate_percentile_rank(values, 30), 60)
    
    def test_calculate_percentile_rank_single_value(self):
        """Test percentile ranking with single value."""
        values = [42]
        # With one value, it should be 50th percentile (middle)
        self.assertEqual(calculate_percentile_rank(values, 42), 50)
    
    def test_calculate_percentile_rank_empty(self):
        """Test percentile ranking with empty list."""
        values = []
        # Should return default 50
        self.assertEqual(calculate_percentile_rank(values, 100), 50)
    
    def test_calculate_percentile_rank_duplicates(self):
        """Test percentile ranking with duplicate values."""
        values = [10, 20, 20, 20, 30]  # Sorted desc: [30, 20, 20, 20, 10]
        
        # First occurrence of 20 should get rank based on first position
        self.assertEqual(calculate_percentile_rank(values, 20), 60)
        
        # 30 (highest) should be 99
        self.assertEqual(calculate_percentile_rank(values, 30), 99)
        
        # 10 (lowest) should be 1
        self.assertEqual(calculate_percentile_rank(values, 10), 1)
    
    def test_safe_float_conversion(self):
        """Test safe float conversion."""
        self.assertEqual(safe_float_conversion("12.34"), 12.34)
        self.assertEqual(safe_float_conversion(42), 42.0)
        self.assertEqual(safe_float_conversion(None), 0.0)
        self.assertEqual(safe_float_conversion("invalid"), 0.0)
        self.assertEqual(safe_float_conversion("invalid", 99.0), 99.0)
    
    def test_safe_get_return(self):
        """Test safe return extraction."""
        data = {'3m': '15.5', '6m': 20, '9m': None}
        
        self.assertEqual(safe_get_return(data, '3m'), 15.5)
        self.assertEqual(safe_get_return(data, '6m'), 20.0)
        self.assertEqual(safe_get_return(data, '9m'), 0.0)  # Default
        self.assertEqual(safe_get_return(data, '12m'), 0.0)  # Missing key
        self.assertEqual(safe_get_return(data, '12m', -999), -999)  # Custom default
    
    def test_calculate_rs_scores_from_returns(self):
        """Test RS score calculation from returns data."""
        stocks_data = [
            {'ticker': 'AAPL', 'returns': {'3m': 10, '6m': 20, '9m': 30, '12m': 40}},
            {'ticker': 'GOOGL', 'returns': {'3m': 5, '6m': 15, '9m': 25, '12m': 35}},
            {'ticker': 'MSFT', 'returns': {'3m': 0, '6m': 0, '9m': 0, '12m': 0}},
            {'ticker': 'TSLA', 'returns': {}}  # No returns data
        ]
        
        result = calculate_rs_scores_from_returns(stocks_data)
        
        # Should have same number of items
        self.assertEqual(len(result), 4)
        
        # All should have rs_score
        for stock in result:
            self.assertIn('rs_score', stock)
            self.assertIn('momentum_score', stock)
            
        # AAPL should have highest momentum score (22.0 as calculated earlier)
        # GOOGL should be second (0.4*5 + 0.2*15 + 0.2*25 + 0.2*35 = 2+3+5+7=17)
        # MSFT should be third (0)
        # TSLA should be last (0.0 momentum score)
        
        # Find stocks by ticker
        aapl = next(s for s in result if s['ticker'] == 'AAPL')
        googl = next(s for s in result if s['ticker'] == 'GOOGL')
        msft = next(s for s in result if s['ticker'] == 'MSFT')
        tsla = next(s for s in result if s['ticker'] == 'TSLA')
        
        # AAPL should have highest RS score
        self.assertGreaterEqual(aapl['rs_score'], googl['rs_score'])
        self.assertGreaterEqual(googl['rs_score'], msft['rs_score'])
        self.assertGreaterEqual(msft['rs_score'], tsla['rs_score'])
        
        # All scores should be between 1 and 99
        for stock in result:
            self.assertGreaterEqual(stock['rs_score'], 1)
            self.assertLessEqual(stock['rs_score'], 99)


if __name__ == '__main__':
    unittest.main()