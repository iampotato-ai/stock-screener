from abc import ABC, abstractmethod
from typing import Any, Optional


class CacheProvider(ABC):
    """Abstract base class representing a cache store provider."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Retrieve key value from cache, return None if expired or not found."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, timeout: int = 3600):
        """Store key-value pair with a expiration timeout in seconds."""
        pass

    @abstractmethod
    def delete(self, key: str):
        """Remove key from cache store."""
        pass

    @abstractmethod
    def delete_pattern(self, pattern: str):
        """Remove all keys starting with pattern prefix."""
        pass
