from typing import Any, Optional
from .base import CacheProvider


class NoCacheProvider(CacheProvider):
    """Fallback cache bypass implementation."""

    def get(self, key: str) -> Optional[Any]:
        return None

    def set(self, key: str, value: Any, timeout: int = 3600):
        pass

    def delete(self, key: str):
        pass

    def delete_pattern(self, pattern: str):
        pass
