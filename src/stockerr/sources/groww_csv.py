"""Groww holdings from an exported CSV (stocks and/or mutual funds).

The v1 Groww route: free, uses no order-capable API key, and is the only way to
include mutual funds (the paid Trading API omits them). Groww's export column
names vary, so this parser auto-detects columns and fails with a clear, helpful
message rather than silently mis-reading money.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from ..models import CATEGORY_MF, CATEGORY_STOCK, Holding
from .base import Source

log = logging.getLogger("stockerr.groww_csv")


class GrowwCsvError(ValueError):
    """Raised when a CSV can't be mapped to holdings."""


# Candidate header names (normalized: lowercased, non-alnum stripped to spaces).
_NAME_COLS = ["stock name", "company name", "company", "scheme name", "instrument", "name"]
_SYMBOL_COLS = ["symbol", "nse symbol", "trading symbol", "ticker", "isin"]
_QTY_COLS = ["quantity", "qty", "shares", "units", "net quantity", "holding quantity"]
_LTP_COLS = ["current price", "ltp", "market price", "last price", "nav", "current nav", "price"]
_VALUE_COLS = ["current value", "market value", "current amount", "present value", "value"]
_AVG_COLS = ["average price", "avg price", "buy average", "average cost", "avg cost"]
_MF_HINTS = ["nav", "units", "scheme", "folio"]


def _norm(col: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(col).lower()).strip()


def _find_col(columns: list[str], candidates: list[str]) -> str | None:
    norm_map = {_norm(c): c for c in columns}
    # exact normalized match first
    for cand in candidates:
        if cand in norm_map:
            return norm_map[cand]
    # then substring containment
    for cand in candidates:
        for norm, original in norm_map.items():
            if cand in norm:
                return original
    return None


def _to_number(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = re.sub(r"[^0-9.\-]", "", str(val))  # strip Rs, commas, %, spaces
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV, tolerating a junk preamble row above the real header."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if _find_col(list(df.columns), _NAME_COLS) is None:
        # Some Groww exports prepend a title line; retry skipping the first row.
        try:
            alt = pd.read_csv(path, dtype=str, keep_default_na=False, skiprows=1)
            if _find_col(list(alt.columns), _NAME_COLS) is not None:
                return alt
        except Exception:
            pass
    return df


def parse_groww_csv(path: str | Path) -> list[Holding]:
    path = Path(path)
    if not path.exists():
        raise GrowwCsvError(f"Groww CSV not found: {path}")

    df = _read_csv(path)
    cols = list(df.columns)

    name_col = _find_col(cols, _NAME_COLS)
    qty_col = _find_col(cols, _QTY_COLS)
    ltp_col = _find_col(cols, _LTP_COLS)
    value_col = _find_col(cols, _VALUE_COLS)
    avg_col = _find_col(cols, _AVG_COLS)
    symbol_col = _find_col(cols, _SYMBOL_COLS)

    if name_col is None or qty_col is None or (ltp_col is None and value_col is None):
        raise GrowwCsvError(
            f"Could not map required columns in {path.name}.\n"
            f"  Found columns: {cols}\n"
            f"  Need: a name column ({_NAME_COLS}), a quantity column ({_QTY_COLS}), "
            f"and a price ({_LTP_COLS}) or value ({_VALUE_COLS}) column.\n"
            f"  Tip: open the file, confirm the header row, and re-export the FULL "
            f"holdings from Groww if columns are missing."
        )

    # File is treated as mutual funds if it clearly carries MF-style columns.
    is_mf = any(_find_col(cols, [hint]) for hint in _MF_HINTS) and ltp_col and _norm(ltp_col) in ("nav", "current nav")
    category = CATEGORY_MF if is_mf else CATEGORY_STOCK

    holdings: list[Holding] = []
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        if not name:
            continue
        qty = _to_number(row[qty_col])
        if not qty:
            continue

        price = _to_number(row[ltp_col]) if ltp_col else None
        if price is None and value_col:
            val = _to_number(row[value_col])
            price = (val / qty) if (val and qty) else None
        if price is None and avg_col:
            price = _to_number(row[avg_col])
        if price is None:
            log.warning("No price for '%s' in %s; valued at 0.", name, path.name)
            price = 0.0

        symbol = str(row[symbol_col]).strip() if symbol_col else name
        holdings.append(
            Holding(
                asset=name,
                symbol=symbol or name,
                category=category,
                quantity=qty,
                price_native=price,
                currency="INR",
                source="groww_csv",
            )
        )

    log.info("Groww CSV %s: %d %s holdings.", path.name, len(holdings), category)
    return holdings


class GrowwCsvSource(Source):
    name = "groww_csv"

    def __init__(self, paths: list[str | Path]):
        if not paths:
            raise ValueError("No Groww CSV paths configured (set STOCKERR_GROWW_CSV).")
        self.paths = [Path(p) for p in paths]

    def fetch_holdings(self) -> list[Holding]:
        holdings: list[Holding] = []
        for p in self.paths:
            holdings.extend(parse_groww_csv(p))
        return holdings
