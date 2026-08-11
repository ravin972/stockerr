"""Canonical data model shared by every source, the merger, and the reporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Category constants -----------------------------------------------------------
CATEGORY_STOCK = "stock"
CATEGORY_MF = "mf"
CATEGORY_CRYPTO = "crypto"

# The one schema every source normalizes into before merging.
CANONICAL_COLUMNS = [
    "asset",          # display name / ticker
    "symbol",         # normalized symbol used for lookups (e.g. NSE ticker, BTC)
    "category",       # one of CATEGORY_* above
    "quantity",       # units held
    "price_native",   # price per unit in `currency`
    "currency",       # "INR" for stocks/MF, "USD" for crypto (USDT ~ USD)
    "price_inr",      # price per unit converted to INR (filled by merge)
    "value_inr",      # quantity * price_inr (filled by merge)
    "source",         # "binance" | "groww_csv" | "groww_api" | ...
]


@dataclass
class Holding:
    """One position from one source, in its native currency.

    `price_inr` / `value_inr` are filled in later by the merge step once the FX
    rate is known, so they default to None here.
    """

    asset: str
    category: str
    quantity: float
    price_native: float
    currency: str
    source: str
    symbol: Optional[str] = None
    price_inr: Optional[float] = None
    value_inr: Optional[float] = None

    def __post_init__(self) -> None:
        if self.symbol is None:
            self.symbol = self.asset


@dataclass
class SourceResult:
    """Outcome of trying to fetch one source, so a partial run can be reported honestly."""

    source: str
    ok: bool
    holdings: list[Holding] = field(default_factory=list)
    error: Optional[str] = None
