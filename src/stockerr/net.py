"""Shared HTTP helper: one session, timeouts, retry+backoff, optional TTL cache.

Every network fetch in Stockerr goes through here so live use stays resilient and
polite under rate limits (NSE ~3 req/s, yfinance/CoinGecko throttling). `get`
returns the response WITHOUT raising on 4xx (so callers like Binance can inspect
401/403 themselves); `get_json` raises for status then parses.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
import time
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger("stockerr.net")

DEFAULT_UA = "Stockerr/0.1 (personal-use)"
DEFAULT_CACHE_DIR = Path(tempfile.gettempdir()) / "stockerr_cache"

# Indirection so tests can stub the sleep between retries.
_sleep = time.sleep
_session: Optional[requests.Session] = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({"User-Agent": DEFAULT_UA})
        _session = s
    return _session


def _cache_file(key: str, cache_dir: Path) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    return cache_dir / f"{digest}.json"


def _cache_read(key: str, ttl: float, cache_dir: Path):
    path = _cache_file(key, cache_dir)
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - blob["ts"] <= ttl:
            return blob["data"]
    except Exception:  # noqa: BLE001 - a bad cache file is just a miss
        return None
    return None


def _cache_write(key: str, data, cache_dir: Path) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_file(key, cache_dir).write_text(
            json.dumps({"ts": time.time(), "data": data}), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - caching is best-effort
        log.debug("cache write failed: %s", exc)


def get(url: str, *, params: dict | None = None, headers: dict | None = None,
        timeout: int = 20, retries: int = 3, backoff: float = 1.5) -> requests.Response:
    """GET with retry+backoff on 429/5xx and connection errors. Does NOT raise on 4xx."""
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = session().get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                _sleep(backoff ** attempt)
                continue
            raise
        if (resp.status_code == 429 or resp.status_code >= 500) and attempt < retries:
            wait = resp.headers.get("Retry-After")
            _sleep(float(wait) if wait and wait.isdigit() else backoff ** attempt)
            continue
        return resp
    raise last_exc  # pragma: no cover - loop always returns or raises above


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: int = 20, retries: int = 3, backoff: float = 1.5,
             cache_ttl: Optional[float] = None, cache_dir: Optional[Path] = None):
    """GET + raise_for_status + .json(), with an optional on-disk TTL cache."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    key = f"{url}?{sorted((params or {}).items())}"
    if cache_ttl:
        hit = _cache_read(key, cache_ttl, cache_dir)
        if hit is not None:
            return hit

    resp = get(url, params=params, headers=headers, timeout=timeout,
               retries=retries, backoff=backoff)
    resp.raise_for_status()
    data = resp.json()
    if cache_ttl:
        _cache_write(key, data, cache_dir)
    return data
