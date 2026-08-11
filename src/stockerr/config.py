"""Configuration and secret access.

Non-secret settings come from environment variables (optionally loaded from a
`.env` file). Secrets (API keys, tokens, passwords) come from the OS keyring
(Windows Credential Manager), never from `.env` or the command line.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

try:  # keyring is a hard dependency, but degrade gracefully if a backend is missing
    import keyring
    import keyring.errors
except Exception:  # pragma: no cover - only on broken installs
    keyring = None  # type: ignore

SERVICE = "stockerr"

# --- Secret names (keys under the "stockerr" service in the OS keyring) --------
SECRET_BINANCE_KEY = "binance_api_key"
SECRET_BINANCE_SECRET = "binance_api_secret"
SECRET_TELEGRAM_TOKEN = "telegram_bot_token"
SECRET_TELEGRAM_CHAT = "telegram_chat_id"
SECRET_EMAIL_USER = "email_smtp_user"
SECRET_EMAIL_PASSWORD = "email_smtp_password"
SECRET_ANTHROPIC_KEY = "anthropic_api_key"
SECRET_IPO_GURU_KEY = "ipo_guru_api_key"
SECRET_COINGECKO_KEY = "coingecko_api_key"

ALL_SECRETS = [
    SECRET_BINANCE_KEY,
    SECRET_BINANCE_SECRET,
    SECRET_TELEGRAM_TOKEN,
    SECRET_TELEGRAM_CHAT,
    SECRET_EMAIL_USER,
    SECRET_EMAIL_PASSWORD,
    SECRET_ANTHROPIC_KEY,
    SECRET_IPO_GURU_KEY,
    SECRET_COINGECKO_KEY,
]


def get_secret(name: str) -> Optional[str]:
    """Return a secret. Env var STOCKERR_<NAME> wins (useful headless/CI), else keyring."""
    env = os.environ.get(f"STOCKERR_{name.upper()}")
    if env:
        return env
    if keyring is None:
        return None
    try:
        return keyring.get_password(SERVICE, name)
    except Exception:
        return None


def set_secret(name: str, value: str) -> None:
    if keyring is None:
        raise RuntimeError(
            "No keyring backend available. Install one, or set STOCKERR_<NAME> env vars."
        )
    keyring.set_password(SERVICE, name, value)


def delete_secret(name: str) -> None:
    if keyring is None:
        return
    try:
        keyring.delete_password(SERVICE, name)
    except Exception:
        pass


# --- Non-secret config --------------------------------------------------------


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_float(name: str, default: float) -> float:
    raw = _get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = _get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool = False) -> bool:
    raw = _get(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _get_paths(name: str) -> list[Path]:
    raw = _get(name)
    if not raw:
        return []
    return [Path(p.strip()) for p in raw.split(";") if p.strip()]


def _get_list(name: str) -> list[str]:
    raw = _get(name)
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _get_allocation(name: str) -> dict[str, float]:
    """Parse "stock=50,mf=20,crypto=30" -> {'stock':50.0,...}."""
    out: dict[str, float] = {}
    for pair in _get_list(name):
        if "=" in pair:
            k, v = pair.split("=", 1)
            try:
                out[k.strip().lower()] = float(v)
            except ValueError:
                continue
    return out


@dataclass
class Config:
    base_currency: str = "INR"
    exports_dir: Path = Path("exports")
    state_dir: Path = Path("state")
    log_level: str = "INFO"

    # Source mode: "live" (Binance API + Groww CSV) or "csv" (Groww CSV only)
    source_mode: str = "live"

    # Groww CSV source
    groww_csv_paths: list[Path] = field(default_factory=list)

    # FX
    fx_source: str = "frankfurter"   # frankfurter | erapi | manual
    manual_usd_inr: Optional[float] = None

    # Alert thresholds
    drift_threshold_pp: float = 5.0
    price_move_threshold_pct: float = 10.0
    target_allocation: dict[str, float] = field(default_factory=dict)

    # Scoring
    score_watchlist: list[str] = field(default_factory=list)
    screener_csv_paths: list[Path] = field(default_factory=list)
    score_alert_min: Optional[float] = None

    # Discovery watchlists
    mf_watchlist: list[str] = field(default_factory=list)        # AMFI scheme codes
    crypto_watchlist: list[str] = field(default_factory=list)    # Binance USDT symbols
    amfi_csv_path: Optional[Path] = None                         # AMFI cap categorization file

    # Alert channels
    telegram_enabled: bool = False
    email_enabled: bool = False
    email_smtp_host: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_from: str = ""
    email_to: str = ""


def load_config(env_file: str | os.PathLike = ".env") -> Config:
    """Load `.env` (if present) then build a Config from environment variables."""
    load_dotenv(env_file, override=False)

    manual = _get("STOCKERR_MANUAL_USD_INR")
    score_min = _get("STOCKERR_SCORE_ALERT_MIN")

    # Default to data/screener_screen.csv when present (mirrors the Groww CSV default),
    # so both holdings scoring and the discovery screener pick it up with no env var.
    screener_paths = _get_paths("STOCKERR_SCREENER_CSV")
    if not screener_paths and Path("data/screener_screen.csv").exists():
        screener_paths = [Path("data/screener_screen.csv")]

    return Config(
        exports_dir=Path(_get("STOCKERR_EXPORTS_DIR", "exports")),
        state_dir=Path(_get("STOCKERR_STATE_DIR", "state")),
        log_level=_get("STOCKERR_LOG_LEVEL", "INFO") or "INFO",
        source_mode=(_get("STOCKERR_SOURCE_MODE", "live") or "live").lower(),
        groww_csv_paths=_get_paths("STOCKERR_GROWW_CSV"),
        fx_source=(_get("STOCKERR_FX_SOURCE", "frankfurter") or "frankfurter").lower(),
        manual_usd_inr=float(manual) if manual else None,
        drift_threshold_pp=_get_float("STOCKERR_DRIFT_THRESHOLD_PP", 5.0),
        price_move_threshold_pct=_get_float("STOCKERR_PRICE_MOVE_THRESHOLD_PCT", 10.0),
        target_allocation=_get_allocation("STOCKERR_TARGET_ALLOCATION"),
        score_watchlist=_get_list("STOCKERR_SCORE_WATCHLIST"),
        screener_csv_paths=screener_paths,
        score_alert_min=float(score_min) if score_min else None,
        mf_watchlist=_get_list("STOCKERR_MF_WATCHLIST"),
        crypto_watchlist=_get_list("STOCKERR_CRYPTO_WATCHLIST"),
        amfi_csv_path=(Path(_get("STOCKERR_AMFI_CSV")) if _get("STOCKERR_AMFI_CSV") else None),
        telegram_enabled=_get_bool("STOCKERR_TELEGRAM_ENABLED"),
        email_enabled=_get_bool("STOCKERR_EMAIL_ENABLED"),
        email_smtp_host=_get("STOCKERR_EMAIL_SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com",
        email_smtp_port=_get_int("STOCKERR_EMAIL_SMTP_PORT", 587),
        email_from=_get("STOCKERR_EMAIL_FROM"),
        email_to=_get("STOCKERR_EMAIL_TO"),
    )
