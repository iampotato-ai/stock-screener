"""
Unit tests for database integration using actual models.
"""
import pytest
import os
import tempfile
from datetime import date
from app import create_app
from app.models import db, ScanHistory, ScanPriceLog
from app.services.screener_service import screener_service
from unittest.mock import patch


class TestScreenerServiceIntegration:
    """Integration tests for ScreenerService with real database."""

    @pytest.fixture
    def app(self):
        """Create and configure a new app instance for each test."""
        # Create a temporary file to isolate the database for each test
        db_fd, db_path = tempfile.mkstemp()
        os.close(db_fd)
        
        # We must set DATABASE in env so raw SQL database helper uses the correct path
        os.environ['DATABASE'] = db_path
        os.environ['TEST_DATABASE_URL'] = f'sqlite:///{db_path}'
        
        app = create_app('testing', overrides={
            'DATABASE': db_path,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        })

        # Create the database and load test data
        with app.app_context():
            from app.database import init_db_app
            init_db_app()  # Initialize raw database path and tables
            db.create_all()  # Create all SQLAlchemy models/tables
            yield app

        # Clean up environment and files
        os.environ.pop('DATABASE', None)
        os.environ.pop('TEST_DATABASE_URL', None)
        try:
            os.unlink(db_path)
        except OSError:
            pass

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
            test_date = date(2023, 1, 1)
            scan_history = ScanHistory(date=test_date, ticker='TEST')
            db.session.add(scan_history)
            db.session.flush()

            scan_price_log = ScanPriceLog(
                date=test_date,
                ticker='TEST',
                close=100.0,
                setupLabel='Test Setup',
                swingband='elite'
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
            assert result[0]['swingband'] == 'elite'

    def test_get_stock_details_found(self, app):
        """Test get_stock_details with existing ticker."""
        with app.app_context():
            # Create test data
            test_date = date(2023, 1, 1)
            scan_history = ScanHistory(date=test_date, ticker='TEST')
            db.session.add(scan_history)
            db.session.flush()

            scan_price_log = ScanPriceLog(
                date=test_date,
                ticker='TEST',
                close=100.0,
                setupLabel='Test Setup',
                swingband='elite'
            )
            db.session.add(scan_price_log)
            db.session.commit()

            # Test the service method
            result = screener_service.get_stock_details('TEST')

            # Assertions
            assert result is not None
            assert result['ticker'] == 'TEST'
            assert result['price_data'] is not None
            assert result['price_data']['close'] == 100.0
            assert result['price_data']['setupLabel'] == 'Test Setup'
            assert result['price_data']['swingband'] == 'elite'

    def test_get_stock_details_not_found(self, app):
        """Test get_stock_details with non-existent ticker."""
        with app.app_context():
            # Create test data with different ticker
            test_date = date(2023, 1, 1)
            scan_history = ScanHistory(date=test_date, ticker='OTHER')
            db.session.add(scan_history)
            db.session.flush()

            scan_price_log = ScanPriceLog(
                date=test_date,
                ticker='OTHER',
                close=50.0,
                setupLabel='Other Setup',
                swingband='watch'
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
            # Trigger an exception by causing a database error on raw query
            with patch('app.database.fetch_one') as mock_fetch:
                mock_fetch.side_effect = Exception("Database error")

                result = screener_service.get_stock_details('TEST')
                assert result is None