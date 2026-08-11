"""Upcoming-IPO tracker.

Lists upcoming/open IPOs with a **fundamentals** score from RHP highlights
(RoNW, debt) and shows subscription + GMP as data — NOT a profit prediction.
Honest framing baked in: IPO listing gains are speculative and GMP is unofficial.

The parse/score/table functions are pure (unit-tested). `fetch_ipos` is a thin,
graceful network layer over IPO Guru (free API key) or the `nse` library.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import pandas as pd

from .. import net

log = logging.getLogger("stockerr.discovery.ipo")

IPO_DISCLAIMER = (
    "IPO listing gains are SPECULATIVE. GMP (grey-market premium) is unofficial and "
    "unregulated — mood, not a forecast. Historically ~66-72% of mainboard IPOs list "
    "positive, but individual outcomes are unpredictable. The score reflects RHP "
    "fundamentals only; subscription is the strongest public signal. Not advice."
)

IPOGURU_URL = "https://www.ipoguru.in/api/v1/ipos"

COLUMNS = ["name", "type", "open", "close", "price_band", "lot_size",
           "subscription_x", "gmp_unofficial", "fund_score", "status"]


def _num(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^0-9.\-]", "", str(v))
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def normalize_ipo(raw: dict) -> dict:
    """Map a provider's IPO dict (IPO Guru / nse / aggregator) to a standard shape."""
    # Normalize keys to alphanumeric-only so snake_case, camelCase and "Title Case"
    # all match the same candidate (companyName / company_name / "Company Name").
    low = {re.sub(r"[^a-z0-9]", "", str(k).lower()): v for k, v in raw.items()}

    def g(*keys):
        for k in keys:
            kk = re.sub(r"[^a-z0-9]", "", k)
            if kk in low and low[kk] not in (None, "", "-"):
                return low[kk]
        return None

    # subscription: IPO Guru uses subscription/times; NSE uses noOfTime.
    sub = g("subscription", "sub", "total_subscription", "times_subscribed",
            "subscription_times", "no_of_time")
    if isinstance(sub, dict):
        sub = sub.get("total") or sub.get("times")
    gmp = g("gmp", "grey_market_premium", "gmp_price")
    if isinstance(gmp, dict):
        gmp = gmp.get("premium") or gmp.get("gmp") or gmp.get("value")

    return {
        "name": g("name", "company", "company_name", "issuer") or "?",
        "symbol": g("symbol", "ticker") or "",
        "type": g("type", "ipo_type", "series") or "",
        "open": g("open", "open_date", "bidding_start_date", "issue_start_date") or "",
        "close": g("close", "close_date", "bidding_end_date", "issue_end_date") or "",
        "listing": g("listing", "listing_date", "listing_on") or "",
        "price_band": g("price_band", "price", "issue_price") or "",
        "lot_size": _num(g("lot_size", "lot", "market_lot")),
        "issue_size": g("issue_size", "size", "total_issue_amount") or "",
        "subscription": _num(sub),
        "gmp": _num(gmp),
        "ronw": _num(g("ronw", "return_on_net_worth", "roe")),
        "de": _num(g("de", "debt_equity", "debt_to_equity", "debt_equity_ratio")),
        "status": g("status", "ipo_status") or "",
    }


def score_ipo_fundamentals(rec: dict) -> Optional[float]:
    """0-100 from RHP fundamentals (RoNW + debt). None if neither is available.

    This is a QUALITY read of the issuer, NOT a listing-gain prediction.
    """
    ronw, de = rec.get("ronw"), rec.get("de")
    parts, possible = 0.0, 0.0
    if ronw is not None:
        parts += 50.0 * max(0.0, min(1.0, ronw / 20.0))   # 20% RoNW -> full
        possible += 50.0
    if de is not None:
        parts += 50.0 * max(0.0, min(1.0, (2.0 - de) / 1.5))  # <=0.5 full, >=2 zero
        possible += 50.0
    if possible == 0:
        return None
    return round(parts / possible * 100.0, 1)


def build_ipo_df(records: list[dict]) -> pd.DataFrame:
    rows = []
    seen: set[str] = set()
    for raw in records:
        rec = normalize_ipo(raw)
        key = (rec.get("symbol") or rec["name"]).upper()
        if key in seen:   # an IPO can appear in both current + upcoming lists
            continue
        seen.add(key)
        rows.append({
            "name": rec["name"],
            "type": rec["type"],
            "open": rec["open"],
            "close": rec["close"],
            "price_band": rec["price_band"],
            "lot_size": rec["lot_size"],
            "subscription_x": rec["subscription"],
            "gmp_unofficial": rec["gmp"],
            "fund_score": score_ipo_fundamentals(rec),
            "status": rec["status"],
        })
    df = pd.DataFrame(rows, columns=COLUMNS)
    if df.empty:
        return df
    return df.sort_values("fund_score", ascending=False, na_position="last").reset_index(drop=True)


def fetch_ipos(cfg=None) -> list[dict]:
    """Best-effort fetch of upcoming/current IPOs. Returns [] on any failure."""
    from ..config import get_secret

    # 1) IPO Guru free API (permits programmatic use) if a key is stored.
    key = get_secret("ipo_guru_api_key")
    if key:
        try:
            data = net.get_json(IPOGURU_URL, headers={"X-API-KEY": key}, timeout=20)
            items = data.get("ipos", data) if isinstance(data, dict) else data
            if isinstance(items, list) and items:
                return items
        except Exception as exc:  # noqa: BLE001
            log.warning("IPO Guru fetch failed: %s", exc)

    # 2) `nse` library (handles NSE cookies/throttle) if installed.
    try:
        from nse import NSE  # type: ignore
        import tempfile
        nse = NSE(download_folder=tempfile.gettempdir())
        out = []
        # Current first: those records are richer (subscription via noOfTime) and
        # win de-duplication against the sparser upcoming entries.
        for meth in ("listCurrentIPO", "listUpcomingIPO"):
            try:
                out.extend(getattr(nse, meth)() or [])
            except Exception:  # noqa: BLE001
                pass
        return out
    except Exception as exc:  # noqa: BLE001
        log.info("No IPO source available (add STOCKERR_IPO_GURU_API_KEY or install `nse`): %s", exc)
        return []
