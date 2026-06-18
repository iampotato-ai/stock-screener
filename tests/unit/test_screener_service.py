"""
Unit tests for the ScreenerService.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.services.screener_service import screener_service


class TestScreenerService:
    """Test cases for ScreenerService."""

    @patch('app.database.get_latest_scan_results')
    def test_get_scan_results_success(self, mock_get_latest_scan_results, flask_app):
        """Test successful retrieval of scan results."""
        # Mock the database function to return a list of dictionaries
        mock_get_latest_scan_results.return_value = [
            {
                'ticker': 'TEST',
                'setupLabel': 'Test Setup',
                'close': 100.0
            }
        ]

        with flask_app.app_context():
            # Call the method
            result = screener_service.get_scan_results(limit=10)

            # Assertions
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]['ticker'] == 'TEST'
            assert result[0]['setup_label'] == 'Test Setup'
            assert result[0]['close'] == 100.0
            assert result[0]['clean_ticker'] == 'TEST'

    @patch('app.database.get_latest_scan_results')
    def test_get_scan_results_no_data(self, mock_get_latest_scan_results, flask_app):
        """Test handling of no scan data."""
        # Mock no scan history found
        mock_get_latest_scan_results.return_value = []

        with flask_app.app_context():
            # Call the method
            result = screener_service.get_scan_results()

            # Assertions
            assert result == []

    @patch('app.database.get_stock_details')
    def test_get_stock_details_success(self, mock_get_stock_details, flask_app):
        """Test successful retrieval of stock details."""
        # Mock the database function to return a dictionary
        mock_get_stock_details.return_value = {
            'ticker': 'TEST',
            'price_data': {
                'close': 100.0,
                'swingband': 'elite',
                'setupLabel': 'Test Setup'
            },
            'fundamentals': None,
            'ep_features': None
        }

        with flask_app.app_context():
            # Call the method
            result = screener_service.get_stock_details('TEST')

            # Assertions
            assert result is not None
            assert result['ticker'] == 'TEST'
            assert result['price_data']['close'] == 100.0
            assert result['price_data']['setupLabel'] == 'Test Setup'

    @patch('app.database.get_stock_details')
    def test_get_stock_details_not_found(self, mock_get_stock_details, flask_app):
        """Test handling of stock not found."""
        # Mock no stock data found
        mock_get_stock_details.return_value = None

        with flask_app.app_context():
            # Call the method
            result = screener_service.get_stock_details('NONEXISTENT')

            # Assertions
            assert result is None

    @patch('app.database.get_stock_details')
    def test_get_stock_details_exception(self, mock_get_stock_details, flask_app):
        """Test handling of database exceptions."""
        # Mock an exception
        mock_get_stock_details.side_effect = Exception("Database error")

        with flask_app.app_context():
            # Call the method
            result = screener_service.get_stock_details('TEST')

            # Assertions
            assert result is None

    @patch('app.services.screener_service.time')
    @patch('app.services.screener_service.threading.Thread')
    def test_refresh_screener_data_success(self, mock_thread, mock_time, flask_app):
        """Test successful triggering of data refresh."""
        # Mock time and lock
        mock_time.time.return_value = 1000.0
        mock_lock = MagicMock()

        # Patch the refresh_lock
        with flask_app.app_context():
            with patch.object(screener_service, 'refresh_lock', mock_lock):
                with patch.object(screener_service, 'last_refresh_time', 900.0):
                    # Call the method
                    result = screener_service.refresh_screener_data()

                    # Assertions
                    assert result is True
                    mock_thread.assert_called_once()

    @patch('app.services.screener_service.time')
    def test_refresh_screener_data_cooldown(self, mock_time, flask_app):
        """Test that refresh respects cooldown period."""
        # Mock time to be within cooldown period
        mock_time.time.return_value = 1000.0

        with flask_app.app_context():
            # Patch the refresh_lock and last_refresh_time
            with patch.object(screener_service, 'refresh_lock'):
                with patch.object(screener_service, 'last_refresh_time', 950.0):  # Only 50 seconds ago
                    # Call the method
                    result = screener_service.refresh_screener_data()

                    # Assertions
                    assert result is False  # Should return False due to cooldown