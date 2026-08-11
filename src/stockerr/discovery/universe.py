"""Market-cap tier classification (Large / Mid / Small).

SEBI defines tiers by rank (Large = top 100, Mid = 101-250, Small = 251+), and
AMFI publishes the authoritative list twice a year. For a self-contained MVP we
classify from a stock's market cap (in Rs. crore) using AMFI's most recent
boundary values as approximate thresholds. These floors move each half-year, so
treat the tag as indicative; drop in an AMFI file later for exact ranks.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import pandas as pd

log = logging.getLogger("stockerr.discovery.universe")

# Approximate boundaries from AMFI's Jul 2026 categorization (Rs. crore).
LARGE_CAP_FLOOR_CR = 106_300.0   # >= this -> Large (roughly top 100)
MID_CAP_FLOOR_CR = 33_500.0      # >= this and < large -> Mid (101-250); below -> Small

LARGE, MID, SMALL, UNKNOWN = "Large", "Mid", "Small", "Unknown"


def classify_cap(market_cap_cr: Optional[float]) -> str:
    """Tag a market cap (in Rs. crore) as Large / Mid / Small / Unknown."""
    if market_cap_cr is None or market_cap_cr <= 0:
        return UNKNOWN
    if market_cap_cr >= LARGE_CAP_FLOOR_CR:
        return LARGE
    if market_cap_cr >= MID_CAP_FLOOR_CR:
        return MID
    return SMALL


def _norm(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(c).lower()).strip()


def _find(cols, candidates):
    m = {_norm(c): c for c in cols}
    for cand in candidates:
        if cand in m:
            return m[cand]
    for cand in candidates:
        for norm, orig in m.items():
            if cand in norm:
                return orig
    return None


def _tier_from(text: str) -> Optional[str]:
    t = str(text).lower()
    if "large" in t:
        return LARGE
    if "mid" in t:
        return MID
    if "small" in t:
        return SMALL
    return None


def load_amfi_caps(path: str | Path) -> dict[str, str]:
    """Read AMFI's official categorization (CSV/XLSX) -> {NAME/SYMBOL upper: tier}.

    Authoritative Large/Mid/Small tags. Returns {} (falls back to thresholds) if the
    file is missing/unreadable or has no recognizable categorization column.
    """
    path = Path(path)
    if not path.exists():
        return {}
    try:
        if path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(path, dtype=str)   # needs openpyxl
        else:
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("AMFI file read failed (%s): %s — using market-cap thresholds.", path, exc)
        return {}

    cols = list(df.columns)
    name_c = _find(cols, ["company name", "name of the company", "name", "company", "stock"])
    sym_c = _find(cols, ["symbol", "nse symbol", "ticker", "nse"])
    cat_c = _find(cols, ["categorization", "category", "classification", "cap"])
    if cat_c is None:  # detect a column whose values look like Large/Mid/Small
        for c in cols:
            if df[c].astype(str).str.contains("cap", case=False, na=False).any():
                cat_c = c
                break
    if cat_c is None or (name_c is None and sym_c is None):
        log.warning("AMFI file %s: no categorization/name column found.", path.name)
        return {}

    out: dict[str, str] = {}
    for _, row in df.iterrows():
        tier = _tier_from(row[cat_c])
        if not tier:
            continue
        if name_c and str(row[name_c]).strip():
            out[str(row[name_c]).strip().upper()] = tier
        if sym_c and str(row[sym_c]).strip():
            out[str(row[sym_c]).strip().upper()] = tier
    return out


def classify_with_lookup(symbol: Optional[str], name: Optional[str],
                         market_cap_cr: Optional[float],
                         amfi: Optional[dict] = None) -> str:
    """AMFI exact tier by symbol/name if available, else market-cap thresholds."""
    if amfi:
        for key in (symbol, name):
            if key and str(key).strip().upper() in amfi:
                return amfi[str(key).strip().upper()]
    return classify_cap(market_cap_cr)
