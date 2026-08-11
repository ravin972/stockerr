"""Interactive `stockerr init` — store secrets in the OS keyring.

Secrets are read with getpass so they never land in shell history or argv.
Leave a prompt blank to skip (keeps any existing stored value).
"""

from __future__ import annotations

import getpass

from . import config


def _prompt_secret(label: str, name: str) -> None:
    existing = config.get_secret(name)
    status = "already set — press Enter to keep" if existing else "not set"
    value = getpass.getpass(f"  {label} ({status}): ").strip()
    if value:
        config.set_secret(name, value)
        print(f"    stored {name}")
    elif existing:
        print(f"    kept existing {name}")
    else:
        print(f"    skipped {name}")


def run_init() -> None:
    print("Stockerr secret setup — values are stored in Windows Credential Manager.")
    print("Reminder: create your Binance API key as READ-ONLY (Enable Reading only;")
    print("trading and withdrawals OFF; IP-whitelist it).\n")

    print("[Binance — read-only]")
    _prompt_secret("Binance API key", config.SECRET_BINANCE_KEY)
    _prompt_secret("Binance API secret", config.SECRET_BINANCE_SECRET)

    print("\n[Telegram alerts] (optional — leave blank to skip)")
    _prompt_secret("Telegram bot token", config.SECRET_TELEGRAM_TOKEN)
    _prompt_secret("Telegram chat id", config.SECRET_TELEGRAM_CHAT)

    print("\n[Email alerts] (optional — SMTP user + app password)")
    _prompt_secret("Email/SMTP username", config.SECRET_EMAIL_USER)
    _prompt_secret("Email/SMTP app password", config.SECRET_EMAIL_PASSWORD)

    print("\n[Confidence scoring — sentiment] (optional — Anthropic API key)")
    _prompt_secret("Anthropic API key", config.SECRET_ANTHROPIC_KEY)

    print("\n[Discovery] (optional)")
    _prompt_secret("IPO Guru API key (free, for IPO tracker)", config.SECRET_IPO_GURU_KEY)
    _prompt_secret("CoinGecko API key (free Demo, for crypto cap tiers)", config.SECRET_COINGECKO_KEY)

    print("\nDone. Non-secret settings (thresholds, paths, channels) live in .env.")
