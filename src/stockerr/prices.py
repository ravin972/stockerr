"""Refresh stock holdings' prices from yfinance (free), so a daily run values the
portfolio at today's prices without needing the paid Groww API.

Holdings quantities come from the Groww CSV; only the price is refreshed. Crypto
already gets live prices from Binance, so this touches INR stock holdings only.
"""

from __future__ import annotations

import logging
from typing import Optional

from .models import CATEGORY_STOCK, Holding
from .scoring.technical import to_yf_ticker

log = logging.getLogger("stockerr.prices")


def fetch_live_price(symbol: str) -> Optional[float]:
    """Latest price for an NSE symbol via yfinance. None on failure."""
    try:
        import yfinance as yf
    except Exception:
        log.warning("yfinance not installed; can't refresh prices "
                    "(pip install 'stockerr[scoring]').")
        return None
    ticker = to_yf_ticker(symbol)
    try:
        t = yf.Ticker(ticker)
        try:
            price = t.fast_info.get("last_price") or t.fast_info.get("lastPrice")
            if price:
                return float(price)
        except Exception:  # noqa: BLE001 - fall back to history
            pass
        hist = t.history(period="1d")
        if hist is not None and not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as exc:  # noqa: BLE001
        log.warning("Live price fetch failed for %s: %s", ticker, exc)
    return None


def refresh_holding_prices(holdings: list[Holding]) -> int:
    """Update INR stock holdings in place with fresh yfinance prices. Returns count updated."""
    updated = 0
    for h in holdings:
        if h.category != CATEGORY_STOCK or h.currency != "INR":
            continue
        price = fetch_live_price(h.symbol or h.asset)
        if price and price > 0:
            h.price_native = price
            updated += 1
    log.info("Refreshed live prices for %d stock holdings.", updated)
    return updated
