"""
Integration tests for RS scores in screener.
"""
import unittest
from unittest.mock import patch, MagicMock
from app.services.screener_service import screener_service


class TestScreenerWithRS(unittest.TestCase):
    
    @patch('app.services.screener_service.rs_service')
    def test_get_scan_results_live_with_rs(self, mock_rs_service):
        """Test that live screener results include RS scores."""
        # Mock the rs_service.calculate_rs_scores method
        mock_stocks_with_rs = [
            {'ticker': 'STOCK1', 'rs_score': 85},
            {'ticker': 'STOCK2', 'rs_score': 60}
        ]
        mock_rs_service.calculate_rs_scores.return_value = mock_stocks_with_rs
        
        # Mock the scan_stocks function from legacy_routes
        with patch('app.api.v1.legacy_routes.scan_stocks') as mock_scan_stocks:
            mock_response = MagicMock()
            mock_response.get_json.return_value = {
                'stocks': [
                    {'ticker': 'STOCK1', 'Perf.3M': 10, 'Perf.6M': 20, 'Perf.9M': 30, 'Perf.12M': 40},
                    {'ticker': 'STOCK2', 'Perf.3M': 5, 'Perf.6M': 15, 'Perf.9M': 25, 'Perf.12M': 35}
                ],
                'total_scanned': 100,
                'total_matched': 50,
                'universe': ['STOCK1', 'STOCK2']
            }
            mock_scan_stocks.return_value = mock_response
            
            # Call the method
            result = screener_service.get_scan_results(limit=10, live=True, full_response=True)
            
            # Verify rs_service.calculate_rs_scores was called
            mock_rs_service.calculate_rs_scores.assert_called_once()
            
            # Verify the result structure
            self.assertEqual(result['total_scanned'], 100)
            self.assertEqual(result['total_matched'], 50)
            self.assertEqual(len(result['stocks']), 2)
            self.assertEqual(result['stocks'][0]['ticker'], 'STOCK1')
            self.assertEqual(result['stocks'][0]['rs_score'], 85)
            self.assertEqual(result['stocks'][1]['ticker'], 'STOCK2')
            self.assertEqual(result['stocks'][1]['rs_score'], 60)
    
    @patch('app.services.screener_service.rs_service')
    def test_get_scan_results_database_with_rs(self, mock_rs_service):
        """Test that database screener results include RS scores."""
        # Mock the rs_service.calculate_rs_scores method
        mock_stocks_with_rs = [
            {'ticker': 'STOCK1', 'rs_score': 90, 'clean_ticker': 'STOCK1'},
            {'ticker': 'STOCK2', 'rs_score': 70, 'clean_ticker': 'STOCK2'}
        ]
        mock_rs_service.calculate_rs_scores.return_value = mock_stocks_with_rs
        
        # Mock the database function
        with patch('app.database.get_latest_scan_results') as mock_get_results:
            # Mock return value - list of sqlite3.Row-like objects
            mock_row1 = MagicMock()
            mock_row1.__getitem__.side_effect = lambda key: {
                'ticker': 'STOCK1',
                'setupLabel': 'Setup1'
            }.get(key, None)
            
            mock_row2 = MagicMock()
            mock_row2.__getitem__.side_effect = lambda key: {
                'ticker': 'STOCK2',
                'setupLabel': 'Setup2'
            }.get(key, None)
            
            mock_get_results.return_value = [mock_row1, mock_row2]
            
            # Call the method
            result = screener_service.get_scan_results(limit=10, live=False, full_response=True)
            
            # Verify rs_service.calculate_rs_scores was called
            mock_rs_service.calculate_rs_scores.assert_called_once()
            
            # Verify the result structure
            self.assertEqual(result['total_scanned'], 2)
            self.assertEqual(result['total_matched'], 2)
            self.assertEqual(len(result['stocks']), 2)
            self.assertEqual(result['stocks'][0]['ticker'], 'STOCK1')
            self.assertEqual(result['stocks'][0]['rs_score'], 90)
            self.assertEqual(result['stocks'][0]['clean_ticker'], 'STOCK1')
            self.assertEqual(result['stocks'][1]['ticker'], 'STOCK2')
            self.assertEqual(result['stocks'][1]['rs_score'], 70)
            self.assertEqual(result['stocks'][1]['clean_ticker'], 'STOCK2')
    
    def test_get_stock_details_unchanged(self):
        """Test that get_stock_details is not affected by RS changes."""
        # This method should remain unchanged
        with patch('app.database.get_stock_details') as mock_get_stock:
            mock_get_stock.return_value = None
            
            result = screener_service.get_stock_details('INVALID')
            
            self.assertIsNone(result)
            mock_get_stock.assert_called_once_with('INVALID')


if __name__ == '__main__':
    unittest.main()