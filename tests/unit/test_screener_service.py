"""
Unit tests for the ScreenerService.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.services.screener_service import screener_service
from app.models import ScanPriceLog, ScanHistory


class TestScreenerService:
    """Test cases for ScreenerService."""

    @patch('app.services.screener_service.db')
    def test_get_scan_results_success(self, mock_db):
        """Test successful retrieval of scan results."""
        # Mock the database query results
        mock_scan_history_result = MagicMock()
        mock_scan_history_result[0] = '2023-01-01'

        mock_scan_price_log_result = MagicMock()
        mock_scan_price_log_result.to_dict.return_value = {
            'ticker': 'TEST',
            'setupLabel': 'Test Setup',
            'close': 100.0
        }

        # Configure mocks
        mock_db.session.query.return_value.order_by.return_value.limit.return_value.first.return_value = mock_scan_history_result
        mock_db.session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_scan_price_log_result]

        # Call the method
        result = screener_service.get_scan_results(limit=10)

        # Assertions
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['ticker'] == 'TEST'
        assert result[0]['setup_label'] == 'Test Setup'
        assert result[0]['close'] == 100.0
        # Check that placeholder values are set
        assert result[0]['volume'] == 0
        assert result[0]['market_cap_basic'] == 0.0

    @patch('app.services.screener_service.db')
    def test_get_scan_results_no_data(self, mock_db):
        """Test handling of no scan data."""
        # Mock no scan history found
        mock_db.session.query.return_value.order_by.return_value.limit.return_value.first.return_value = None

        # Call the method
        result = screener_service.get_scan_results()

        # Assertions
        assert result == []

    @patch('app.services.screener_service.db')
    def test_get_stock_details_success(self, mock_db):
        """Test successful retrieval of stock details."""
        # Mock the database query results
        mock_scan_history_result = MagicMock()
        mock_scan_history_result[0] = '2023-01-01'

        mock_scan_price_log_result = MagicMock()
        mock_scan_price_log_result.to_dict.return_value = {
            'ticker': 'TEST',
            'setupLabel': 'Test Setup',
            'close': 100.0
        }

        # Configure mocks
        mock_db.session.query.return_value.order_by.return_value.limit.return_value.first.return_value = mock_scan_history_result
        mock_db.session.query.return_value.filter.return_value.first.return_value = mock_scan_price_log_result

        # Call the method
        result = screener_service.get_stock_details('TEST')

        # Assertions
        assert result is not None
        assert result['ticker'] == 'TEST'
        assert result['setup_label'] == 'Test Setup'
        assert result['close'] == 100.0
        # Check that placeholder values are set
        assert result['volume'] == 0
        assert result['market_cap_basic'] == 0.0

    @patch('app.services.screener_service.db')
    def test_get_stock_details_not_found(self, mock_db):
        """Test handling of stock not found."""
        # Mock scan history found but no stock data
        mock_scan_history_result = MagicMock()
        mock_scan_history_result[0] = '2023-01-01'

        # Configure mocks
        mock_db.session.query.return_value.order_by.return_value.limit.return_value.first.return_value = mock_scan_history_result
        mock_db.session.query.return_value.filter.return_value.first.return_value = None

        # Call the method
        result = screener_service.get_stock_details('NONEXISTENT')

        # Assertions
        assert result is None

    @patch('app.services.screener_service.db')
    def test_get_stock_details_exception(self, mock_db):
        """Test handling of database exceptions."""
        # Mock an exception
        mock_db.session.query.side_effect = Exception("Database error")

        # Call the method
        result = screener_service.get_stock_details('TEST')

        # Assertions
        assert result is None

    @patch('app.services.screener_service.current_app')
    @patch('app.services.screener_service.time')
    @patch('app.services.screener_service.threading.Thread')
    def test_refresh_screener_data_success(self, mock_thread, mock_time, mock_current_app):
        """Test successful triggering of data refresh."""
        # Mock time and lock
        mock_time.time.return_value = 1000.0
        mock_lock = MagicMock()
        mock_current_app._get_current_object.return_value = MagicMock()

        # Patch the refresh_lock
        with patch.object(screener_service, 'refresh_lock', mock_lock):
            with patch.object(screener_service, 'last_refresh_time', 900.0):
                # Call the method
                result = screener_service.refresh_screener_data()

                # Assertions
                assert result is True
                mock_thread.assert_called_once()
                mock_current_app.logger.info.assert_called_with("Background screener refresh triggered")

    @patch('app.services.screener_service.time')
    def test_refresh_screener_data_cooldown(self, mock_time):
        """Test that refresh respects cooldown period."""
        # Mock time to be within cooldown period
        mock_time.time.return_value = 1000.0

        # Patch the refresh_lock and last_refresh_time
        with patch.object(screener_service, 'refresh_lock'):
            with patch.object(screener_service, 'last_refresh_time', 950.0):  # Only 50 seconds ago
                # Call the method
                result = screener_service.refresh_screener_data()

                # Assertions
                assert result is False  # Should return False due to cooldown


if __name__ == "__main__":
    pytest.main([__file__])