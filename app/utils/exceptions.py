"""
Custom exceptions for the Stock Screener application.
"""
class StockScreenerException(Exception):
    """Base exception for all stock screener custom exceptions."""
    pass

class ServiceException(StockScreenerException):
    """Exception raised for errors in the service layer."""
    def __init__(self, message: str, service_name: str = None):
        self.service_name = service_name
        super().__init__(f"[{service_name}] {message}" if service_name else message)

class DataAccessException(StockScreenerException):
    """Exception raised for errors in data access operations."""
    def __init__(self, message: str, query: str = None):
        self.query = query
        super().__init__(f"[DataAccess] {message}" + (f" Query: {query}" if query else ""))

class ValidationException(StockScreenerException):
    """Exception raised for validation errors."""
    def __init__(self, message: str, field: str = None):
        self.field = field
        super().__init__(f"[Validation] {message}" + (f" Field: {field}" if field else ""))

class ExternalAPIException(StockScreenerException):
    """Exception raised for errors when calling external APIs."""
    def __init__(self, message: str, api_name: str = None, status_code: int = None):
        self.api_name = api_name
        self.status_code = status_code
        super().__init__(f"[ExternalAPI:{api_name}] {message}" + (f" Status: {status_code}" if status_code else ""))

class ConfigurationException(StockScreenerException):
    """Exception raised for configuration errors."""
    def __init__(self, message: str, config_key: str = None):
        self.config_key = config_key
        super().__init__(f"[Configuration] {message}" + (f" Key: {config_key}" if config_key else ""))