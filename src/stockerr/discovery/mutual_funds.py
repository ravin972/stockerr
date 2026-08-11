"""Mutual-fund screener (Groww investor).

Ranks funds by CONSISTENCY and RISK-ADJUSTED return computed from free NAV
history — deliberately not naive past-return chasing. Metrics are pure functions
(unit-tested from a synthetic NAV series); `fetch_nav` is a graceful layer over
the free `api.mfapi.in`.

Score = rolling-return consistency (30%) + risk-adjusted Sortino/Sharpe (30%) +
downside protection / max drawdown (25%) + low expense ratio (15%), renormalized
over whichever inputs are present. Rank Direct plans within the same category.
"""

from __future__ import annotations

import logging
import math
import statistics
from typing import Optional

import pandas as pd

from .. import net

log = logging.getLogger("stockerr.discovery.mutual_funds")

MF_DISCLAIMER = (
    "Ratings are backward-looking and computed from NAV history — NOT advice or a "
    "guarantee of future returns. Rank Direct plans within the same category; watch "
    "for manager/mandate changes. Expense ratio & AUM (when shown) are best-effort."
)

MFAPI_URL = "https://api.mfapi.in/mf/{code}"


def to_series(records: list[dict]) -> pd.Series:
    """NAV records [{date:'dd-mm-YYYY', nav:'123.45'}, ...] -> chronological Series."""
    if not records:
        return pd.Series(dtype=float)
    df = pd.DataFrame(records)
    dates = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    navs = pd.to_numeric(df["nav"], errors="coerce")
    s = pd.Series(navs.values, index=dates).dropna()
    s = s[~s.index.isna()].sort_index()
    # Drop non-positive NAVs — mfapi history occasionally carries a spurious 0,
    # which otherwise yields a bogus -100% drawdown and an infinite Sortino.
    return s[s > 0]


def _ppy(s: pd.Series) -> float:
    days = (s.index[-1] - s.index[0]).days
    return len(s) / (days / 365.25) if days > 0 else 252.0


def cagr(start: float, end: float, years: float) -> Optional[float]:
    if start <= 0 or years <= 0:
        return None
    return ((end / start) ** (1 / years) - 1) * 100.0


def trailing_cagr(s: pd.Series, years: int) -> Optional[float]:
    if len(s) < 2:
        return None
    target = s.index[-1] - pd.DateOffset(years=years)
    past = s[s.index <= target]
    if past.empty:
        return None
    return cagr(float(past.iloc[-1]), float(s.iloc[-1]), years)


def rolling_returns(s: pd.Series, years: int) -> Optional[dict]:
    """Median and % positive across all `years`-length windows (consistency)."""
    if len(s) < 2:
        return None
    out = []
    for d, v in s.items():
        fut = s[s.index >= d + pd.DateOffset(years=years)]
        if fut.empty:
            continue
        r = cagr(float(v), float(fut.iloc[0]), years)
        if r is not None:
            out.append(r)
    if not out:
        return None
    return {
        "median": statistics.median(out),
        "pct_positive": sum(1 for r in out if r > 0) / len(out) * 100.0,
        "count": len(out),
    }


def max_drawdown(s: pd.Series) -> Optional[float]:
    if len(s) < 2:
        return None
    peak = s.cummax()
    return float((s / peak - 1.0).min()) * 100.0   # negative %


def sharpe_sortino(s: pd.Series, rf: float = 6.0) -> tuple[Optional[float], Optional[float], Optional[float]]:
    rets = s.pct_change().dropna()
    if len(rets) < 3:
        return None, None, None
    ppy = _ppy(s)
    ann_ret = rets.mean() * ppy
    ann_vol = rets.std() * math.sqrt(ppy)
    downside = rets[rets < 0]
    dd_vol = downside.std() * math.sqrt(ppy) if len(downside) > 1 else None
    rf_frac = rf / 100.0
    sharpe = (ann_ret - rf_frac) / ann_vol if ann_vol and ann_vol > 0 else None
    sortino = (ann_ret - rf_frac) / dd_vol if dd_vol and dd_vol > 0 else None
    # Never surface non-finite ratios (degenerate/near-zero downside).
    if sharpe is not None and not math.isfinite(sharpe):
        sharpe = None
    if sortino is not None and not math.isfinite(sortino):
        sortino = None
    return sharpe, sortino, (ann_vol * 100.0 if ann_vol else None)


