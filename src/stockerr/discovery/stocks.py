"""Buffett-style stock value screener.

Ranks the companies in a Screener.in screen CSV by a blend of quality
(fundamentals), valuation (margin of safety), and — optionally, for the
shortlist — technicals. Output is ranked ideas + rationale + a labeled value
estimate. NOT advice; see DISCOVERY_DISCLAIMER.

Two-tier by design: quality+valuation are computed offline for every row (no
network), then technicals (yfinance) are added only for the top N — matching the
research finding that per-stock price pulls must be throttled.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from ..scoring.fundamental import load_fundamentals, score_fundamental
from ..scoring.models import SubScore
from .universe import classify_with_lookup
from .valuation import graham_number, margin_of_safety, score_valuation

log = logging.getLogger("stockerr.discovery.stocks")

WEIGHTS = {"quality": 0.45, "valuation": 0.35, "technical": 0.20, "consistency": 0.20}

COLUMNS = ["symbol", "name", "cap", "confidence", "signal",
           "quality", "valuation", "technical", "consistency", "mos_pct", "rationale"]


def signal(score: Optional[float]) -> str:
    if score is None or pd.isna(score):
        return "N/A"
    if score > 75:
        return "Strong Buy"
    if score >= 50:
        return "Watch"
    return "Avoid"


def _combine(subs: dict[str, SubScore]) -> tuple[Optional[float], list[str]]:
    available = {k: v for k, v in subs.items() if v is not None and v.available}
    if not available:
        return None, list(subs)
    weight_sum = sum(WEIGHTS[k] for k in available)
    score = sum(subs[k].score * WEIGHTS[k] for k in available) / weight_sum
    missing = [k for k in subs if k not in available]
    return score, missing


def _rationale(metrics: dict, quality: SubScore, valuation: SubScore,
               mos: Optional[float]) -> str:
    bits = []
    if metrics.get("roe") is not None:
        bits.append(f"ROE {metrics['roe']:.0f}%")
    if metrics.get("roce") is not None:
        bits.append(f"ROCE {metrics['roce']:.0f}%")
    if metrics.get("de") is not None:
        bits.append(f"D/E {metrics['de']:.2f}")
    if metrics.get("pe") is not None:
        bits.append(f"PE {metrics['pe']:.0f}")
    if mos is not None:
        bits.append(f"MoS {mos:+.0f}%")
    if metrics.get("profit_growth") is not None:
        bits.append(f"profit growth {metrics['profit_growth']:.0f}%")
    notes = [n for n in (quality.note, valuation.note) if n]
    tail = f" ({'; '.join(notes)})" if notes else ""
    return ", ".join(bits) + tail if bits else "insufficient data"


def _score_row(symbol: str, metrics: dict, technical: Optional[SubScore],
               consistency: Optional[SubScore] = None,
               cap_lookup: Optional[dict] = None) -> dict:
    quality = score_fundamental(metrics)
    valuation = score_valuation(metrics)
    confidence, _missing = _combine(
        {"quality": quality, "valuation": valuation,
         "technical": technical, "consistency": consistency})

    # Data-completeness guard: thin data must not over-rank. Count how many of the
    # 5 quality metrics + valuation are actually present (out of 6) and scale down.
    quality_present = sum(1 for k in ("de", "roe", "roce", "fcf", "pe")
                          if metrics.get(k) is not None)
    signals = quality_present + (1 if valuation.available else 0)
    factor = 1.0 if signals >= 5 else (0.85 if signals >= 3 else 0.5)
    if confidence is not None:
        confidence *= factor

    mos = margin_of_safety(graham_number(metrics.get("eps"), metrics.get("bvps")),
                           metrics.get("price"))
    sig = signal(confidence)
    # Without a valuation you can't call something a value "Strong Buy".
    if sig == "Strong Buy" and not valuation.available:
        sig = "Watch"
    # Too few inputs to judge -> say so, don't imply a verdict.
    if signals < 3:
        sig = "Insufficient"

    name = metrics.get("name", symbol)
    return {
        "symbol": symbol,
        "name": name,
        "cap": classify_with_lookup(symbol, name, metrics.get("mcap"), cap_lookup),
        "confidence": round(confidence, 1) if confidence is not None else None,
        "signal": sig,
        "quality": round(quality.score, 0) if quality.available else None,
        "valuation": round(valuation.score, 0) if valuation.available else None,
        "technical": round(technical.score, 0) if (technical and technical.available) else None,
        "consistency": (round(consistency.score, 0)
                        if (consistency and consistency.available) else None),
        "mos_pct": round(mos, 1) if mos is not None else None,
        "rationale": _rationale(metrics, quality, valuation, mos),
    }


def screen_stocks(csv_paths: list, *, enrich_technical: bool = False,
                  top_n: int = 20, cap_lookup: Optional[dict] = None) -> pd.DataFrame:
    """Rank a Screener CSV universe. Set enrich_technical to add yfinance
    technicals for the top `top_n` rows (network; throttled to the shortlist).
    `cap_lookup` is an optional AMFI {name/symbol: tier} map for exact cap tags."""
    fundamentals = load_fundamentals(csv_paths)
    if not fundamentals:
        return pd.DataFrame(columns=COLUMNS)

    rows = [_score_row(sym, m, None, cap_lookup=cap_lookup)
            for sym, m in fundamentals.items()]
    df = pd.DataFrame(rows, columns=COLUMNS)
    df = df.sort_values("confidence", ascending=False, na_position="last").reset_index(drop=True)

    if enrich_technical and not df.empty:
        from ..scoring.technical import score_technical, to_yf_ticker  # lazy: optional yfinance
        from .consistency import compute_consistency, fetch_annual_fundamentals
        for i in df.head(top_n).index:
            sym = df.at[i, "symbol"]
            tech = cons = None
            try:
                tech = score_technical(sym)
            except Exception as exc:  # noqa: BLE001 - one symbol must not kill the run
                log.warning("Technical enrich failed for %s: %s", sym, exc)
            try:
                annual = fetch_annual_fundamentals(to_yf_ticker(sym))
                if annual:
                    cons = compute_consistency(**annual)
            except Exception as exc:  # noqa: BLE001
                log.warning("Consistency enrich failed for %s: %s", sym, exc)
            enriched = _score_row(sym, fundamentals[sym], tech,
                                  consistency=cons, cap_lookup=cap_lookup)
            for col in COLUMNS:
                df.at[i, col] = enriched[col]
        df = df.sort_values("confidence", ascending=False, na_position="last").reset_index(drop=True)

    return df
