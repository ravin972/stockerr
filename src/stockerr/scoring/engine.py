"""Combine the three sub-scores into a ranked confidence table."""

from __future__ import annotations

import logging
from typing import Iterable, Optional

import pandas as pd

from ..config import Config
from . import W_FUNDAMENTAL, W_SENTIMENT, W_TECHNICAL
from .fundamental import load_fundamentals, score_fundamental
from .models import StockScore, SubScore
from .sentiment import score_sentiment
from .technical import score_technical

log = logging.getLogger("stockerr.scoring.engine")

_WEIGHTS = {
    "fundamental": W_FUNDAMENTAL,
    "technical": W_TECHNICAL,
    "sentiment": W_SENTIMENT,
}


def combine(fundamental: SubScore, technical: SubScore,
            sentiment: SubScore) -> tuple[Optional[float], str]:
    """Weighted blend, renormalizing over whichever sub-scores are available."""
    subs = {"fundamental": fundamental, "technical": technical, "sentiment": sentiment}
    available = {k: v for k, v in subs.items() if v.available}
    if not available:
        return None, "no sub-scores available"

    weight_sum = sum(_WEIGHTS[k] for k in available)
    confidence = sum(subs[k].score * _WEIGHTS[k] for k in available) / weight_sum

    missing = [k for k in subs if not subs[k].available]
    note = "" if not missing else "reweighted; missing " + ", ".join(missing)
    return confidence, note


def build_rationale(metrics: Optional[dict], fundamental: SubScore,
                    technical: SubScore, sentiment: SubScore) -> str:
    """Plain-English 'why' behind the score, drawn from the sub-score evidence.

    Explains the drivers (trend, valuation, debt, news) — it is NOT a claim that
    the stock will be profitable.
    """
    m = metrics or {}
    bits: list[str] = []

    if technical.available:
        d = technical.detail
        price, e50, e200 = d.get("price"), d.get("ema50"), d.get("ema200")
        if price is not None and e50 is not None and e200 is not None:
            if price > e50 and price > e200:
                bits.append("uptrend (price above 50 & 200-day avg)")
            elif price < e50 and price < e200:
                bits.append("downtrend (below 50 & 200-day avg)")
            else:
                bits.append("mixed trend")
        rsi = d.get("rsi")
        if rsi is not None and rsi >= 70:
            bits.append(f"RSI {rsi:.0f} (overbought)")
        elif rsi is not None and rsi <= 30:
            bits.append(f"RSI {rsi:.0f} (oversold)")

    if m.get("de") is not None:
        bits.append(f"{'low' if m['de'] < 1 else 'high'} debt (D/E {m['de']:.2f})")
    if m.get("roe") is not None:
        bits.append(f"ROE {m['roe']:.0f}%")
    if m.get("pe") is not None:
        pe = m["pe"]
        tag = "cheap" if pe <= 15 else ("fair" if pe <= 30 else "pricey")
        bits.append(f"PE {pe:.0f} ({tag})")
    if m.get("eps") is not None and m["eps"] < 0:
        bits.append("loss-making (negative EPS)")

    if sentiment.available and sentiment.detail.get("rationale"):
        bits.append(f"news: {sentiment.detail['rationale']}")

    missing = []
    if not fundamental.available:
        missing.append("fundamentals")
    if not sentiment.available:
        missing.append("sentiment")
    tail = f" [no {', '.join(missing)} data]" if missing else ""
    return ("; ".join(bits) + tail) if bits else "insufficient data to explain"


def score_one(symbol: str, name: Optional[str], fundamentals: dict) -> StockScore:
    key = (symbol or "").strip().upper()
    metrics = fundamentals.get(key)
    if metrics is None and name:
        metrics = fundamentals.get(name.strip().upper())

    fundamental = score_fundamental(metrics)
    try:
        technical = score_technical(symbol)
    except Exception as exc:  # noqa: BLE001
        technical = SubScore.unavailable("technical", f"error: {exc}")
    try:
        sentiment = score_sentiment(symbol, name)
    except Exception as exc:  # noqa: BLE001
        sentiment = SubScore.unavailable("sentiment", f"error: {exc}")

    confidence, note = combine(fundamental, technical, sentiment)
    rationale = build_rationale(metrics, fundamental, technical, sentiment)
    return StockScore(symbol, confidence, fundamental, technical, sentiment, note, rationale)


def score_stocks(items: Iterable[tuple[str, Optional[str]]], cfg: Config) -> list[StockScore]:
    """Score (symbol, name) pairs. Fundamentals are loaded once from the config."""
    fundamentals = load_fundamentals(cfg.screener_csv_paths) if cfg.screener_csv_paths else {}

    seen: set[str] = set()
    scores: list[StockScore] = []
    for symbol, name in items:
        sym = (symbol or "").strip()
        if not sym or sym.upper() in seen:
            continue
        seen.add(sym.upper())
        log.info("Scoring %s ...", sym)
        try:
            scores.append(score_one(sym, name, fundamentals))
        except Exception as exc:  # noqa: BLE001 - never let one symbol kill the batch
            log.warning("Scoring failed for %s: %s", sym, exc)

    # Rank by confidence desc; unscored (None) sink to the bottom.
    scores.sort(key=lambda s: (s.confidence is not None, s.confidence or 0), reverse=True)
    return scores


def to_dataframe(scores: list[StockScore]) -> pd.DataFrame:
    cols = ["symbol", "confidence", "fundamental", "technical", "sentiment", "why", "notes"]
    if not scores:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame([s.to_row() for s in scores], columns=cols)