def fund_metrics(s: pd.Series, rf: float = 6.0) -> dict:
    sharpe, sortino, vol = sharpe_sortino(s, rf)
    r3 = rolling_returns(s, 3)
    return {
        "cagr_1y": trailing_cagr(s, 1),
        "cagr_3y": trailing_cagr(s, 3),
        "cagr_5y": trailing_cagr(s, 5),
        "roll3_median": r3["median"] if r3 else None,
        "roll3_pct_pos": r3["pct_positive"] if r3 else None,
        "volatility": vol,
        "max_drawdown": max_drawdown(s),
        "sharpe": sharpe,
        "sortino": sortino,
    }


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_fund(metrics: dict, expense_ratio: Optional[float] = None) -> Optional[float]:
    """0-100 blend, renormalized over available components."""
    comps: dict[str, tuple[float, float]] = {}   # name -> (value 0-1, weight)

    if metrics.get("roll3_pct_pos") is not None:
        comps["consistency"] = (_clamp(metrics["roll3_pct_pos"] / 100.0), 0.30)
    ra = metrics.get("sortino")
    if ra is None:
        ra = metrics.get("sharpe")
    if ra is not None:
        comps["risk_adjusted"] = (_clamp(ra / 2.0), 0.30)   # ratio of 2 -> full
    if metrics.get("max_drawdown") is not None:
        comps["downside"] = (1.0 - _clamp(abs(metrics["max_drawdown"]) / 50.0), 0.25)
    if expense_ratio is not None:
        comps["cost"] = (1.0 - _clamp(expense_ratio / 2.0), 0.15)

    if not comps:
        return None
    wsum = sum(w for _, w in comps.values())
    score = sum(v * w for v, w in comps.values()) / wsum
    return round(score * 100.0, 1)


def screen_funds(funds: list[dict], rf: float = 6.0) -> pd.DataFrame:
    """funds: [{code, name, category, expense_ratio, series(pd.Series) or records}]."""
    rows = []
    for f in funds:
        s = f.get("series")
        if s is None and f.get("records"):
            s = to_series(f["records"])
        if s is None or len(s) < 2:
            continue
        m = fund_metrics(s, rf)
        rows.append({
            "code": f.get("code"),
            "name": f.get("name", f.get("code")),
            "category": f.get("category", ""),
            "score": score_fund(m, f.get("expense_ratio")),
            "cagr_3y": round(m["cagr_3y"], 1) if m["cagr_3y"] is not None else None,
            "cagr_5y": round(m["cagr_5y"], 1) if m["cagr_5y"] is not None else None,
            "roll3_pos_pct": round(m["roll3_pct_pos"], 0) if m["roll3_pct_pos"] is not None else None,
            "sortino": round(m["sortino"], 2) if m["sortino"] is not None else None,
            "max_dd": round(m["max_drawdown"], 1) if m["max_drawdown"] is not None else None,
            "ter": f.get("expense_ratio"),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)


def fetch_nav(code: str, timeout: int = 20) -> tuple[list[dict], dict]:
    """Fetch NAV history + meta for a scheme code from api.mfapi.in. ([], {}) on failure."""
    try:
        # NAV refreshes a few times/day -> cache 6h to spare the no-SLA hobby API.
        data = net.get_json(MFAPI_URL.format(code=code), timeout=timeout, cache_ttl=21600)
        return data.get("data", []), data.get("meta", {})
    except Exception as exc:  # noqa: BLE001
        log.warning("mfapi fetch failed for %s: %s", code, exc)
        return [], {}
