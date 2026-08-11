"""Binance read-only Spot source.

Uses only signed GET requests (never any order endpoint). Valuation is done by
pricing every asset in USDT via the public ticker endpoint; INR conversion
happens later in the merge step using the FX rate.

The HTTP client is plain `requests` + HMAC-SHA256 signing — small, transparent,
and dependency-light, which suits a security-conscious read-only tool. (The
`python-binance` library is a drop-in alternative if you prefer.)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from urllib.parse import urlencode

from .. import net
from ..models import CATEGORY_CRYPTO, Holding
from .base import Source

log = logging.getLogger("stockerr.binance")

BASE_URL = "https://api.binance.com"

# Treated as 1 USD each (USDT ~ USD peg) so they still get a value.
STABLE_USD = {"USDT", "BUSD", "USDC", "FDUSD", "TUSD", "USDP", "DAI"}


def _sign(query: str, secret: str) -> str:
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def price_in_usdt(asset: str, prices: dict[str, float]) -> float:
    """Best-effort USDT price for `asset` given a symbol->price map.

    Returns 0.0 if no direct USDT pair and no BTC bridge exists (flagged upstream).
    """
    if asset in STABLE_USD:
        return 1.0
    direct = prices.get(f"{asset}USDT")
    if direct:
        return direct
    # Bridge illiquid alts through BTC.
    via_btc = prices.get(f"{asset}BTC")
    btc_usdt = prices.get("BTCUSDT")
    if via_btc and btc_usdt:
        return via_btc * btc_usdt
    return 0.0


def build_holdings(account: dict, prices: dict[str, float]) -> list[Holding]:
    """Pure transform: Binance /account JSON + price map -> Holdings. (Unit-testable.)"""
    holdings: list[Holding] = []
    for bal in account.get("balances", []):
        try:
            qty = float(bal.get("free", 0)) + float(bal.get("locked", 0))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        asset = bal["asset"]
        usdt = price_in_usdt(asset, prices)
        if usdt <= 0:
            log.warning("No USD price for %s; valued at 0. Holding still listed.", asset)
        holdings.append(
            Holding(
                asset=asset,
                symbol=asset,
                category=CATEGORY_CRYPTO,
                quantity=qty,
                price_native=usdt,
                currency="USD",
                source="binance",
            )
        )
    return holdings


class BinanceSource(Source):
    name = "binance"

    def __init__(self, api_key: str, api_secret: str, *,
                 base_url: str = BASE_URL, recv_window: int = 5000, timeout: int = 15):
        if not api_key or not api_secret:
            raise ValueError("Binance API key/secret missing (run `stockerr init`).")
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.recv_window = recv_window
        self.timeout = timeout

    def _signed_get(self, path: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = self.recv_window
        query = urlencode(params)
        signature = _sign(query, self.api_secret)
        url = f"{self.base_url}{path}?{query}&signature={signature}"
        headers = {"X-MBX-APIKEY": self.api_key}
        resp = net.get(url, headers=headers, timeout=self.timeout)
        if resp.status_code in (401, 403):
            raise PermissionError(
                "Binance rejected the API key (401/403). Check the key is valid, "
                "'Enable Reading' is on, and your IP is whitelisted."
            )
        resp.raise_for_status()
        return resp.json()

    def _all_prices(self) -> dict[str, float]:
        data = net.get_json(f"{self.base_url}/api/v3/ticker/price", timeout=self.timeout)
        return {d["symbol"]: float(d["price"]) for d in data}

    def fetch_holdings(self) -> list[Holding]:
        account = self._signed_get("/api/v3/account", {"omitZeroBalances": "true"})
        perms = account.get("permissions")
        if perms and perms != ["SPOT"]:
            log.info("Binance key permissions: %s (read-only Spot recommended).", perms)
        prices = self._all_prices()
        holdings = build_holdings(account, prices)
        log.info("Binance: %d non-zero balances.", len(holdings))
        return holdings
