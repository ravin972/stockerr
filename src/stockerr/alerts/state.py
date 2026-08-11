"""Persist a portfolio snapshot so the next run can diff against it."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

log = logging.getLogger("stockerr.alerts.state")

SNAPSHOT_FILE = "last-snapshot.json"


def build_snapshot(df: pd.DataFrame, cat_df: pd.DataFrame,
                   generated_at: datetime) -> dict:
    total = float(df["value_inr"].sum()) if not df.empty else 0.0
    categories = {
        str(r["category"]): {
            "value_inr": float(r["value_inr"]),
            "alloc_pct": float(r["alloc_pct"]),
        }
        for _, r in cat_df.iterrows()
    } if not cat_df.empty else {}
    assets = {}
    if not df.empty:
        for _, r in df.iterrows():
            assets[str(r["symbol"])] = {
                "asset": str(r["asset"]),
                "category": str(r["category"]),
                "quantity": float(r["quantity"]),
                "price_inr": float(r["price_inr"]),
                "value_inr": float(r["value_inr"]),
            }
    return {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "total_inr": round(total, 2),
        "categories": categories,
        "assets": assets,
    }


def load_last_snapshot(state_dir: Path) -> Optional[dict]:
    path = state_dir / SNAPSHOT_FILE
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read previous snapshot: %s", exc)
        return None


def save_snapshot(state_dir: Path, snapshot: dict) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / SNAPSHOT_FILE
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return path
