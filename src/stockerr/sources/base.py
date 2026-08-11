"""Common interface every data source implements."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Holding


class Source(ABC):
    """A read-only portfolio data source."""

    #: short id used in reports and the SourceResult, e.g. "binance".
    name: str = "source"

    @abstractmethod
    def fetch_holdings(self) -> list[Holding]:
        """Return current holdings in native currency. Raise on failure."""
        raise NotImplementedError
