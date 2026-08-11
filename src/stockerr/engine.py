"""StockerrEngine — the single orchestration facade used by both the CLI and the UI.

Wraps the existing building blocks (sources -> FX -> merge -> scoring -> alerts ->
report) behind one class so `app.py` and `cli.py` share exactly one code path.
Everything here is read-only; nothing places trades.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from . import config, report
from .alerts import state as state_mod
from .alerts.detect import detect_alerts
from .alerts.email import send_email
from .alerts.telegram import send_telegram
from .config import Config, load_config
from .fx import FxRate, get_usd_inr
from .logging_setup import redact
from .merge import allocation_by_category, build_dataframe, total_net_worth
from .models import CATEGORY_CRYPTO, CATEGORY_MF, CATEGORY_STOCK, SourceResult
from .sources.binance_api import BinanceSource
from .sources.groww_csv import GrowwCsvSource

log = logging.getLogger("stockerr.engine")

DEFAULT_GROWW_CSV = Path("data/groww_holdings.csv")


class PortfolioError(RuntimeError):
    """Raised when the portfolio cannot be valued (e.g. crypto held but FX unavailable)."""


@dataclass
class PortfolioResult:
    df: pd.DataFrame
    cat_df: pd.DataFrame
    fx: FxRate
    source_results: list[SourceResult]
    generated_at: datetime

    @property
    def net_worth(self) -> float:
        return total_net_worth(self.df)

    @property
    def by_category(self) -> dict[str, float]:
        if self.cat_df.empty:
            return {}
        return {str(r["category"]): float(r["value_inr"]) for _, r in self.cat_df.iterrows()}

    def category_value(self, category: str) -> float:
        return self.by_category.get(category, 0.0)

    @property
    def has_holdings(self) -> bool:
        return not self.df.empty

    @property
    def failures(self) -> list[SourceResult]:
        return [r for r in self.source_results if not r.ok]


@dataclass
class PipelineResult:
    portfolio: PortfolioResult
    scores_df: Optional[pd.DataFrame]
    alerts: list[str]
    report_paths: dict
    sent: dict


class StockerrEngine:
    def __init__(self, cfg: Config | None = None, env_file: str = ".env"):
        self.cfg = cfg or load_config(env_file)

    # --- secret / config helpers (used by the UI sidebar) --------------------
    @staticmethod
    def get_secret(name: str) -> Optional[str]:
        return config.get_secret(name)

    @staticmethod
    def set_secret(name: str, value: str) -> None:
        config.set_secret(name, value)

    def has_binance(self) -> bool:
        return bool(config.get_secret(config.SECRET_BINANCE_KEY)
                    and config.get_secret(config.SECRET_BINANCE_SECRET))

    def groww_csv_path(self) -> Optional[Path]:
        if self.cfg.groww_csv_paths:
            return self.cfg.groww_csv_paths[0]
        return DEFAULT_GROWW_CSV if DEFAULT_GROWW_CSV.exists() else None

    # --- source assembly -----------------------------------------------------
    def build_sources(self):
        sources = []
        # "csv" mode intentionally ignores the Binance API even if a key is stored.
        if self.has_binance() and self.cfg.source_mode != "csv":
            sources.append(BinanceSource(
                config.get_secret(config.SECRET_BINANCE_KEY),
                config.get_secret(config.SECRET_BINANCE_SECRET),
            ))
        paths = list(self.cfg.groww_csv_paths)
        if not paths and DEFAULT_GROWW_CSV.exists():
            paths = [DEFAULT_GROWW_CSV]
        if paths:
            sources.append(GrowwCsvSource(paths))
        return sources

    def _fetch_all(self, sources) -> tuple[list, list[SourceResult]]:
        holdings, results = [], []
        for src in sources:
            try:
                hs = src.fetch_holdings()
                holdings.extend(hs)
                results.append(SourceResult(src.name, True, hs))
            except Exception as exc:  # noqa: BLE001 - isolate per-source failures
                # Redact so a signed-request URL (signature/query) never reaches
                # logs, the console, or the written report.
                safe = redact(str(exc))
                log.warning("Source %s failed: %s", src.name, safe)
                results.append(SourceResult(src.name, False, [], error=safe))
        return holdings, results

    def _resolve_fx(self, holdings) -> FxRate:
        need_fx = any(h.currency == "USD" for h in holdings)
        try:
            return get_usd_inr(self.cfg.fx_source, self.cfg.manual_usd_inr)
        except Exception as exc:  # noqa: BLE001
            if need_fx:
                raise PortfolioError(
                    f"You hold crypto but the USD->INR rate is unavailable: {exc}"
                ) from exc
            log.warning("FX unavailable but no USD holdings; continuing. (%s)", exc)
            return FxRate("USD/INR", 1.0, "unavailable",
                          datetime.now().astimezone().isoformat(timespec="seconds"))

    # --- high-level operations ----------------------------------------------
    def load_portfolio(self, *, live_prices: bool = False) -> PortfolioResult:
        """Fetch + value everything. Never raises on a single-source failure.

        `live_prices` refreshes INR stock holdings with today's yfinance prices
        (used by the daily digest so the portfolio is valued at current prices).
        """
        generated_at = datetime.now().astimezone()
        holdings, results = self._fetch_all(self.build_sources())
        if live_prices:
            from .prices import refresh_holding_prices
            refresh_holding_prices(holdings)
        fx = self._resolve_fx(holdings)
        df = build_dataframe(holdings, fx)
        cat_df = allocation_by_category(df)
        return PortfolioResult(df, cat_df, fx, results, generated_at)

    def score(self, portfolio: PortfolioResult) -> pd.DataFrame:
        from .scoring.engine import score_stocks, to_dataframe  # lazy: optional extra

        items: list[tuple[str, str | None]] = []
        if portfolio.has_holdings:
            stocks = portfolio.df[portfolio.df["category"] == CATEGORY_STOCK]
            items.extend((str(r["symbol"]), str(r["asset"])) for _, r in stocks.iterrows())
        items.extend((sym, None) for sym in self.cfg.score_watchlist)
        if not items:
            return to_dataframe([])
        return to_dataframe(score_stocks(items, self.cfg))

    def execute_pipeline(self, *, score: bool = True, send: bool = True,
                         dry_run: bool = False, no_alerts: bool = False) -> PipelineResult:
        """Full run: load -> score -> alerts -> report -> (send). Returns everything."""
        portfolio = self.load_portfolio()
        scores_df = self.score(portfolio) if score else None

        current = state_mod.build_snapshot(portfolio.df, portfolio.cat_df, portfolio.generated_at)
        previous = state_mod.load_last_snapshot(self.cfg.state_dir)
        alerts = [] if no_alerts else detect_alerts(current, previous, self.cfg, scores_df)

        paths = report.write_reports(
            portfolio.df, portfolio.cat_df, portfolio.fx, portfolio.source_results, self.cfg,
            generated_at=portfolio.generated_at, alerts=alerts, scores_df=scores_df,
        )

        sent = {"email": False, "telegram": False}
        if not dry_run:
            state_mod.save_snapshot(self.cfg.state_dir, current)
            if alerts and send:
                body = "Stockerr alerts:\n\n- " + "\n- ".join(alerts)
                sent["email"] = send_email(self.cfg, "Stockerr alerts", body)
                sent["telegram"] = send_telegram(self.cfg, body)

        return PipelineResult(portfolio, scores_df, alerts, paths, sent)


# Category labels the UI reuses so wording stays consistent.
CATEGORY_LABELS = {
    CATEGORY_STOCK: "Direct Equity",
    CATEGORY_MF: "Mutual Funds",
    CATEGORY_CRYPTO: "Crypto (Bitcoin)",
}
