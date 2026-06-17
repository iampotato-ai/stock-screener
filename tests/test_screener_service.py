"""
Unit tests for the screener service.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.screener_service import screener_service


def test_screener_service_import():
    """Test that the screener service can be imported."""
    assert screener_service is not None
    print("✓ Screener service imported successfully")


def test_screener_service_has_expected_methods():
    """Test that the screener service has the expected methods."""
    assert hasattr(screener_service, 'get_scan_results')
    assert hasattr(screener_service, 'get_stock_details')
    assert hasattr(screener_service, 'refresh_screener_data')
    print("✓ Screener service has expected methods")


if __name__ == "__main__":
    test_screener_service_import()
    test_screener_service_has_expected_methods()
    print("All screener service tests passed!")