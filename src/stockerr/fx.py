"""Foreign-exchange: convert USD (~USDT) to INR.

Binance has no fiat endpoint, so crypto is priced in USDT on Binance and then
converted to INR with a rate from a dedicated free FX feed (ECB via Frankfurter,
with open.er-api.com as a fallback). A manual override is also supported.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from . import net

log = logging.getLogger("stockerr.fx")

FRANKFURTER_URL = "https://api.frankfurter.app/latest?from=USD&to=INR"
ERAPI_URL = "https://open.er-api.com/v6/latest/USD"


@dataclass
class FxRate:
    pair: str          # e.g. "USD/INR"
    rate: float        # 1 USD = <rate> INR
    source: str        # frankfurter | erapi | manual
    fetched_at: str    # ISO8601 UTC


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _from_frankfurter(timeout: int) -> Optional[float]:
    # FX moves daily — cache for an hour to avoid hammering the feed.
    data = net.get_json(FRANKFURTER_URL, timeout=timeout, cache_ttl=3600)
    return float(data["rates"]["INR"])


def _from_erapi(timeout: int) -> Optional[float]:
    data = net.get_json(ERAPI_URL, timeout=timeout, cache_ttl=3600)
    if data.get("result") != "success":
        raise RuntimeError(f"erapi result={data.get('result')}")
    return float(data["rates"]["INR"])


def get_usd_inr(source: str = "frankfurter",
                manual_rate: Optional[float] = None,
                timeout: int = 15) -> FxRate:
    """Return the current USD->INR rate.

    On any network/parse failure of the primary source, falls back to the other
    live feed before giving up.
    """
    source = (source or "frankfurter").lower()

    if source == "manual":
        if not manual_rate or manual_rate <= 0:
            raise ValueError("fx_source=manual but no valid STOCKERR_MANUAL_USD_INR set")
        return FxRate("USD/INR", float(manual_rate), "manual", _now_iso())

    providers = [("frankfurter", _from_frankfurter), ("erapi", _from_erapi)]
    # Try the requested provider first, then the rest as fallbacks.
    providers.sort(key=lambda p: 0 if p[0] == source else 1)

    last_err: Optional[Exception] = None
    for name, fn in providers:
        try:
            rate = fn(timeout)
            if rate and rate > 0:
                if name != source:
                    log.warning("FX source %s failed; used fallback %s", source, name)
                return FxRate("USD/INR", rate, name, _now_iso())
        except Exception as exc:  # noqa: BLE001 - try next provider
            last_err = exc
            log.warning("FX provider %s failed: %s", name, exc)

    raise RuntimeError(f"All FX providers failed; last error: {last_err}")
