"""Valuation sub-score: intrinsic value + margin of safety (Graham-style).

A transparent, conservative estimate — Benjamin Graham's fair-value number plus a
PE-reasonableness check. Every number here is an ESTIMATE, not a target or promise.
Renormalizes over whichever inputs are available, like the other sub-scores.
"""

from __future__ import annotations

from typing import Optional

from ..scoring.models import SubScore, clamp


def graham_number(eps: Optional[float], bvps: Optional[float]) -> Optional[float]:
    """Graham number = sqrt(22.5 * EPS * BookValuePerShare). Needs both > 0."""
    if eps is None or bvps is None or eps <= 0 or bvps <= 0:
        return None
    return (22.5 * eps * bvps) ** 0.5


def margin_of_safety(intrinsic: Optional[float], price: Optional[float]) -> Optional[float]:
    """Percentage the price sits below intrinsic value. Positive = undervalued."""
    if not intrinsic or not price or price <= 0:
        return None
    return (intrinsic - price) / intrinsic * 100.0


def _pe_points(pe: Optional[float]) -> Optional[float]:
    # 0-40: cheap PE (<=15) full marks; taper to 0 by ~50; loss-making PE<=0 -> 0.
    if pe is None:
        return None
    if pe <= 0:
        return 0.0
    if pe <= 15:
        return 40.0
    if pe <= 50:
        return 40.0 * (50 - pe) / 35.0
    return 0.0


def _mos_points(mos: Optional[float]) -> Optional[float]:
    # 0-60: >=30% margin of safety full marks; <=-30% (overvalued) -> 0.
    if mos is None:
        return None
    return 60.0 * clamp((mos + 30.0) / 60.0, 0.0, 1.0)


def score_valuation(metrics: dict | None) -> SubScore:
    if not metrics:
        return SubScore.unavailable("valuation", "no valuation inputs")

    eps = metrics.get("eps")
    bvps = metrics.get("bvps")
    price = metrics.get("price")
    pe = metrics.get("pe")

    intrinsic = graham_number(eps, bvps)
    mos = margin_of_safety(intrinsic, price)

    parts = {
        "margin_of_safety": (_mos_points(mos), mos),
        "pe_reasonable": (_pe_points(pe), pe),
    }
    present = {k: v for k, v in parts.items() if v[0] is not None}
    if not present:
        return SubScore.unavailable("valuation", "need EPS+book value+price or PE")

    earned = sum(v[0] for v in present.values())
    possible = sum({"margin_of_safety": 60.0, "pe_reasonable": 40.0}[k] for k in present)
    score = clamp(earned / possible * 100.0)

    detail = {k: {"value": round(v[1], 2) if v[1] is not None else None,
                  "points": round(v[0], 1)} for k, v in present.items()}
    if intrinsic is not None:
        detail["graham_fair_value"] = round(intrinsic, 2)
    note = "" if len(present) == 2 else "partial valuation inputs"
    return SubScore("valuation", True, score, detail, note)
