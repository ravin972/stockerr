"""Stockerr v1 — Streamlit dashboard.

A wide, dark-mode frontend over the read-only StockerrEngine: unified net worth,
allocation drift vs a target, and the AI Confidence Scoring grid. It visualizes
and scores only — it never places trades.

Run:  uv run --extra ui streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make src/ importable when running `streamlit run app.py` without an editable install.
sys.path.insert(0, str(Path(__file__).parent / "src"))

import os

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from dotenv import set_key  # noqa: E402

from stockerr import config  # noqa: E402
from stockerr.config import (  # noqa: E402
    SECRET_ANTHROPIC_KEY,
    SECRET_BINANCE_KEY,
    SECRET_BINANCE_SECRET,
    SECRET_EMAIL_PASSWORD,
    SECRET_EMAIL_USER,
    SECRET_TELEGRAM_CHAT,
    SECRET_TELEGRAM_TOKEN,
)
from stockerr.discovery import DISCOVERY_DISCLAIMER  # noqa: E402
from stockerr.discovery.engine import DiscoveryEngine  # noqa: E402
from stockerr.engine import PortfolioError, StockerrEngine  # noqa: E402
from stockerr.models import CATEGORY_CRYPTO, CATEGORY_MF, CATEGORY_STOCK  # noqa: E402

# --- constants ----------------------------------------------------------------
st.set_page_config(page_title="Stockerr", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")

DATA_CSV = Path("data/groww_holdings.csv")
SCREENER_CSV = Path("data/screener_screen.csv")
ENV_PATH = Path(".env")
DEFAULT_TARGET = {CATEGORY_STOCK: 50.0, CATEGORY_MF: 30.0, CATEGORY_CRYPTO: 20.0}
DRIFT_LIMIT = 5.0

ACCENTS = {CATEGORY_STOCK: "#4c8bf5", CATEGORY_MF: "#22b07d",
           CATEGORY_CRYPTO: "#f5a623", "total": "#a06bff"}
CARD_TITLES = {CATEGORY_STOCK: "Direct Equity", CATEGORY_MF: "Mutual Funds",
               CATEGORY_CRYPTO: "Crypto (Bitcoin)"}

GREEN, YELLOW, RED, MUTED = "#0e5c2f", "#7a5c00", "#6e1414", "#333"


def _wide_kwargs() -> dict:
    """`width='stretch'` on new Streamlit, else the older `use_container_width`."""
    try:
        major_minor = tuple(int(x) for x in st.__version__.split(".")[:2])
    except Exception:
        major_minor = (0, 0)
    return {"width": "stretch"} if major_minor >= (1, 43) else {"use_container_width": True}


_WIDE = _wide_kwargs()


# --- styling ------------------------------------------------------------------
def inject_css() -> None:
    st.markdown(
        """
        <style>
          .stApp { background-color: #0e1117; }
          .metric-card {
            background: #161b26; border-radius: 12px; padding: 18px 20px;
            border-top: 3px solid #4c8bf5; box-shadow: 0 2px 10px rgba(0,0,0,.35);
          }
          .metric-label { color:#9aa4b2; font-size:.85rem; text-transform:uppercase;
            letter-spacing:.05em; margin-bottom:6px; }
          .metric-value { color:#f5f7fa; font-size:1.7rem; font-weight:700; }
          .section-title { color:#e6e9ef; font-size:1.1rem; font-weight:600;
            margin:.2rem 0 .6rem; }
          .drift-banner {
            background:#3a1414; border:1px solid #6e1414; color:#ffb4b4;
            padding:12px 16px; border-radius:10px; font-weight:600;
            animation: blink 1.1s ease-in-out infinite;
          }
          .ok-banner {
            background:#0e2a1a; border:1px solid #14502f; color:#7ee0a8;
            padding:12px 16px; border-radius:10px; font-weight:600;
          }
          @keyframes blink { 0%,100%{opacity:1;} 50%{opacity:.45;} }
        </style>
        """,
        unsafe_allow_html=True,
    )


# --- config persistence -------------------------------------------------------
def save_env(key: str, value: str) -> None:
    """Persist a NON-secret setting to .env and the live process env."""
    if not ENV_PATH.exists():
        ENV_PATH.touch()
    set_key(str(ENV_PATH), key, value)
    os.environ[key] = value


def save_secret(name: str, value: str) -> bool:
    try:
        StockerrEngine.set_secret(name, value)
        return True
    except Exception as exc:  # noqa: BLE001
        st.sidebar.error(f"Could not store secret ({name}): {exc}")
        return False


def secret_status(name: str) -> str:
    return "✅ set" if StockerrEngine.get_secret(name) else "— not set"


# --- sidebar ------------------------------------------------------------------
def render_sidebar(engine: StockerrEngine) -> None:
    st.sidebar.header("⚙️ Integration Setup")

    mode_label = st.sidebar.radio(
        "Data mode",
        ["CSV Mode", "Live API Mode"],
        index=0 if engine.cfg.source_mode == "csv" else 1,
        help="CSV Mode uses only your Groww export. Live API Mode also pulls Binance.",
    )
    new_mode = "csv" if mode_label == "CSV Mode" else "live"
    if new_mode != engine.cfg.source_mode:
        save_env("STOCKERR_SOURCE_MODE", new_mode)
        st.session_state.pop("portfolio", None)
        st.rerun()

    # Groww CSV upload (always available; the safe, MF-inclusive route).
    with st.sidebar.expander("📄 Groww holdings CSV", expanded=not DATA_CSV.exists()):
        current = engine.groww_csv_path()
        st.caption(f"Current: {current if current else 'none'}")
        up = st.file_uploader("Upload / replace", type="csv", key="sb_csv")
        if up is not None:
            _save_groww_csv(up.getvalue())

    with st.sidebar.expander("🔑 Binance (read-only)", expanded=False):
        st.caption(f"Key {secret_status(SECRET_BINANCE_KEY)} · "
                   f"Secret {secret_status(SECRET_BINANCE_SECRET)}")
        st.info("Create the key with **Enable Reading only** — trading & withdrawals OFF.")
        b_key = st.text_input("API key", type="password", key="b_key")
        b_secret = st.text_input("API secret", type="password", key="b_secret")

    with st.sidebar.expander("📨 Telegram", expanded=False):
        st.caption(f"Token {secret_status(SECRET_TELEGRAM_TOKEN)} · "
                   f"Chat {secret_status(SECRET_TELEGRAM_CHAT)}")
        tg_enabled = st.checkbox("Enable Telegram alerts", value=engine.cfg.telegram_enabled)
        tg_token = st.text_input("Bot token", type="password", key="tg_token")
        tg_chat = st.text_input("Chat id", type="password", key="tg_chat")

    with st.sidebar.expander("✉️ Email (SMTP)", expanded=False):
        st.caption(f"User {secret_status(SECRET_EMAIL_USER)} · "
                   f"Password {secret_status(SECRET_EMAIL_PASSWORD)}")
        em_enabled = st.checkbox("Enable email alerts", value=engine.cfg.email_enabled)
        em_host = st.text_input("SMTP host", value=engine.cfg.email_smtp_host)
        em_port = st.number_input("SMTP port", value=int(engine.cfg.email_smtp_port), step=1)
        em_from = st.text_input("From", value=engine.cfg.email_from)
        em_to = st.text_input("To", value=engine.cfg.email_to)
        em_user = st.text_input("SMTP username", type="password", key="em_user")
        em_pass = st.text_input("SMTP app password", type="password", key="em_pass")

    with st.sidebar.expander("🎯 Target allocation (%)", expanded=False):
        tgt = {**DEFAULT_TARGET, **engine.cfg.target_allocation}
        t_stock = st.number_input("Stocks", value=float(tgt[CATEGORY_STOCK]), step=1.0)
        t_mf = st.number_input("Mutual funds", value=float(tgt[CATEGORY_MF]), step=1.0)
        t_crypto = st.number_input("Crypto", value=float(tgt[CATEGORY_CRYPTO]), step=1.0)

    with st.sidebar.expander("🧠 Sentiment (Anthropic)", expanded=False):
        st.caption(f"Key {secret_status(SECRET_ANTHROPIC_KEY)}")
        an_key = st.text_input("Anthropic API key", type="password", key="an_key")

    if st.sidebar.button("💾 Save settings", **_WIDE, type="primary"):
        # Secrets -> keyring (only if a new value was typed).
        for name, val in [
            (SECRET_BINANCE_KEY, b_key), (SECRET_BINANCE_SECRET, b_secret),
            (SECRET_TELEGRAM_TOKEN, tg_token), (SECRET_TELEGRAM_CHAT, tg_chat),
            (SECRET_EMAIL_USER, em_user), (SECRET_EMAIL_PASSWORD, em_pass),
            (SECRET_ANTHROPIC_KEY, an_key),
        ]:
            if val:
                save_secret(name, val)
        # Non-secret toggles -> .env
        save_env("STOCKERR_TELEGRAM_ENABLED", str(tg_enabled).lower())
        save_env("STOCKERR_EMAIL_ENABLED", str(em_enabled).lower())
        save_env("STOCKERR_EMAIL_SMTP_HOST", em_host)
        save_env("STOCKERR_EMAIL_SMTP_PORT", str(int(em_port)))
        save_env("STOCKERR_EMAIL_FROM", em_from)
        save_env("STOCKERR_EMAIL_TO", em_to)
        save_env("STOCKERR_TARGET_ALLOCATION",
                 f"stock={t_stock:g},mf={t_mf:g},crypto={t_crypto:g}")
        st.session_state.pop("portfolio", None)
        st.sidebar.success("Saved.")
        st.rerun()


def _save_groww_csv(data: bytes) -> None:
    DATA_CSV.parent.mkdir(parents=True, exist_ok=True)
    DATA_CSV.write_bytes(data)
    save_env("STOCKERR_GROWW_CSV", str(DATA_CSV))
    st.session_state.pop("portfolio", None)
    st.success(f"Saved to {DATA_CSV}. Reloading…")
    st.rerun()


# --- onboarding (no data at all) ----------------------------------------------
def render_onboarding() -> None:
    st.subheader("Let's get your first data source connected")
    st.write("No **Groww holdings CSV** found and no **Binance** key stored yet. "
             "Upload your Groww holdings export to begin — stocks *and* mutual funds are supported.")
    up = st.file_uploader("Upload Groww holdings CSV (stocks / mutual funds)", type="csv")
    if up is not None:
        _save_groww_csv(up.getvalue())
    st.info("Prefer Binance too? Open **⚙️ Integration Setup → Binance** in the sidebar and add a "
            "**read-only** key, then switch to *Live API Mode*.")


# --- portfolio loading --------------------------------------------------------
def load_into_state(engine: StockerrEngine, force: bool = False) -> None:
    if force:
        st.session_state.pop("portfolio", None)
    if "portfolio" in st.session_state:
        return
    with st.spinner("Loading portfolio…"):
        try:
            st.session_state["portfolio"] = engine.load_portfolio()
        except PortfolioError as exc:
            st.error(str(exc))
            st.stop()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not load portfolio: {exc}")
            st.stop()


# --- UI pieces ----------------------------------------------------------------
def render_metric_cards(portfolio) -> None:
    cols = st.columns(4)
    order = [CATEGORY_STOCK, CATEGORY_MF, CATEGORY_CRYPTO]
    for col, cat in zip(cols[:3], order):
        _card(col, CARD_TITLES[cat], portfolio.category_value(cat), ACCENTS[cat])
    _card(cols[3], "Combined Net Worth", portfolio.net_worth, ACCENTS["total"])


def _card(col, label: str, value: float, accent: str) -> None:
    col.markdown(
        f'<div class="metric-card" style="border-top-color:{accent}">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value">₹{value:,.0f}</div></div>',
        unsafe_allow_html=True,
    )


def render_allocation(portfolio, target: dict) -> None:
    st.markdown('<div class="section-title">Portfolio Drift & Allocation</div>',
                unsafe_allow_html=True)
    by_cat = portfolio.by_category
    total = portfolio.net_worth
    if total <= 0:
        st.info("No valued holdings yet.")
        return

    labels = [CARD_TITLES.get(c, c) for c in by_cat]
    values = list(by_cat.values())
    colors = [ACCENTS.get(c, "#888") for c in by_cat]
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.55,
                           marker=dict(colors=colors), textinfo="label+percent",
                           sort=False))
    fig.update_layout(template="plotly_dark", showlegend=False,
                      margin=dict(t=10, b=10, l=10, r=10), height=320,
                      paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, **_WIDE)

    # Current vs target + drift.
    rows, breaches = [], []
    for cat in [CATEGORY_STOCK, CATEGORY_MF, CATEGORY_CRYPTO]:
        cur_pct = (by_cat.get(cat, 0.0) / total * 100) if total else 0.0
        tgt_pct = float(target.get(cat, 0.0))
        drift = cur_pct - tgt_pct
        rows.append({"Category": CARD_TITLES[cat], "Current %": round(cur_pct, 1),
                     "Target %": round(tgt_pct, 1), "Drift": round(drift, 1)})
        if abs(drift) > DRIFT_LIMIT:
            breaches.append(f"{CARD_TITLES[cat]} {drift:+.1f} pts")
    st.dataframe(pd.DataFrame(rows), **_WIDE, hide_index=True)

    if breaches:
        st.markdown(
            f'<div class="drift-banner">⚠️ Allocation drift &gt; {DRIFT_LIMIT:.0f} pts: '
            f'{", ".join(breaches)} — consider rebalancing.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="ok-banner">✓ Allocation within target thresholds.</div>',
                    unsafe_allow_html=True)


def _signal(score) -> str:
    if score is None or pd.isna(score):
        return "N/A"
    if score > 75:
        return "Strong Buy"
    if score >= 50:
        return "Hold"
    return "Avoid"


def _conf_style(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return f"background-color:{MUTED};color:#aaa"
    if v > 75:
        return f"background-color:{GREEN};color:#fff"
    if v >= 50:
        return f"background-color:{YELLOW};color:#fff"
    return f"background-color:{RED};color:#fff"


def _signal_style(s):
    return {
        "Strong Buy": f"background-color:{GREEN};color:#fff",
        "Bullish": f"background-color:{GREEN};color:#fff",
        "Hold": f"background-color:{YELLOW};color:#fff",
        "Watch": f"background-color:{YELLOW};color:#fff",
        "Neutral": f"background-color:{YELLOW};color:#fff",
        "Avoid": f"background-color:{RED};color:#fff",
        "Bearish": f"background-color:{RED};color:#fff",
        "Insufficient": f"background-color:{MUTED};color:#aaa",
    }.get(s, f"background-color:{MUTED};color:#aaa")


def render_scores(engine: StockerrEngine) -> None:
    st.markdown('<div class="section-title">AI Confidence Scoring</div>', unsafe_allow_html=True)
    st.caption("0–100 screen: Fundamentals (PE, D/E, ROE, ROCE, FCF) × Technicals (EMA, RSI) × "
               "Sentiment. **Decision support, not advice.**")

    if st.button("⚡ Compute confidence scores", **_WIDE):
        with st.spinner("Scoring — fundamentals + technicals (yfinance) + sentiment (Claude)…"):
            try:
                st.session_state["scores"] = engine.score(st.session_state["portfolio"])
            except Exception as exc:  # noqa: BLE001
                st.error(f"Scoring failed: {exc}")

    scores = st.session_state.get("scores")
    if scores is None:
        st.info("Click **Compute confidence scores** to rank your stocks + watchlist.")
        return
    if scores.empty:
        st.warning("No stocks to score. Add a watchlist (STOCKERR_SCORE_WATCHLIST) or Groww stocks.")
        return

    view = scores.copy()
    view.insert(2, "Signal", view["confidence"].apply(_signal))
    if "notes" in view.columns:
        view = view.drop(columns=["notes"])   # the "Why" column replaces it
    view = view.rename(columns={
        "symbol": "Symbol", "confidence": "Confidence", "fundamental": "Fund.",
        "technical": "Tech.", "sentiment": "Sent.", "why": "Why",
    })
    styler = (view.style
              .map(_conf_style, subset=["Confidence"])
              .map(_signal_style, subset=["Signal"])
              .format({c: "{:.0f}" for c in ["Confidence", "Fund.", "Tech.", "Sent."]},
                      na_rep="—"))
    st.dataframe(styler, **_WIDE, hide_index=True)
    st.caption("**Why** = the evidence behind the score (trend, valuation, debt). It explains the "
               "score — it is NOT a promise of profit. Always do your own diligence.")


def render_scan_button(engine: StockerrEngine) -> None:
    c1, c2, c3 = st.columns([2, 1, 1])
    push = c2.checkbox("Push to Telegram & Email", value=True,
                       help="Only sends when those channels are enabled + configured.")
    if c1.button("🔄 Trigger Manual Scan & Alert", type="primary", **_WIDE):
        with st.spinner("Running full pipeline — fetch, score, report, notify…"):
            try:
                res = engine.execute_pipeline(score=True, send=push, dry_run=False)
                st.session_state["portfolio"] = res.portfolio
                st.session_state["scores"] = res.scores_df
                st.session_state["last_pipeline"] = res
            except PortfolioError as exc:
                st.error(str(exc))
            except Exception as exc:  # noqa: BLE001
                st.error(f"Pipeline failed: {exc}")
    if c3.button("↻ Refresh data", **_WIDE):
        load_into_state(engine, force=True)
        st.session_state.pop("scores", None)
        st.rerun()


def render_pipeline_result() -> None:
    res = st.session_state.get("last_pipeline")
    if not res:
        return
    with st.expander("📣 Last scan result", expanded=True):
        if res.alerts:
            for a in res.alerts:
                st.warning(a)
        else:
            st.success("No new alerts — allocation and prices within thresholds.")
        st.write(f"Telegram: {'sent ✅' if res.sent.get('telegram') else 'not sent'} · "
                 f"Email: {'sent ✅' if res.sent.get('email') else 'not sent'}")
        md = res.report_paths.get("markdown")
        if md and Path(md).exists():
            st.download_button("⬇️ Download Markdown report", Path(md).read_bytes(),
                               file_name=Path(md).name, mime="text/markdown")


# --- Opportunities: stock screener -------------------------------------------
def _save_screener_csv(data: bytes) -> None:
    SCREENER_CSV.parent.mkdir(parents=True, exist_ok=True)
    SCREENER_CSV.write_bytes(data)
    save_env("STOCKERR_SCREENER_CSV", str(SCREENER_CSV))
    st.session_state.pop("screen_df", None)
    st.success(f"Saved to {SCREENER_CSV}. Reloading…")
    st.rerun()


def render_stock_screener(engine: StockerrEngine) -> None:
    st.caption("Rank a Screener.in *screen* export by **quality + valuation** (margin of safety) "
               "across small/mid/large cap. Decision support — **not advice.**")
    current = (engine.cfg.screener_csv_paths[0] if engine.cfg.screener_csv_paths
               else (SCREENER_CSV if SCREENER_CSV.exists() else None))

    with st.expander("📄 Screener.in CSV", expanded=current is None):
        st.caption(f"Current: {current if current else 'none'}")
        up = st.file_uploader("Upload a Screener.in screen export (CSV)", type="csv",
                              key="screener_csv")
        if up is not None:
            _save_screener_csv(up.getvalue())

    if current is None:
        st.info("Export a screen from **screener.in** with columns like PE, ROE, ROCE, "
                "Debt/Equity, Free cash flow, EPS, Book value, CMP, Market Cap — then upload it.")
        return

    c1, c2 = st.columns([1, 1])
    enrich = c1.checkbox("Add technicals to top 20 (slower · yfinance)", value=False)
    cap_filter = c2.selectbox("Cap filter", ["All", "Large", "Mid", "Small"])

    if st.button("🔎 Run screen", type="primary", **_WIDE):
        with st.spinner("Screening the universe…"):
            try:
                st.session_state["screen_df"] = DiscoveryEngine(engine.cfg).discover_stocks(
                    enrich_technical=enrich, top_n=20)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Screen failed: {exc}")

    df = st.session_state.get("screen_df")
    if df is None:
        st.info("Click **Run screen** to rank the universe.")
        return
    if df.empty:
        st.warning("No rows parsed from the CSV — check that it has a name/symbol column.")
        return

    view = df.copy()
    if cap_filter != "All":
        view = view[view["cap"] == cap_filter]
    view = view.rename(columns={
        "symbol": "Symbol", "name": "Name", "cap": "Cap", "confidence": "Confidence",
        "signal": "Signal", "quality": "Quality", "valuation": "Valuation",
        "technical": "Tech.", "consistency": "Consist.", "mos_pct": "MoS %",
        "rationale": "Rationale"})
    styler = (view.style
              .map(_conf_style, subset=["Confidence"])
              .map(_signal_style, subset=["Signal"])
              .format({c: "{:.0f}" for c in
                       ["Confidence", "Quality", "Valuation", "Tech.", "Consist."]}, na_rep="—")
              .format({"MoS %": "{:+.0f}%"}, na_rep="—"))
    st.dataframe(styler, **_WIDE, hide_index=True)
    st.caption(DISCOVERY_DISCLAIMER)


def _disc_grid(df, *, score_cols=(), signal_cols=(), pct_cols=(), int_cols=()) -> None:
    styler = df.style
    for c in list(score_cols) + list(signal_cols):
        if c in df.columns:
            fn = _conf_style if c in score_cols else _signal_style
            styler = styler.map(fn, subset=[c])
    fmt = {c: "{:.0f}" for c in list(score_cols) + list(int_cols) if c in df.columns}
    fmt.update({c: "{:+.1f}%" for c in pct_cols if c in df.columns})
    if fmt:
        styler = styler.format(fmt, na_rep="—")
    st.dataframe(styler, **_WIDE, hide_index=True)


def render_ipo_tab(engine: StockerrEngine) -> None:
    from stockerr.discovery.ipo import IPO_DISCLAIMER
    st.caption("Upcoming/open IPOs with a **fundamentals** score. Subscription is the strongest "
               "public signal; **GMP is unofficial**. NOT a profit prediction.")
    if st.button("🚀 Fetch upcoming IPOs", **_WIDE):
        with st.spinner("Fetching IPO calendar…"):
            try:
                st.session_state["ipo_df"] = DiscoveryEngine(engine.cfg).discover_ipos()
            except Exception as exc:  # noqa: BLE001
                st.error(f"IPO fetch failed: {exc}")
    df = st.session_state.get("ipo_df")
    if df is None:
        st.info("Click **Fetch upcoming IPOs**. Needs an IPO Guru key (`stockerr init`) "
                "or `pip install nse`.")
        return
    if df.empty:
        st.warning("No IPO data. Add an IPO Guru API key or install the `nse` library.")
        return
    _disc_grid(df, score_cols=["fund_score"], int_cols=["lot_size"])
    st.caption(IPO_DISCLAIMER)


def render_mf_tab(engine: StockerrEngine) -> None:
    from stockerr.discovery.mutual_funds import MF_DISCLAIMER
    st.caption("Rank funds by rolling-return **consistency** + risk-adjusted return + low expense. "
               "NOT advice.")
    if not engine.cfg.mf_watchlist:
        st.info("Add AMFI scheme codes to **STOCKERR_MF_WATCHLIST** in .env (e.g. 120503,119597).")
        return
    if st.button("🧺 Screen my funds", **_WIDE):
        with st.spinner("Fetching NAV history + scoring…"):
            try:
                st.session_state["mf_df"] = DiscoveryEngine(engine.cfg).discover_mutual_funds()
            except Exception as exc:  # noqa: BLE001
                st.error(f"MF screen failed: {exc}")
    df = st.session_state.get("mf_df")
    if df is None:
        st.info("Click **Screen my funds**.")
        return
    if df.empty:
        st.warning("No fund data — check the scheme codes.")
        return
    _disc_grid(df, score_cols=["score"], int_cols=["roll3_pos_pct"])
    st.caption(MF_DISCLAIMER)


def render_crypto_tab(engine: StockerrEngine) -> None:
    from stockerr.discovery.crypto import CRYPTO_DISCLAIMER
    st.caption("Momentum filter for **Binance USDT** pairs. Speculative — NOT advice.")
    if not engine.cfg.crypto_watchlist:
        st.info("Add Binance USDT symbols to **STOCKERR_CRYPTO_WATCHLIST** in .env "
                "(e.g. ETHUSDT,SOLUSDT).")
        return
    if st.button("🪙 Screen coins", **_WIDE):
        with st.spinner("Fetching Binance klines…"):
            try:
                st.session_state["crypto_df"] = DiscoveryEngine(engine.cfg).discover_crypto()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Crypto screen failed: {exc}")
    df = st.session_state.get("crypto_df")
    if df is None:
        st.info("Click **Screen coins**.")
        return
    if df.empty:
        st.warning("No coin data — check the symbols.")
        return
    _disc_grid(df, score_cols=["score"], signal_cols=["signal"],
               pct_cols=["rel_vs_btc_pct"], int_cols=["trend", "volatility_pct"])
    st.caption(CRYPTO_DISCLAIMER)


def _safe(render_fn, engine: StockerrEngine) -> None:
    """Isolate a section so one failure can't red-screen the whole dashboard."""
    try:
        render_fn(engine)
    except Exception as exc:  # noqa: BLE001
        st.error(f"This section failed to render: {exc}")
        st.caption("If you just updated the code, restart the Streamlit server "
                   "(Ctrl+C, then re-run) — it caches imported modules.")


def render_opportunities_tab(engine: StockerrEngine) -> None:
    st.markdown('<div class="section-title">Opportunities — discover what to buy</div>',
                unsafe_allow_html=True)
    t_stocks, t_mf, t_crypto, t_ipo = st.tabs(
        ["📈 Stocks", "🧺 Mutual Funds", "🪙 Crypto", "🚀 IPOs"])
    with t_stocks:
        _safe(render_stock_screener, engine)
    with t_mf:
        _safe(render_mf_tab, engine)
    with t_crypto:
        _safe(render_crypto_tab, engine)
    with t_ipo:
        _safe(render_ipo_tab, engine)


# --- Portfolio tab ------------------------------------------------------------
def render_portfolio_tab(engine: StockerrEngine) -> None:
    has_data = engine.has_binance() or engine.groww_csv_path() is not None
    if not has_data:
        render_onboarding()
        return

    render_scan_button(engine)
    render_pipeline_result()

    load_into_state(engine)
    portfolio = st.session_state["portfolio"]

    for fail in portfolio.failures:
        st.warning(f"Source '{fail.source}' unavailable: {fail.error}")

    render_metric_cards(portfolio)
    st.divider()

    target = {**DEFAULT_TARGET, **engine.cfg.target_allocation}
    left, right = st.columns(2)
    with left:
        render_allocation(portfolio, target)
    with right:
        render_scores(engine)

    st.caption(f"FX USD→INR {portfolio.fx.rate} ({portfolio.fx.source}) · "
               f"generated {portfolio.generated_at:%Y-%m-%d %H:%M}")


# --- main ---------------------------------------------------------------------
def main() -> None:
    inject_css()
    engine = StockerrEngine()  # reads .env / os.environ fresh each rerun

    render_sidebar(engine)
    st.title("📊 Stockerr — Unified Investment Dashboard")
    st.caption("Read-only. Visualizes, scores, and screens — never places trades.")

    tab_portfolio, tab_opportunities = st.tabs(["📈 Portfolio", "🔎 Opportunities"])
    with tab_portfolio:
        render_portfolio_tab(engine)
    with tab_opportunities:
        render_opportunities_tab(engine)


# Streamlit executes this script with __name__ == "__main__".
if __name__ == "__main__":
    main()
