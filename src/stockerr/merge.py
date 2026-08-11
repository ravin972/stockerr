"""Merge heterogeneous holdings into one INR-denominated view + allocation."""

from __future__ import annotations

import logging

import pandas as pd

from .fx import FxRate
from .models import CANONICAL_COLUMNS, Holding

log = logging.getLogger("stockerr.merge")


def build_dataframe(holdings: list[Holding], fx: FxRate) -> pd.DataFrame:
    """Return a DataFrame with CANONICAL_COLUMNS, prices/values converted to INR.

    Only USD is FX-converted (INR passes through 1:1). Unknown currencies are
    logged and treated as INR to avoid silently zeroing a value.
    """
    fx_map = {"INR": 1.0, "USD": fx.rate}

    rows = []
    for h in holdings:
        factor = fx_map.get(h.currency)
        if factor is None:
            log.warning("Unknown currency %s for %s; treating as INR.", h.currency, h.asset)
            factor = 1.0
        price_inr = (h.price_native or 0.0) * factor
        value_inr = (h.quantity or 0.0) * price_inr
        rows.append({
            "asset": h.asset,
            "symbol": h.symbol or h.asset,
            "category": h.category,
            "quantity": h.quantity,
            "price_native": h.price_native,
            "currency": h.currency,
            "price_inr": round(price_inr, 4),
            "value_inr": round(value_inr, 2),
            "source": h.source,
        })

    df = pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
    if df.empty:
        return df

    total = df["value_inr"].sum()
    df["alloc_pct"] = (df["value_inr"] / total * 100).round(2) if total else 0.0
    return df.sort_values("value_inr", ascending=False).reset_index(drop=True)


def allocation_by_category(df: pd.DataFrame) -> pd.DataFrame:
    """Roll holdings up to category totals + allocation %."""
    if df.empty:
        return pd.DataFrame(columns=["category", "value_inr", "alloc_pct"])
    total = df["value_inr"].sum()
    roll = (
        df.groupby("category")["value_inr"].sum().sort_values(ascending=False)
        .rename("value_inr").reset_index()
    )
    roll["alloc_pct"] = (roll["value_inr"] / total * 100).round(2) if total else 0.0
    return roll


def total_net_worth(df: pd.DataFrame) -> float:
    return float(df["value_inr"].sum()) if not df.empty else 0.0
