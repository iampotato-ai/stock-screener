import time
from typing import Any, Optional, Dict, Tuple
from .base import CacheProvider


class MemoryCacheProvider(CacheProvider):
    """Simple in-memory CacheProvider implementation supporting expiration timeout."""

    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        value, expires_at = self._cache[key]
        if time.time() > expires_at:
            self.delete(key)
            return None
        return value

    def set(self, key: str, value: Any, timeout: int = 3600):
        self._cache[key] = (value, time.time() + timeout)

    def delete(self, key: str):
        self._cache.pop(key, None)

    def delete_pattern(self, pattern: str):
        keys_to_del = [k for k in self._cache.keys() if k.startswith(pattern)]
        for k in keys_to_del:
            self._cache.pop(k, None)
