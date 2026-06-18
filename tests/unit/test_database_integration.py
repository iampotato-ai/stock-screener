"""
Unit tests for database integration using actual models.
"""
import pytest
import os
import tempfile
from app import create_app
from app.models import db, ScanHistory, ScanPriceLog
from app.services.screener_service import screener_service


class TestScreenerServiceIntegration:
    """Integration tests for ScreenerService with real database."""

    @pytest.fixture
    def app(self):
        """Create and configure a new app instance for each test."""
        # Create a temporary file to isolate the database for each test
        db_fd, db_path = tempfile.mkstemp()
        app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        })

        # Create the database and load test data
        with app.app_context():
            db.create_all()
            yield app

        # Close and remove the temporary database
        os.close(db_fd)
        os.unlink(db_path)

    @pytest.fixture
    def client(self, app):
        """A test client for the app."""
        return app.test_client()

    def test_get_scan_results_empty_db(self, app):
        """Test get_scan_results with empty database."""
        with app.app_context():
            result = screener_service.get_scan_results()
            assert result == []

    def test_get_scan_results_with_data(self, app):
        """Test get_scan_results with data in database."""
        with app.app_context():
            # Create test data
            scan_history = ScanHistory(scan_date='2023-01-01')
            db.session.add(scan_history)
            db.session.flush()  # Get the ID

            scan_price_log = ScanPriceLog(
                scan_history_id=scan_history.id,
                ticker='TEST',
                setup_label='Test Setup',
                close=100.0
            )
            db.session.add(scan_price_log)
            db.session.commit()

            # Test the service method
            result = screener_service.get_scan_results(limit=10)

            # Assertions
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]['ticker'] == 'TEST'
            assert result[0]['setup_label'] == 'Test Setup'
            assert result[0]['close'] == 100.0
            # Check that placeholder values are set (from the service)
            assert result[0]['volume'] == 0
            assert result[0]['market_cap_basic'] == 0.0

    def test_get_stock_details_found(self, app):
        """Test get_stock_details with existing ticker."""
        with app.app_context():
            # Create test data
            scan_history = ScanHistory(scan_date='2023-01-01')
            db.session.add(scan_history)
            db.session.flush()

            scan_price_log = ScanPriceLog(
                scan_history_id=scan_history.id,
                ticker='TEST',
                setup_label='Test Setup',
                close=100.0
            )
            db.session.add(scan_price_log)
            db.session.commit()

            # Test the service method
            result = screener_service.get_stock_details('TEST')

            # Assertions
            assert result is not None
            assert result['ticker'] == 'TEST'
            assert result['setup_label'] == 'Test Setup'
            assert result['close'] == 100.0
            # Check that placeholder values are set
            assert result['volume'] == 0
            assert result['market_cap_basic'] == 0.0

    def test_get_stock_details_not_found(self, app):
        """Test get_stock_details with non-existent ticker."""
        with app.app_context():
            # Create test data with different ticker
            scan_history = ScanHistory(scan_date='2023-01-01')
            db.session.add(scan_history)
            db.session.flush()

            scan_price_log = ScanPriceLog(
                scan_history_id=scan_history.id,
                ticker='OTHER',
                setup_label='Other Setup',
                close=50.0
            )
            db.session.add(scan_price_log)
            db.session.commit()

            # Test the service method
            result = screener_service.get_stock_details('NONEXISTENT')

            # Assertions
            assert result is None

    def test_get_stock_details_exception_handling(self, app):
        """Test get_stock_details handles exceptions gracefully."""
        with app.app_context():
            # Trigger an exception by causing a database error
            # We'll patch the query to raise an exception
            with patch('app.services.screener_service.db.session.query') as mock_query:
                mock_query.side_effect = Exception("Database error")

                result = screener_service.get_stock_details('TEST')
                assert result is None


# Need to import patch for the exception test
from unittest.mock import patch