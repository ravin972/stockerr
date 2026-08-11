"""Daily digest: fresh prices -> re-score -> "what changed" -> Telegram + Email.

This automates the ANALYSIS, not the decision. The digest gives evidence (scores,
the 'why', day-over-day changes, alerts) so the user decides. It never says "buy
X", never guarantees profit, and never trades.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from . import report
from .alerts import state as pstate
from .alerts.detect import detect_alerts
from .alerts.email import send_email
from .alerts.telegram import send_telegram
from .config import Config
from .engine import StockerrEngine

log = logging.getLogger("stockerr.digest")

DIGEST_STATE_FILE = "last-digest.json"
DISCLAIMER = ("Decision support, NOT advice. Scores are heuristic and partial; do your own "
              "diligence. Read-only — you place every trade yourself.")


# --- day-over-day state -------------------------------------------------------
def load_digest_state(state_dir: Path) -> Optional[dict]:
    path = state_dir / DIGEST_STATE_FILE
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def save_digest_state(state_dir: Path, portfolio, scores_df) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    scores = {}
    if scores_df is not None and not scores_df.empty:
        for _, r in scores_df.iterrows():
            c = r.get("confidence")
            if c is not None and not pd.isna(c):
                scores[str(r["symbol"])] = float(c)
    blob = {
        "generated_at": portfolio.generated_at.isoformat(timespec="seconds"),
        "net_worth": round(portfolio.net_worth, 2),
        "scores": scores,
    }
    (state_dir / DIGEST_STATE_FILE).write_text(json.dumps(blob, indent=2), encoding="utf-8")


# --- digest text --------------------------------------------------------------
def _signal(conf: float) -> str:
    if conf > 75:
        return "Strong Buy"
    if conf >= 50:
        return "Hold"
    return "Avoid"


def _delta_tag(cur: float, prev: Optional[float]) -> str:
    if prev is None:
        return ""
    d = cur - prev
    if abs(d) < 1:
        return ""
    return f" ({'+' if d > 0 else ''}{d:.0f})"


def build_digest(portfolio, scores_df, prev: Optional[dict], alerts: list[str],
                 generated_at: datetime, top_n: int = 8) -> str:
    prev = prev or {}
    lines = [f"Stockerr daily digest - {generated_at:%Y-%m-%d}"]

    nw = portfolio.net_worth
    nw_line = f"Net worth: Rs.{nw:,.0f}"
    prev_nw = prev.get("net_worth")
    if prev_nw:
        pct = (nw - prev_nw) / prev_nw * 100 if prev_nw else 0.0
        nw_line += f" ({'+' if pct >= 0 else ''}{pct:.1f}% since last)"
    lines.append(nw_line)

    cats = portfolio.by_category
    if cats and nw:
        lines.append("Allocation: " + ", ".join(f"{k} {v / nw * 100:.0f}%" for k, v in cats.items()))
    lines.append("")

    prev_scores = prev.get("scores", {})
    if scores_df is not None and not scores_df.empty:
        lines.append("Holdings (score + why):")
        movers = []
        for _, r in scores_df.head(top_n).iterrows():
            conf = r.get("confidence")
            if conf is None or pd.isna(conf):
                continue
            prev_c = prev_scores.get(str(r["symbol"]))
            lines.append(f"- {r['symbol']} {conf:.0f}{_delta_tag(conf, prev_c)} "
                         f"[{_signal(conf)}] - {r.get('why', '')}")
            if prev_c is not None and abs(conf - prev_c) >= 5:
                movers.append((r["symbol"], conf - prev_c))
        lines.append("")
        if movers:
            movers.sort(key=lambda x: abs(x[1]), reverse=True)
            lines.append("Biggest score changes: "
                         + ", ".join(f"{s} {'+' if d > 0 else ''}{d:.0f}" for s, d in movers[:5]))
            lines.append("")

    if alerts:
        lines.append("Alerts:")
        lines += [f"- {a}" for a in alerts]
        lines.append("")

    lines.append(f"- {DISCLAIMER}")
    return "\n".join(lines)


# --- orchestration ------------------------------------------------------------
def run_digest(cfg: Config, *, send: bool = True, dry_run: bool = False,
               live_prices: bool = True) -> tuple[str, dict, dict]:
    """Build and (optionally) send the daily digest. Returns (text, report_paths, sent)."""
    engine = StockerrEngine(cfg)
    portfolio = engine.load_portfolio(live_prices=live_prices)
    scores_df = engine.score(portfolio)

    current_snap = pstate.build_snapshot(portfolio.df, portfolio.cat_df, portfolio.generated_at)
    prev_snap = pstate.load_last_snapshot(cfg.state_dir)
    alerts = detect_alerts(current_snap, prev_snap, cfg, scores_df)

    prev_digest = load_digest_state(cfg.state_dir)
    text = build_digest(portfolio, scores_df, prev_digest, alerts, portfolio.generated_at)

    paths = report.write_reports(
        portfolio.df, portfolio.cat_df, portfolio.fx, portfolio.source_results, cfg,
        generated_at=portfolio.generated_at, alerts=alerts, scores_df=scores_df)

    sent = {"telegram": False, "email": False}
    if not dry_run:
        pstate.save_snapshot(cfg.state_dir, current_snap)
        save_digest_state(cfg.state_dir, portfolio, scores_df)
        if send:
            subject = f"Stockerr digest {portfolio.generated_at:%Y-%m-%d}"
            sent["telegram"] = send_telegram(cfg, text)
            sent["email"] = send_email(cfg, subject, text)
    return text, paths, sent
