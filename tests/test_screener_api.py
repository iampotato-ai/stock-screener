"""
Unit tests for the screener API.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.api.v1 import screener
from flask import Flask


def test_screener_api_import():
    """Test that the screener API module can be imported."""
    assert screener is not None
    print("✓ Screener API imported successfully")


def test_screener_api_has_expected_routes():
    """Test that the screener API has the expected routes."""
    # Check that the routes are defined
    assert hasattr(screener, 'get_screener_scan')
    assert hasattr(screener, 'get_screener_stock_detail')
    assert hasattr(screener, 'refresh_screener_data')
    print("✓ Screener API has expected route functions")


if __name__ == "__main__":
    test_screener_api_import()
    test_screener_api_has_expected_routes()
    print("All screener API tests passed!")