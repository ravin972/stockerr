"""Stage-2 multi-year consistency sub-score (the Buffett "over time" test).

From ~3-4 years of annual financials (yfinance's free cap), rewards: ROE
consistently >15%, rising revenue and earnings, and an unbroken positive-FCF
streak. `compute_consistency` is pure (unit-tested); `fetch_annual_fundamentals`
is a guarded yfinance layer. Only run on the enriched shortlist — labeled 3-4yr,
since true 10-yr history needs a Screener per-company export.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..scoring.models import SubScore, clamp

log = logging.getLogger("stockerr.discovery.consistency")


def _cagr(series: list[float]) -> Optional[float]:
    """CAGR % from an oldest->newest list."""
    if not series or len(series) < 2 or series[0] <= 0:
        return None
    n = len(series) - 1
    return ((series[-1] / series[0]) ** (1 / n) - 1) * 100.0


def compute_consistency(net_income: Optional[list] = None,
                        revenue: Optional[list] = None,
                        equity: Optional[list] = None,
                        fcf: Optional[list] = None) -> SubScore:
    """Each input is a list oldest->newest (or None). Score renormalizes over what's present."""
    comps: dict[str, tuple[float, float]] = {}

    if net_income and equity and len(net_income) == len(equity):
        roes = [ni / eq * 100.0 for ni, eq in zip(net_income, equity) if eq and eq > 0]
        if roes:
            frac = sum(1 for r in roes if r >= 15) / len(roes)
            comps["roe_consistency"] = (25.0 * frac, 25.0)
    if revenue:
        g = _cagr(revenue)
        if g is not None:
            comps["revenue_growth"] = (25.0 * clamp(g / 15.0, 0.0, 1.0), 25.0)
    if net_income:
        g = _cagr(net_income)
        if g is not None:
            comps["earnings_growth"] = (25.0 * clamp(g / 15.0, 0.0, 1.0), 25.0)
    if fcf:
        vals = [f for f in fcf if f is not None]
        if vals:
            frac = sum(1 for f in vals if f > 0) / len(vals)
            comps["fcf_streak"] = (25.0 * frac, 25.0)

    if not comps:
        return SubScore.unavailable("consistency", "no multi-year data")
    earned = sum(p for p, _ in comps.values())
    possible = sum(q for _, q in comps.values())
    detail = {k: round(v[0], 1) for k, v in comps.items()}
    return SubScore("consistency", True, clamp(earned / possible * 100.0),
                    detail, "3-4yr (yfinance)")


def _extract(df, *names) -> Optional[list]:
    """Find a row by fuzzy name in a yfinance statement frame -> oldest->newest list."""
    if df is None or getattr(df, "empty", True):
        return None
    import pandas as pd
    for name in names:
        for idx in df.index:
            if name.lower() in str(idx).lower():
                vals = [float(x) for x in df.loc[idx].values if pd.notna(x)]
                return list(reversed(vals))  # yfinance columns are newest-first
    return None


def fetch_annual_fundamentals(ticker: str) -> Optional[dict]:
    """Best-effort annual financials from yfinance. None on any failure."""
    try:
        import yfinance as yf
    except Exception:
        log.warning("yfinance not installed; skipping consistency.")
        return None
    try:
        t = yf.Ticker(ticker)
        inc, bs, cf = t.income_stmt, t.balance_sheet, t.cashflow
    except Exception as exc:  # noqa: BLE001
        log.warning("yfinance financials failed for %s: %s", ticker, exc)
        return None

    net_income = _extract(inc, "Net Income")
    revenue = _extract(inc, "Total Revenue", "Operating Revenue")
    equity = _extract(bs, "Stockholders Equity", "Total Stockholder Equity")
    fcf = _extract(cf, "Free Cash Flow")
    if fcf is None:  # derive FCF = Operating Cash Flow - CapEx
        ocf = _extract(cf, "Operating Cash Flow", "Total Cash From Operating")
        capex = _extract(cf, "Capital Expenditure")
        if ocf and capex and len(ocf) == len(capex):
            fcf = [o + c for o, c in zip(ocf, capex)]   # capex is negative
    if not any([net_income, revenue, equity, fcf]):
        return None
    return {"net_income": net_income, "revenue": revenue, "equity": equity, "fcf": fcf}
