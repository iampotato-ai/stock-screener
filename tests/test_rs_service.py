"""
Unit tests for RS service.
"""
import unittest
from unittest.mock import patch, MagicMock
from app.services.rs_service import rs_service, RSService


class TestRSService(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.service = RSService()
    
    def test_init(self):
        """Test RSService initialization."""
        self.assertIsInstance(self.service, RSService)
        self.assertEqual(self.service.weights['3m'], 0.40)
        self.assertEqual(self.service.weights['6m'], 0.20)
        self.assertEqual(self.service.weights['9m'], 0.20)
        self.assertEqual(self.service.weights['12m'], 0.20)
    
    def test_calculate_momentum_score(self):
        """Test momentum score calculation."""
        returns = {
            '3m': 10.0,
            '6m': 20.0,
            '9m': 30.0,
            '12m': 40.0
        }
        # Expected: 0.4*10 + 0.2*20 + 0.2*30 + 0.2*40 = 4 + 4 + 6 + 8 = 22
        result = self.service.calculate_momentum_score(returns)
        self.assertEqual(result, 22.0)
    
    def test_calculate_momentum_score_partial_data(self):
        """Test momentum score with partial data."""
        returns = {
            '3m': 10.0,
            '6m': 20.0
            # Missing 9m and 12m
        }
        result = self.service.calculate_momentum_score(returns)
        # Should use only available data with default weights
        # Weighted sum = 0.4*10 + 0.2*20 = 4 + 4 = 8
        # Total weight used = 0.4 + 0.2 = 0.6
        # Result = 8 / 0.6 = 13.333...
        self.assertAlmostEqual(result, 13.333, places=3)
    
    def test_calculate_momentum_score_no_data(self):
        """Test momentum score with no data."""
        returns = {}
        result = self.service.calculate_momentum_score(returns)
        self.assertEqual(result, 0.0)
    
    def test_calculate_rs_scores_empty_list(self):
        """Test RS score calculation with empty list."""
        result = self.service.calculate_rs_scores([])
        self.assertEqual(result, [])
    
    def test_calculate_rs_scores_single_stock(self):
        """Test RS score calculation with single stock."""
        stocks_data = [
            {'ticker': 'TEST', '3m': 10, '6m': 20, '9m': 30, '12m': 40}
        ]
        
        result = self.service.calculate_rs_scores(stocks_data)
        
        self.assertEqual(len(result), 1)
        stock = result[0]
        self.assertEqual(stock['ticker'], 'TEST')
        self.assertEqual(stock['momentum_score'], 22.0)  # As calculated before
        # With only one stock, it should get middle rank (50)
        self.assertEqual(stock['rs_score'], 50)
    
    def test_calculate_rs_scores_multiple_stocks(self):
        """Test RS score calculation with multiple stocks."""
        stocks_data = [
            {'ticker': 'LOW', '3m': 0, '6m': 0, '9m': 0, '12m': 0},
            {'ticker': 'MED', '3m': 10, '6m': 10, '9m': 10, '12m': 10},
            {'ticker': 'HIGH', '3m': 20, '6m': 20, '9m': 20, '12m': 20}
        ]
        
        result = self.service.calculate_rs_scores(stocks_data)
        
        self.assertEqual(len(result), 3)
        
        # Should be sorted by RS score descending
        self.assertEqual(result[0]['ticker'], 'HIGH')  # Highest RS score
        self.assertEqual(result[1]['ticker'], 'MED')   # Middle RS score
        self.assertEqual(result[2]['ticker'], 'LOW')   # Lowest RS score
        
        # Check that scores are in expected range and ordered
        self.assertGreaterEqual(result[0]['rs_score'], result[1]['rs_score'])
        self.assertGreaterEqual(result[1]['rs_score'], result[2]['rs_score'])
        
        # All scores should be between 1 and 99
        for stock in result:
            self.assertGreaterEqual(stock['rs_score'], 1)
            self.assertLessEqual(stock['rs_score'], 99)
    
    def test_calculate_rs_scores_with_missing_data(self):
        """Test RS score calculation with some stocks missing data."""
        stocks_data = [
            {'ticker': 'GOOD_DATA', '3m': 10, '6m': 20, '9m': 30, '12m': 40},
            {'ticker': 'PARTIAL_DATA', '3m': 15, '6m': 25},  # Missing 9m, 12m
            {'ticker': 'NO_DATA', 'other_field': 'value'}  # No return data
        ]
        
        result = self.service.calculate_rs_scores(stocks_data)
        
        self.assertEqual(len(result), 3)
        
        # Find each stock
        good = next(s for s in result if s['ticker'] == 'GOOD_DATA')
        partial = next(s for s in result if s['ticker'] == 'PARTIAL_DATA')
        none = next(s for s in result if s['ticker'] == 'NO_DATA')
        
        # GOOD_DATA should have highest RS score (has all data)
        self.assertGreaterEqual(good['rs_score'], partial['rs_score'])
        
        # NO_DATA should have rs_score of 0 (indicates insufficient data)
        self.assertEqual(none['rs_score'], 0)
        self.assertEqual(none['momentum_score'], 0.0)
        self.assertFalse(none.get('has_returns_data', False))
    
    def test_has_sufficient_data(self):
        """Test checking for sufficient data."""
        # Should return True for valid data
        self.assertTrue(self.service.has_sufficient_data({'3m': 10}))
        self.assertTrue(self.service.has_sufficient_data({'6m': -5}))
        self.assertTrue(self.service.has_sufficient_data({'12m': 0}))
        
        # Should return False for invalid or missing data
        self.assertFalse(self.service.has_sufficient_data({}))
        self.assertFalse(self.service.has_sufficient_data({'other': 10}))
        self.assertFalse(self.service.has_sufficient_data({'3m': None}))
        self.assertFalse(self.service.has_sufficient_data({'3m': 'invalid'}))
    
    def test_get_default_weights(self):
        """Test getting default weights."""
        weights = self.service.get_default_weights()
        self.assertIsInstance(weights, dict)
        self.assertEqual(weights['3m'], 0.40)
        self.assertEqual(weights['6m'], 0.20)
        self.assertEqual(weights['9m'], 0.20)
        self.assertEqual(weights['12m'], 0.20)
        
        # Should return a copy, not the original
        weights['3m'] = 0.99
        self.assertEqual(self.service.weights['3m'], 0.40)  # Original unchanged


if __name__ == '__main__':
    unittest.main()