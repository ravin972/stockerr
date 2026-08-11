"""Stockerr command-line entry point.

    stockerr init                 store secrets (read-only keys, tokens) in keyring
    stockerr run [--score]        fetch -> merge -> (score) -> report -> alerts
    stockerr score                score your holdings + watchlist only

`run` flags: --score  --analyze  --no-alerts  --dry-run  --env PATH

All orchestration lives in `StockerrEngine` (engine.py); this module is a thin CLI
around it so the CLI and the Streamlit UI share one code path.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from . import __version__, config
from .engine import PortfolioError, StockerrEngine
from .logging_setup import setup_logging
from .merge import total_net_worth

log = logging.getLogger("stockerr.cli")


# --- optional Claude analysis -------------------------------------------------

def _analyze(cfg: config.Config, md_path, generated_at: datetime) -> None:
    key = config.get_secret(config.SECRET_ANTHROPIC_KEY)
    if not key:
        print("  --analyze: no Anthropic key stored; open the .md in a Claude Project instead.")
        return
    try:
        import anthropic
    except Exception:
        print("  --analyze: anthropic not installed (pip install 'stockerr[analyze]').")
        return
    try:
        content = md_path.read_text(encoding="utf-8")
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": content}],
        )
        out = "".join(getattr(b, "text", "") for b in msg.content)
        out_path = cfg.exports_dir / f"analysis_{generated_at.strftime('%Y-%m-%d')}.md"
        out_path.write_text(out, encoding="utf-8")
        print(f"  --analyze: wrote {out_path.name}")
    except Exception as exc:  # noqa: BLE001
        print(f"  --analyze failed: {exc}")


# --- commands -----------------------------------------------------------------

def cmd_run(args) -> int:
    cfg = config.load_config(args.env)
    setup_logging(cfg.log_level, log_dir=cfg.state_dir)
    engine = StockerrEngine(cfg)

    if not engine.build_sources():
        print("No sources configured. Run `stockerr init` (Binance) and/or set "
              "STOCKERR_GROWW_CSV in .env (or add data/groww_holdings.csv).", file=sys.stderr)
        return 2

    try:
        result = engine.execute_pipeline(
            score=args.score, send=not args.dry_run,
            dry_run=args.dry_run, no_alerts=args.no_alerts,
        )
    except PortfolioError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    p = result.portfolio
    _print_summary(p.df, p.cat_df, result.scores_df, result.alerts,
                   result.report_paths, p.source_results)
    if args.analyze:
        _analyze(cfg, result.report_paths["markdown"], p.generated_at)
    return 0


def cmd_score(args) -> int:
    cfg = config.load_config(args.env)
    setup_logging(cfg.log_level, log_dir=cfg.state_dir)
    engine = StockerrEngine(cfg)

    try:
        portfolio = engine.load_portfolio()
    except PortfolioError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    scores_df = engine.score(portfolio)
    if scores_df.empty:
        print("Nothing to score. Add STOCKERR_SCORE_WATCHLIST or Groww stock holdings.")
        return 0
    print("\nConfidence scores (0-100 screen — NOT advice):")
    print(scores_df.to_string(index=False))
    print("\nFundamental x0.50 + Technical x0.30 + Sentiment x0.20 "
          "(reweighted when a sub-score is unavailable).")
    return 0


def cmd_discover(args) -> int:
    cfg = config.load_config(args.env)
    setup_logging(cfg.log_level, log_dir=cfg.state_dir)
    from .discovery.engine import DiscoveryEngine

    engine = DiscoveryEngine(cfg)

    if args.target == "stocks":
        from .discovery import DISCOVERY_DISCLAIMER
        csv = [args.csv] if args.csv else None
        df = engine.discover_stocks(csv, enrich_technical=args.enrich, top_n=args.top)
        empty_msg = ("Nothing to screen. Export a Screener.in screen CSV and pass --csv "
                     "(or set STOCKERR_SCREENER_CSV).")
        title, disclaimer, score_col = "Buffett-style stock screen", DISCOVERY_DISCLAIMER, "confidence"
    elif args.target == "ipo":
        from .discovery.ipo import IPO_DISCLAIMER
        df = engine.discover_ipos()
        empty_msg = ("No IPO data. Add an IPO Guru key (`stockerr init`) or `pip install nse`.")
        title, disclaimer, score_col = "Upcoming IPOs", IPO_DISCLAIMER, "fund_score"
    elif args.target == "mf":
        from .discovery.mutual_funds import MF_DISCLAIMER
        df = engine.discover_mutual_funds()
        empty_msg = "No funds. Set STOCKERR_MF_WATCHLIST to AMFI scheme codes (comma separated)."
        title, disclaimer, score_col = "Mutual fund screen", MF_DISCLAIMER, "score"
    elif args.target == "crypto":
        from .discovery.crypto import CRYPTO_DISCLAIMER
        df = engine.discover_crypto()
        empty_msg = "No coins. Set STOCKERR_CRYPTO_WATCHLIST to Binance USDT symbols (e.g. ETHUSDT)."
        title, disclaimer, score_col = "Crypto momentum screen", CRYPTO_DISCLAIMER, "score"
    else:  # pragma: no cover - argparse restricts choices
        print(f"unknown target {args.target}", file=sys.stderr)
        return 2

    if df.empty:
        print(empty_msg)
        return 0
    if args.min_score is not None and score_col in df.columns:
        df = df[df[score_col].fillna(-1) >= args.min_score]

    print(f"\n{title} (NOT advice):")
    print(df.to_string(index=False))
    print(f"\n{disclaimer}")
    return 0


def cmd_doctor(args) -> int:
    cfg = config.load_config(args.env)
    setup_logging(cfg.log_level, log_dir=cfg.state_dir)
    from .diagnostics import run_diagnostics

    marks = {"OK": "[OK]", "WARN": "[! ]", "MISSING": "[--]", "FAIL": "[X ]"}
    print("\nStockerr doctor — data-source self-check:\n")
    for name, status, detail in run_diagnostics(cfg):
        print(f"  {marks.get(status, status):4} {name:<24} {detail}")
    print("\n  [OK] good   [! ] check this   [--] not configured   [X ] failed")
    return 0


def cmd_digest(args) -> int:
    cfg = config.load_config(args.env)
    setup_logging(cfg.log_level, log_dir=cfg.state_dir)
    from .digest import run_digest

    text, paths, sent = run_digest(
        cfg, send=not args.no_send, dry_run=args.dry_run,
        live_prices=not args.no_live_prices)
    print(text)
    if not args.dry_run and not args.no_send:
        print(f"\nSent -> Telegram: {'ok' if sent['telegram'] else 'no'} | "
              f"Email: {'ok' if sent['email'] else 'no'}")
    print(f"\nReport: {paths.get('markdown')}")
    return 0


def cmd_telegram_test(args) -> int:
    cfg = config.load_config(args.env)
    setup_logging(cfg.log_level, log_dir=cfg.state_dir)
    from .alerts.telegram import detect_chat_id, send_message

    token = config.get_secret(config.SECRET_TELEGRAM_TOKEN)
    if not token:
        print("No Telegram bot token stored. Run `stockerr init` (or set it in .env).",
              file=sys.stderr)
        return 2

    detected = detect_chat_id(token)
    if not detected:
        print("No messages found for your bot. Open your bot in Telegram, send it ANY "
              "message, then re-run `stockerr telegram-test`.")
        return 1

    chat_id, who = detected
    ok, err = send_message(token, chat_id,
                           "✅ Stockerr connected — you'll get your daily digest here.")
    if ok:
        print(f"Test message sent to '{who}' (chat id: {chat_id}). Check Telegram!")
    else:
        print(f"Detected chat id {chat_id} but send failed: {err}", file=sys.stderr)

    stored = config.get_secret(config.SECRET_TELEGRAM_CHAT)
    if stored != chat_id:
        print(f"\n[!] Your configured chat id ({stored or 'none'}) differs from the correct "
              f"one ({chat_id}).")
        print("    Fix it so digests deliver — put this line in your .env:")
        print(f"        STOCKERR_TELEGRAM_CHAT_ID={chat_id}")
        print(f"    (or re-run `stockerr init` and enter {chat_id} as the chat id)")
    elif ok:
        print("\nYour configured chat id is correct — digests will deliver. ✅")
    return 0 if ok else 1


def cmd_init(args) -> int:
    from .secrets_setup import run_init
    run_init()
    return 0


def _print_summary(df, cat_df, scores_df, alerts, paths, results) -> None:
    print("\n=== Stockerr ===")
    for r in results:
        state = "OK" if r.ok else f"FAILED ({r.error})"
        print(f"  source {r.source}: {state}"
              + (f", {len(r.holdings)} holdings" if r.ok else ""))
    print(f"\nNet worth: Rs.{total_net_worth(df):,.2f}")
    if not cat_df.empty:
        print("Allocation:")
        for _, r in cat_df.iterrows():
            print(f"  {r['category']:<8} Rs.{r['value_inr']:>14,.2f}  ({r['alloc_pct']:.1f}%)")
    if scores_df is not None and not scores_df.empty:
        print("\nTop confidence scores:")
        print(scores_df.head(5).to_string(index=False))
    if alerts:
        print("\nAlerts:")
        for a in alerts:
            print(f"  ! {a}")
    print("\nWrote:")
    for kind, p in paths.items():
        print(f"  {kind:<9} {p}")
    print("\nTip: drag the .md file into a Claude Project for deep analysis.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stockerr", description="Read-only portfolio analysis & alerts.")
    p.add_argument("--version", action="version", version=f"stockerr {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="store secrets in the OS keyring")
    p_init.set_defaults(func=cmd_init, env=".env")

    p_doctor = sub.add_parser("doctor", help="self-check every data source")
    p_doctor.add_argument("--env", default=".env", help="path to .env file")
    p_doctor.set_defaults(func=cmd_doctor)

    p_tg = sub.add_parser("telegram-test", help="auto-detect your chat id + send a test message")
    p_tg.add_argument("--env", default=".env", help="path to .env file")
    p_tg.set_defaults(func=cmd_telegram_test)

    p_digest = sub.add_parser("digest", help="daily digest: refresh prices, re-score, notify")
    p_digest.add_argument("--no-send", action="store_true", help="don't send Telegram/email")
    p_digest.add_argument("--no-live-prices", action="store_true",
                          help="use CSV prices instead of live yfinance")
    p_digest.add_argument("--dry-run", action="store_true", help="don't send or save state")
    p_digest.add_argument("--env", default=".env", help="path to .env file")
    p_digest.set_defaults(func=cmd_digest)

    p_run = sub.add_parser("run", help="fetch, merge, report, and alert")
    p_run.add_argument("--score", action="store_true", help="also run the confidence engine")
    p_run.add_argument("--analyze", action="store_true", help="also call Claude for a written analysis")
    p_run.add_argument("--no-alerts", action="store_true", help="skip alert detection/sending")
    p_run.add_argument("--dry-run", action="store_true", help="don't send alerts or save snapshot")
    p_run.add_argument("--env", default=".env", help="path to .env file")
    p_run.set_defaults(func=cmd_run)

    p_score = sub.add_parser("score", help="score holdings + watchlist only")
    p_score.add_argument("--env", default=".env", help="path to .env file")
    p_score.set_defaults(func=cmd_score)

    p_disc = sub.add_parser("discover", help="screen the market for ideas (stocks)")
    p_disc.add_argument("target", choices=["stocks", "mf", "crypto", "ipo"],
                        help="what to screen (only 'stocks' is built so far)")
    p_disc.add_argument("--csv", help="Screener.in screen CSV (else STOCKERR_SCREENER_CSV)")
    p_disc.add_argument("--enrich", action="store_true",
                        help="add yfinance technicals for the top rows (network)")
    p_disc.add_argument("--top", type=int, default=20, help="rows to technical-enrich")
    p_disc.add_argument("--min-score", type=float, default=None,
                        help="only show confidence >= this")
    p_disc.add_argument("--env", default=".env", help="path to .env file")
    p_disc.set_defaults(func=cmd_discover)

    return p


def main(argv: list[str] | None = None) -> int:
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)   # quiet yfinance/numpy noise
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
