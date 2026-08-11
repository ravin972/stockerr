"""Turn (previous snapshot, current snapshot, scores) into alert messages."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from ..config import Config


def _pct_change(old: float, new: float) -> Optional[float]:
    if old == 0:
        return None
    return (new - old) / abs(old) * 100.0


def detect_alerts(
    current: dict,
    previous: Optional[dict],
    cfg: Config,
    scores_df: Optional[pd.DataFrame] = None,
) -> list[str]:
    alerts: list[str] = []

    cur_cats = current.get("categories", {})
    cur_assets = current.get("assets", {})

    # --- Allocation drift vs a configured target -----------------------------
    for cat, target in cfg.target_allocation.items():
        cur_pct = cur_cats.get(cat, {}).get("alloc_pct", 0.0)
        if abs(cur_pct - target) >= cfg.drift_threshold_pp:
            alerts.append(
                f"Allocation: {cat} is {cur_pct:.1f}% vs target {target:.1f}% "
                f"(off by {cur_pct - target:+.1f} pts)."
            )

    if previous:
        prev_cats = previous.get("categories", {})
        prev_assets = previous.get("assets", {})

        # --- Allocation drift vs the previous run ----------------------------
        for cat, cur in cur_cats.items():
            prev_pct = prev_cats.get(cat, {}).get("alloc_pct")
            if prev_pct is None:
                continue
            move = cur["alloc_pct"] - prev_pct
            if abs(move) >= cfg.drift_threshold_pp:
                alerts.append(
                    f"Allocation drift: {cat} moved {move:+.1f} pts "
                    f"({prev_pct:.1f}% -> {cur['alloc_pct']:.1f}%) since last run."
                )

        # --- Per-asset price moves -------------------------------------------
        for sym, cur in cur_assets.items():
            prev = prev_assets.get(sym)
            if not prev:
                continue
            change = _pct_change(prev["price_inr"], cur["price_inr"])
            if change is not None and abs(change) >= cfg.price_move_threshold_pct:
                alerts.append(
                    f"Price move: {cur['asset']} {change:+.1f}% "
                    f"(Rs.{prev['price_inr']:.2f} -> Rs.{cur['price_inr']:.2f})."
                )

        # --- Net-worth swing (uses price-move threshold) ---------------------
        nw_change = _pct_change(previous.get("total_inr", 0.0), current.get("total_inr", 0.0))
        if nw_change is not None and abs(nw_change) >= cfg.price_move_threshold_pct:
            alerts.append(
                f"Net worth moved {nw_change:+.1f}% "
                f"(Rs.{previous['total_inr']:,.0f} -> Rs.{current['total_inr']:,.0f})."
            )

    # --- High-confidence stock alerts ----------------------------------------
    if cfg.score_alert_min is not None and scores_df is not None and not scores_df.empty:
        for _, row in scores_df.iterrows():
            conf = row.get("confidence")
            if conf is not None and not pd.isna(conf) and conf >= cfg.score_alert_min:
                alerts.append(
                    f"High confidence: {row['symbol']} scored {conf:.0f}/100 "
                    f"(>= {cfg.score_alert_min:.0f}). Screen only — do your own diligence."
                )

    return alerts
