"""Light crypto screener (Binance) — momentum filter, sized for a small allocation.

Reuses the equity technical engine (EMA/RSI) on Binance klines, adds relative
strength vs BTC and a market-cap tier (CoinGecko). This is a WATCHLIST FILTER,
not a value screen and not a buy signal — crypto has no earnings/cash flow to
value, is extremely volatile, and small-caps can go to zero.

Pure scoring (unit-tested on synthetic candles); `fetch_*` are graceful network
layers over Binance's public market mirror + CoinGecko free tier.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import pandas as pd

from .. import net
from ..scoring.models import clamp
from ..scoring.technical import compute_technical_score

log = logging.getLogger("stockerr.discovery.crypto")

CRYPTO_DISCLAIMER = (
    "Momentum filter, NOT advice. Crypto has no earnings/cash flow to value, is "
    "extremely volatile, and small-caps can go to zero (rug-pulls, thin liquidity, "
    "wash-traded volume). Signals are historical, not predictive. India: 30% tax + "
    "1% TDS on crypto. Size only what you can afford to lose."
)

BINANCE_DATA_URL = "https://data-api.binance.vision"
COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"

COLUMNS = ["symbol", "cap", "score", "signal", "trend", "rel_vs_btc_pct",
           "volatility_pct", "note"]


def base_asset(symbol: str) -> str:
    """'ETHUSDT' -> 'ETH' (strip the USDT quote)."""
    s = symbol.upper()
    return s[:-4] if s.endswith("USDT") else s


def cap_tier(rank: Optional[int]) -> str:
    if rank is None:
        return "Unknown"
    if rank <= 10:
        return "Large"
    if rank <= 100:
        return "Mid"
    return "Small"


def signal(score: Optional[float]) -> str:
    if score is None or pd.isna(score):
        return "N/A"
    if score > 70:
        return "Bullish"
    if score >= 45:
        return "Neutral"
    return "Bearish"


def closes_from_klines(klines: list) -> pd.Series:
    """Binance klines (list of arrays) -> close-price Series (index = close time)."""
    if not klines:
        return pd.Series(dtype=float)
    closes = [float(k[4]) for k in klines]
    times = pd.to_datetime([int(k[6]) for k in klines], unit="ms")
    return pd.Series(closes, index=times)


def relative_strength(coin: pd.Series, btc: pd.Series) -> Optional[float]:
    """Coin's total return minus BTC's over the series (percentage points)."""
    if len(coin) < 2 or btc is None or len(btc) < 2:
        return None
    coin_ret = (coin.iloc[-1] / coin.iloc[0] - 1) * 100.0
    btc_ret = (btc.iloc[-1] / btc.iloc[0] - 1) * 100.0
    return coin_ret - btc_ret


def volatility(s: pd.Series) -> Optional[float]:
    rets = s.pct_change().dropna()
    if len(rets) < 2:
        return None
    return float(rets.std() * math.sqrt(365) * 100.0)   # crypto trades daily


def score_crypto(close: pd.Series, btc_close: Optional[pd.Series] = None) -> Optional[float]:
    """0-100 momentum blend: 70% trend/RSI + 30% relative strength vs BTC."""
    tech = compute_technical_score(close)
    if not tech.available:
        return None
    comps: dict[str, tuple[float, float]] = {"technical": (tech.score, 0.70)}
    rel = relative_strength(close, btc_close) if btc_close is not None else None
    if rel is not None:
        comps["rel_strength"] = (clamp((rel + 20.0) / 40.0 * 100.0), 0.30)  # -20%->0,+20%->100
    wsum = sum(w for _, w in comps.values())
    return round(sum(v * w for v, w in comps.values()) / wsum, 1)


def build_crypto_df(entries: list[dict]) -> pd.DataFrame:
    """entries: [{symbol, close(Series), btc_close(Series)?, cap_rank(int)?}]."""
    btc_default = None
    for e in entries:
        if e["symbol"].upper().startswith("BTC"):
            btc_default = e.get("close")
            break

    rows = []
    for e in entries:
        close = e.get("close")
        if close is None or len(close) < 30:
            continue
        btc = e.get("btc_close", btc_default)
        score = score_crypto(close, btc)
        tech = compute_technical_score(close)
        rel = relative_strength(close, btc) if btc is not None else None
        rows.append({
            "symbol": e["symbol"],
            "cap": cap_tier(e.get("cap_rank")),
            "score": score,
            "signal": signal(score),
            "trend": round(tech.score, 0) if tech.available else None,
            "rel_vs_btc_pct": round(rel, 1) if rel is not None else None,
            "volatility_pct": round(volatility(close), 0) if volatility(close) is not None else None,
            "note": "momentum only",
        })
    df = pd.DataFrame(rows, columns=COLUMNS)
    if df.empty:
        return df
    return df.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)


def fetch_usdt_symbols(timeout: int = 20) -> list[str]:
    """Tradable USDT spot symbols from Binance exchangeInfo. [] on failure."""
    try:
        # Symbol list is slow-changing -> cache for a day.
        data = net.get_json(f"{BINANCE_DATA_URL}/api/v3/exchangeInfo",
                            timeout=timeout, cache_ttl=86400)
        return [s["symbol"] for s in data.get("symbols", [])
                if s.get("status") == "TRADING" and s.get("isSpotTradingAllowed")
                and s.get("quoteAsset") == "USDT"]
    except Exception as exc:  # noqa: BLE001
        log.warning("Binance exchangeInfo fetch failed: %s", exc)
        return []


def fetch_24h_volume(timeout: int = 20) -> dict[str, float]:
    """{symbol: 24h quoteVolume} for a liquidity floor. {} on failure."""
    try:
        data = net.get_json(f"{BINANCE_DATA_URL}/api/v3/ticker/24hr", timeout=timeout)
        return {d["symbol"]: float(d.get("quoteVolume", 0)) for d in data}
    except Exception as exc:  # noqa: BLE001
        log.warning("Binance 24h ticker fetch failed: %s", exc)
        return {}


def fetch_cap_ranks(timeout: int = 20) -> dict[str, int]:
    """{ASSET: market_cap_rank} from CoinGecko top markets. {} on failure.

    Uses a free Demo key if stored (higher rate limit). Symbols are ordered by
    market cap, so the first occurrence of a ticker is its highest-cap coin.
    """
    from ..config import SECRET_COINGECKO_KEY, get_secret
    headers = {}
    key = get_secret(SECRET_COINGECKO_KEY)
    if key:
        headers["x-cg-demo-api-key"] = key
    ranks: dict[str, int] = {}
    try:
        for page in (1, 2):   # top ~500 by market cap
            data = net.get_json(
                COINGECKO_MARKETS,
                params={"vs_currency": "usd", "order": "market_cap_desc",
                        "per_page": 250, "page": page},
                headers=headers, timeout=timeout, cache_ttl=3600)
            for c in data:
                sym = str(c.get("symbol", "")).upper()
                rank = c.get("market_cap_rank")
                if sym and rank and sym not in ranks:
                    ranks[sym] = int(rank)
    except Exception as exc:  # noqa: BLE001
        log.warning("CoinGecko cap ranks fetch failed: %s", exc)
    return ranks


def fetch_klines(symbol: str, interval: str = "1d", limit: int = 250,
                 timeout: int = 20) -> pd.Series:
    """Daily close series for a Binance symbol. Empty Series on failure."""
    try:
        data = net.get_json(f"{BINANCE_DATA_URL}/api/v3/klines",
                            params={"symbol": symbol, "interval": interval, "limit": limit},
                            timeout=timeout)
        return closes_from_klines(data)
    except Exception as exc:  # noqa: BLE001
        log.warning("Binance klines fetch failed for %s: %s", symbol, exc)
        return pd.Series(dtype=float)
