from abc import ABC, abstractmethod
from typing import List, Union
from ..schemas.normalized_event import NormalizedArticle, NormalizedEvent


class BaseDataProvider(ABC):
    """Abstract base class for all Market Intelligence data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name identifier of the provider."""
        pass

    @abstractmethod
    def fetch(self, symbol: str) -> List[Union[NormalizedArticle, NormalizedEvent]]:
        """
        Fetch raw data for a given symbol from the provider and return a normalized list.
        
        Args:
            symbol: Stock symbol (e.g. RELIANCE)
            
        Returns:
            List of NormalizedArticle or NormalizedEvent objects.
        """
        pass
