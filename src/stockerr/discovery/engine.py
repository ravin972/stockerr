"""DiscoveryEngine — facade over the opportunity screeners (stocks first)."""

from __future__ import annotations

import logging

import pandas as pd

from ..config import Config, load_config
from .stocks import screen_stocks
from .universe import load_amfi_caps

log = logging.getLogger("stockerr.discovery.engine")


class DiscoveryEngine:
    def __init__(self, cfg: Config | None = None, env_file: str = ".env"):
        self.cfg = cfg or load_config(env_file)

    def discover_stocks(self, csv_paths: list | None = None, *,
                        enrich_technical: bool = False, top_n: int = 20) -> pd.DataFrame:
        """Rank a Screener CSV universe into ideas. Defaults to STOCKERR_SCREENER_CSV."""
        paths = csv_paths or self.cfg.screener_csv_paths
        if not paths:
            log.info("No Screener CSV configured (STOCKERR_SCREENER_CSV / --csv).")
            return screen_stocks([])
        cap_lookup = load_amfi_caps(self.cfg.amfi_csv_path) if self.cfg.amfi_csv_path else None
        return screen_stocks(paths, enrich_technical=enrich_technical, top_n=top_n,
                             cap_lookup=cap_lookup)

    def discover_ipos(self) -> pd.DataFrame:
        """Upcoming/open IPOs with a fundamentals score. Needs an IPO source configured."""
        from .ipo import build_ipo_df, fetch_ipos
        return build_ipo_df(fetch_ipos(self.cfg))

    def discover_mutual_funds(self, codes: list | None = None) -> pd.DataFrame:
        """Rank funds by consistency + risk-adjusted return. Defaults to STOCKERR_MF_WATCHLIST."""
        from .mutual_funds import fetch_nav, screen_funds, to_series
        codes = codes or self.cfg.mf_watchlist
        funds = []
        for code in codes:
            records, meta = fetch_nav(code)
            if not records:
                continue
            funds.append({
                "code": code,
                "name": meta.get("scheme_name", code),
                "category": meta.get("scheme_category", ""),
                "series": to_series(records),
            })
        return screen_funds(funds)

    def discover_crypto(self, symbols: list | None = None, *,
                        min_quote_volume: float = 1_000_000) -> pd.DataFrame:
        """Momentum screen of Binance USDT pairs. Defaults to STOCKERR_CRYPTO_WATCHLIST.

        Attaches CoinGecko cap tiers and drops pairs below a 24h quote-volume floor
        (BTC is always kept for the relative-strength benchmark).
        """
        from .crypto import (
            base_asset,
            build_crypto_df,
            fetch_24h_volume,
            fetch_cap_ranks,
            fetch_klines,
        )
        symbols = symbols or self.cfg.crypto_watchlist
        if not symbols:
            return build_crypto_df([])
        syms = list(dict.fromkeys([s.upper() for s in symbols] + ["BTCUSDT"]))
        volumes = fetch_24h_volume()
        ranks = fetch_cap_ranks()
        entries = []
        for s in syms:
            if volumes and s != "BTCUSDT" and volumes.get(s, 0.0) < min_quote_volume:
                log.info("Skipping %s: 24h volume below liquidity floor.", s)
                continue
            close = fetch_klines(s)
            if len(close) >= 30:
                entries.append({"symbol": s, "close": close,
                                "cap_rank": ranks.get(base_asset(s))})
        return build_crypto_df(entries)
