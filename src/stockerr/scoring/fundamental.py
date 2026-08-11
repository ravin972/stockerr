"""Fundamental sub-score (50%) from Screener.in-style fundamentals CSV.

Checks (each graded 0-25, not binary; the score is renormalized over the checks
actually present):
  - Debt-to-Equity < 1        (lower is safer)
  - ROE  > 15%                (efficient use of equity)
  - ROCE > 15%                (efficient use of capital)
  - Free Cash Flow positive   (real cash generation)
  - PE ratio reasonable       (not richly priced; loss-making PE<=0 scores 0)

Provide a CSV (Screener export or your own) with one row per company and columns
for symbol/name + these metrics. Column names are auto-detected. Any missing
metric is skipped and the score is renormalized over the checks present.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from .models import SubScore, clamp

log = logging.getLogger("stockerr.scoring.fundamental")

_SYMBOL_COLS = ["nse code", "symbol", "ticker", "bse code", "code"]
_NAME_COLS = ["name", "company", "company name", "stock name"]
_DE_COLS = ["debt to equity", "d e", "debt equity", "de ratio"]
_ROE_COLS = ["roe", "return on equity"]
_ROCE_COLS = ["roce", "return on capital employed", "return on capital"]
_FCF_COLS = ["free cash flow", "fcf", "free cash flow last year", "free cash flow 3years"]
_PE_COLS = ["price to earning", "pe ratio", "pe", "p e", "price earning"]
# Extra columns used by the discovery valuation model (all optional).
_EPS_COLS = ["eps", "earnings per share", "eps 12m", "eps ttm"]
_BV_COLS = ["book value", "bvps", "book value per share"]
_PRICE_COLS = ["current price", "cmp", "ltp", "market price", "close price", "price"]
_MCAP_COLS = ["market capitalization", "market cap", "mcap", "market capital"]
_SALESG_COLS = ["sales growth", "revenue growth", "sales growth 5years", "sales growth 3years"]
_PROFITG_COLS = ["profit growth", "net profit growth", "profit growth 5years", "profit growth 3years"]


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


def _num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = re.sub(r"[^0-9.\-]", "", str(v))
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_fundamentals(paths: list[str | Path]) -> dict[str, dict]:
    """Return {SYMBOL_UPPER: {de, roe, roce, fcf}} merged across CSVs."""
    out: dict[str, dict] = {}
    for path in paths:
        path = Path(path)
        if not path.exists():
            log.warning("Screener CSV not found: %s", path)
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        cols = list(df.columns)
        sym_col = _find(cols, _SYMBOL_COLS) or _find(cols, _NAME_COLS)
        if sym_col is None:
            log.warning("No symbol/name column in %s; skipping.", path.name)
            continue
        name_c = _find(cols, _NAME_COLS)
        de_c, roe_c, roce_c, fcf_c, pe_c = (
            _find(cols, _DE_COLS), _find(cols, _ROE_COLS),
            _find(cols, _ROCE_COLS), _find(cols, _FCF_COLS), _find(cols, _PE_COLS),
        )
        eps_c, bv_c, price_c, mcap_c, salesg_c, profitg_c = (
            _find(cols, _EPS_COLS), _find(cols, _BV_COLS), _find(cols, _PRICE_COLS),
            _find(cols, _MCAP_COLS), _find(cols, _SALESG_COLS), _find(cols, _PROFITG_COLS),
        )
        for _, row in df.iterrows():
            key = str(row[sym_col]).strip().upper()
            if not key:
                continue
            out[key] = {
                "name": str(row[name_c]).strip() if name_c else key,
                "de": _num(row[de_c]) if de_c else None,
                "roe": _num(row[roe_c]) if roe_c else None,
                "roce": _num(row[roce_c]) if roce_c else None,
                "fcf": _num(row[fcf_c]) if fcf_c else None,
                "pe": _num(row[pe_c]) if pe_c else None,
                "eps": _num(row[eps_c]) if eps_c else None,
                "bvps": _num(row[bv_c]) if bv_c else None,
                "price": _num(row[price_c]) if price_c else None,
                "mcap": _num(row[mcap_c]) if mcap_c else None,
                "sales_growth": _num(row[salesg_c]) if salesg_c else None,
                "profit_growth": _num(row[profitg_c]) if profitg_c else None,
            }
    return out


def _de_points(de):
    # 25 at D/E<=0.5, 0 at D/E>=2.0, linear between; rewards < 1.
    if de is None:
        return None
    factor = clamp((2.0 - de) / 1.5, 0.0, 1.0)
    return 25.0 * factor


def _ratio_points(v):
    # ROE/ROCE: 25 at >=25%, 0 at <=0%, linear; 15% -> 15 pts.
    if v is None:
        return None
    return 25.0 * clamp(v / 25.0, 0.0, 1.0)


def _fcf_points(fcf):
    if fcf is None:
        return None
    if fcf > 0:
        return 25.0
    if fcf == 0:
        return 12.5
    return 0.0


def _pe_points(pe):
    # Full marks for a reasonable PE (<=15), taper to 0 by PE 50; loss-making PE<=0 -> 0.
    if pe is None:
        return None
    if pe <= 0:
        return 0.0
    if pe <= 15:
        return 25.0
    if pe <= 30:
        return 25.0 - (pe - 15) / 15.0 * 12.5
    if pe <= 50:
        return 12.5 - (pe - 30) / 20.0 * 12.5
    return 0.0


def score_fundamental(metrics: dict | None) -> SubScore:
    if not metrics:
        return SubScore.unavailable("fundamental", "no fundamentals found for symbol")

    parts = {
        "debt_to_equity": (_de_points(metrics.get("de")), metrics.get("de")),
        "roe": (_ratio_points(metrics.get("roe")), metrics.get("roe")),
        "roce": (_ratio_points(metrics.get("roce")), metrics.get("roce")),
        "free_cash_flow": (_fcf_points(metrics.get("fcf")), metrics.get("fcf")),
        "pe_ratio": (_pe_points(metrics.get("pe")), metrics.get("pe")),
    }
    present = {k: v for k, v in parts.items() if v[0] is not None}
    if not present:
        return SubScore.unavailable("fundamental", "no usable fundamental metrics")

    earned = sum(v[0] for v in present.values())
    possible = 25.0 * len(present)
    score = clamp(earned / possible * 100.0)
    detail = {k: {"value": v[1], "points": round(v[0], 1)} for k, v in present.items()}
    total = len(parts)
    note = "" if len(present) == total else f"only {len(present)}/{total} metrics available"
    return SubScore("fundamental", True, score, detail, note)
