"""Technical sub-score (30%) from free daily prices (yfinance).

Checks (25 each):
  - Price above 50-day EMA        (short-term uptrend)
  - Price above 200-day EMA       (long-term uptrend)
  - 50-day EMA above 200-day EMA  (golden-cross regime)
  - RSI(14) in a healthy 40-60 band (not overbought/oversold)

The price fetch and the math are separated so the scoring is unit-testable
without a network call.
"""

from __future__ import annotations

import logging

import pandas as pd

from .models import SubScore, clamp

log = logging.getLogger("stockerr.scoring.technical")


def to_yf_ticker(symbol: str) -> str:
    """Map an NSE trading symbol to a yfinance ticker (RELIANCE -> RELIANCE.NS)."""
    s = symbol.strip().upper()
    if "." in s or s.startswith("^"):
        return s
    return f"{s}.NS"


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def _rsi_points(value: float) -> float:
    # Full marks inside 40-60; taper to 0 at 30/70; 0 beyond.
    if 40 <= value <= 60:
        return 25.0
    if 30 <= value < 40:
        return 25.0 * (value - 30) / 10.0
    if 60 < value <= 70:
        return 25.0 * (70 - value) / 10.0
    return 0.0


def compute_technical_score(close: pd.Series) -> SubScore:
    """Pure computation from a close-price Series (chronological)."""
    close = pd.to_numeric(close, errors="coerce").dropna()
    if len(close) < 30:
        return SubScore.unavailable("technical", "not enough price history")

    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
    ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
    price = close.iloc[-1]
    rsi_series = rsi(close)
    rsi_val = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

    checks = {
        "above_ema50": (25.0 if price > ema50 else 0.0),
        "above_ema200": (25.0 if price > ema200 else 0.0),
        "ema50_above_ema200": (25.0 if ema50 > ema200 else 0.0),
        "rsi_healthy": _rsi_points(rsi_val),
    }
    score = clamp(sum(checks.values()))
    detail = {
        "price": round(float(price), 2),
        "ema50": round(float(ema50), 2),
        "ema200": round(float(ema200), 2),
        "rsi": round(rsi_val, 1),
        "points": {k: round(v, 1) for k, v in checks.items()},
    }
    note = "" if len(close) >= 200 else "short history (<200d): EMA200 approximate"
    return SubScore("technical", True, score, detail, note)


def fetch_close_series(ticker: str, period: str = "1y") -> pd.Series | None:
    """Fetch daily closes via yfinance. Returns None if unavailable."""
    try:
        import yfinance as yf
    except Exception:
        log.warning("yfinance not installed; skipping technical score. "
                    "Install with: pip install 'stockerr[scoring]'")
        return None
    try:
        hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("yfinance fetch failed for %s: %s", ticker, exc)
        return None
    if hist is None or hist.empty or "Close" not in hist:
        log.warning("No price data for %s.", ticker)
        return None
    return hist["Close"]


def score_technical(symbol: str) -> SubScore:
    ticker = to_yf_ticker(symbol)
    close = fetch_close_series(ticker)
    if close is None:
        return SubScore.unavailable("technical", f"no price data for {ticker}")
    sub = compute_technical_score(close)
    sub.detail["ticker"] = ticker
    return sub
