from typing import Any, Optional
from .base import CacheProvider
from .memory import MemoryCacheProvider


class CacheManager:
    """Manages the active CacheProvider, routing cache checks dynamically."""

    def __init__(self, provider: CacheProvider = None):
        self.provider = provider or MemoryCacheProvider()

    def get(self, key: str) -> Optional[Any]:
        return self.provider.get(key)

    def set(self, key: str, value: Any, timeout: int = 3600):
        self.provider.set(key, value, timeout)

    def delete(self, key: str):
        self.provider.delete(key)

    def delete_pattern(self, pattern: str):
        self.provider.delete_pattern(pattern)


# Singleton cache manager instance
cache_manager = CacheManager()
