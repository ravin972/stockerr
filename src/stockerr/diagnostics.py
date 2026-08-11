"""`stockerr doctor` — probe every data path and report what's live vs a gap.

The fastest way to build trust before relying on the tool: confirm the Binance key
is genuinely read-only, sources parse, and each feed is reachable.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import config, net
from .config import Config
from .logging_setup import redact

log = logging.getLogger("stockerr.diagnostics")

DEFAULT_GROWW_CSV = Path("data/groww_holdings.csv")

OK, WARN, MISSING, FAIL = "OK", "WARN", "MISSING", "FAIL"


def _reachable(name: str, url: str) -> tuple[str, str, str]:
    try:
        resp = net.get(url, timeout=10, retries=1, backoff=0)
        if resp.status_code < 400:
            return name, OK, "reachable"
        return name, WARN, f"HTTP {resp.status_code}"
    except Exception as exc:  # noqa: BLE001
        return name, FAIL, str(exc)[:70]


def run_diagnostics(cfg: Config) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []

    # keyring backend
    try:
        import keyring
        keyring.get_keyring()
        out.append(("keyring backend", OK, ""))
    except Exception as exc:  # noqa: BLE001
        out.append(("keyring backend", WARN, str(exc)[:70]))

    # Binance key + read-only check
    key = config.get_secret(config.SECRET_BINANCE_KEY)
    secret = config.get_secret(config.SECRET_BINANCE_SECRET)
    if not (key and secret):
        out.append(("Binance key", MISSING, "not set (run `stockerr init`)"))
    else:
        try:
            from .sources.binance_api import BinanceSource
            perms = BinanceSource(key, secret)._signed_get("/sapi/v1/account/apiRestrictions")
            if perms.get("enableSpotAndMarginTrading") or perms.get("enableWithdrawals"):
                out.append(("Binance key read-only", WARN,
                            "key can TRADE/WITHDRAW — recreate as read-only!"))
            else:
                out.append(("Binance key read-only", OK, "reading only"))
        except Exception as exc:  # noqa: BLE001
            out.append(("Binance key", FAIL, str(exc)[:70]))

    # FX
    try:
        from .fx import get_usd_inr
        fx = get_usd_inr(cfg.fx_source, cfg.manual_usd_inr)
        out.append(("FX USD/INR", OK, f"{fx.rate} ({fx.source})"))
    except Exception as exc:  # noqa: BLE001
        out.append(("FX USD/INR", FAIL, str(exc)[:70]))

    # Groww CSV
    groww = cfg.groww_csv_paths[0] if cfg.groww_csv_paths else (
        DEFAULT_GROWW_CSV if DEFAULT_GROWW_CSV.exists() else None)
    if not groww:
        out.append(("Groww CSV", MISSING, "no holdings CSV configured"))
    else:
        try:
            from .sources.groww_csv import parse_groww_csv
            n = len(parse_groww_csv(groww))
            out.append(("Groww CSV", OK, f"{n} holdings parsed"))
        except Exception as exc:  # noqa: BLE001
            out.append(("Groww CSV", FAIL, str(exc)[:70]))

    # Screener CSV
    if not cfg.screener_csv_paths:
        out.append(("Screener CSV", MISSING, "STOCKERR_SCREENER_CSV not set"))
    else:
        try:
            from .scoring.fundamental import load_fundamentals
            funds = load_fundamentals(cfg.screener_csv_paths)
            out.append(("Screener CSV", OK if funds else WARN,
                        f"{len(funds)} companies parsed"))
        except Exception as exc:  # noqa: BLE001
            out.append(("Screener CSV", FAIL, str(exc)[:70]))

    # Reachability of the free feeds
    out.append(_reachable("mfapi.in (funds)", "https://api.mfapi.in/mf/119597/latest"))
    out.append(_reachable("Binance public", "https://data-api.binance.vision/api/v3/ping"))
    out.append(_reachable("CoinGecko", "https://api.coingecko.com/api/v3/ping"))

    # IPO source
    if config.get_secret(config.SECRET_IPO_GURU_KEY):
        out.append(("IPO source", OK, "IPO Guru key set"))
    else:
        try:
            import nse  # noqa: F401
            out.append(("IPO source", OK, "`nse` library installed"))
        except Exception:  # noqa: BLE001
            out.append(("IPO source", MISSING, "add IPO Guru key or `pip install nse`"))

    # Telegram channel
    if not cfg.telegram_enabled:
        out.append(("Telegram", MISSING, "STOCKERR_TELEGRAM_ENABLED not true"))
    else:
        tok = config.get_secret(config.SECRET_TELEGRAM_TOKEN)
        chat = config.get_secret(config.SECRET_TELEGRAM_CHAT)
        if not (tok and chat):
            out.append(("Telegram", MISSING, "token/chat id not set"))
        else:
            try:
                data = net.get_json(f"https://api.telegram.org/bot{tok}/getMe", timeout=10)
                if data.get("ok"):
                    uname = data.get("result", {}).get("username", "bot")
                    out.append(("Telegram", OK, f"@{uname} valid — send the bot /start once"))
                else:
                    out.append(("Telegram", WARN, "token rejected by getMe"))
            except Exception as exc:  # noqa: BLE001
                out.append(("Telegram", FAIL, redact(str(exc))))

    # Email channel
    if not cfg.email_enabled:
        out.append(("Email (SMTP)", MISSING, "STOCKERR_EMAIL_ENABLED not true"))
    else:
        user = config.get_secret(config.SECRET_EMAIL_USER)
        pw = config.get_secret(config.SECRET_EMAIL_PASSWORD)
        if not (user and pw and cfg.email_to):
            out.append(("Email (SMTP)", MISSING, "user/app-password/recipient not set"))
        else:
            out.append(("Email (SMTP)", OK, f"{user} -> {cfg.email_to} (send-test: `stockerr digest`)"))

    # Watchlists
    out.append(("MF watchlist", OK if cfg.mf_watchlist else MISSING,
                f"{len(cfg.mf_watchlist)} scheme codes"))
    out.append(("Crypto watchlist", OK if cfg.crypto_watchlist else MISSING,
                f"{len(cfg.crypto_watchlist)} symbols"))
    return out
