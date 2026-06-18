"""
Unit tests for custom exceptions.
"""
import pytest
from app.utils.exceptions import (
    StockScreenerException,
    ServiceException,
    DataAccessException,
    ValidationException,
    ExternalAPIException,
    ConfigurationException
)


def test_stock_screener_exception_base():
    """Test that StockScreenerException is the base exception."""
    exc = StockScreenerException("Base exception")
    assert str(exc) == "Base exception"
    assert isinstance(exc, Exception)


def test_service_exception():
    """Test ServiceException formatting."""
    exc = ServiceException("Service error", "test_service")
    assert "[test_service] Service error" in str(exc)

    # Test without service name
    exc_no_service = ServiceException("Service error")
    assert "Service error" in str(exc_no_service)
    assert "[None]" not in str(exc_no_service)


def test_data_access_exception():
    """Test DataAccessException formatting."""
    exc = DataAccessException("Query failed", "SELECT * FROM table")
    assert "[DataAccess] Query failed Query: SELECT * FROM table" in str(exc)

    # Test without query
    exc_no_query = DataAccessException("Query failed")
    assert "[DataAccess] Query failed" in str(exc_no_query)


def test_validation_exception():
    """Test ValidationException formatting."""
    exc = ValidationException("Invalid value", "email")
    assert "[Validation] Invalid value Field: email" in str(exc)

    # Test without field
    exc_no_field = ValidationException("Invalid value")
    assert "[Validation] Invalid value" in str(exc_no_field)


def test_external_api_exception():
    """Test ExternalAPIException formatting."""
    exc = ExternalAPIException("API error", "news_api", 500)
    assert "[ExternalAPI:news_api] API error Status: 500" in str(exc)

    # Test without status code
    exc_no_status = ExternalAPIException("API error", "news_api")
    assert "[ExternalAPI:news_api] API error" in str(exc_no_status)

    # Test without api name
    exc_no_api = ExternalAPIException("API error")
    assert "[ExternalAPI:None] API error" in str(exc_no_api)


def test_configuration_exception():
    """Test ConfigurationException formatting."""
    exc = ConfigurationException("Missing config", "API_KEY")
    assert "[Configuration] Missing config Key: API_KEY" in str(exc)

    # Test without config key
    exc_no_key = ConfigurationException("Missing config")
    assert "[Configuration] Missing config" in str(exc_no_key)


if __name__ == "__main__":
    pytest.main([__file__])