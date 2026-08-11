# Stockerr — Frontend Specification

**Status:** Living document · **Surface:** Streamlit dashboard (`app.py`) · **Theme:** dark, wide.

> The dashboard is read-only: it visualizes, scores, and screens. It never places trades. Every
> analytical surface carries a "decision support, not advice" disclaimer.

---

## 1. Layout

- `st.set_page_config(layout="wide", initial_sidebar_state="expanded", page_icon="📊")`.
- **Sidebar:** "⚙️ Integration Setup" (config + secrets).
- **Main:** title + caption, then two top-level tabs: **📈 Portfolio** and **🔎 Opportunities**.
- Theme via `.streamlit/config.toml` (base dark) + injected CSS. Widths use a **version-safe** helper
  `_WIDE` (`width="stretch"` on new Streamlit, else `use_container_width=True`).

## 2. Design tokens

| Token | Value | Use |
|---|---|---|
| App background | `#0e1117` | page |
| Card background | `#161b26` | metric cards |
| Text primary | `#f5f7fa` / `#e6e9ef` | headings/values |
| Text muted | `#9aa4b2` | labels |
| Accent (primary) | `#4c8bf5` | stocks / primary buttons |
| Category accents | stock `#4c8bf5`, mf `#22b07d`, crypto `#f5a623`, total `#a06bff` | metric cards, donut |
| Green / Yellow / Red / Muted | `#0e5c2f` / `#7a5c00` / `#6e1414` / `#333` | score & signal coloring |

**Signal → color mapping** (`_conf_style` for scores, `_signal_style` for labels):
- **Green:** Strong Buy · Bullish · score > 75
- **Yellow:** Hold · Watch · Neutral · score 50–75
- **Red:** Avoid · Bearish · score < 50
- **Muted/grey:** Insufficient · N/A · no score

## 3. Components

### 3.1 Metric cards (row of 4)
Custom HTML cards with a colored top border: **Direct Equity** (stock), **Mutual Funds** (mf),
**Crypto (Bitcoin)** (crypto), **Combined Net Worth**. Values `₹{value:,.0f}` from
`PortfolioResult.by_category` / `net_worth`.

### 3.2 Portfolio Drift & Allocation (left column)
- **Plotly donut** (`template="plotly_dark"`, `hole=0.55`) of current allocation by category.
- **Current-vs-target table**: Category · Current % · Target % · Drift (target default 50/30/20 from
  `cfg.target_allocation`).
- **Blinking drift banner**: if any `|current − target|` > 5 pts, a red `@keyframes blink` banner
  listing offenders ("… consider rebalancing"); else a green "within thresholds" banner.

### 3.3 AI Confidence Scoring (right column)
- Button **"⚡ Compute confidence scores"** (network: yfinance/Claude) → stores `scores` in session.
- Grid (pandas `Styler` in `st.dataframe`): **Symbol · Confidence · Signal · Fund. · Tech. · Sent. ·
  Why**. Confidence cell + Signal cell colored per mapping; numeric cols formatted `{:.0f}`, `na_rep="—"`.
- **"Why"** column = plain-English evidence (trend, valuation, debt, RSI, "loss-making", missing-data
  tail). Caption clarifies: *explains the score, not a promise of profit.*

### 3.4 Header actions
- **"🔄 Trigger Manual Scan & Alert"** (primary) → `engine.execute_pipeline(send=<checkbox>)`;
  spinner → results expander (alerts, per-channel sent status, **download** the `.md` report).
- **"Push to Telegram & Email"** checkbox (default on; only sends when channels configured).
- **"↻ Refresh data"** → reload portfolio from CSV/API (picks up edited holdings), clear scores.

### 3.5 Opportunities (tab) → sub-tabs
- **📈 Stocks:** upload/point to a Screener.in CSV → **"🔎 Run screen"** → color-coded ranked grid
  (Symbol/Name/Cap/Confidence/Signal/Quality/Valuation/Tech./Consist./MoS %/Rationale); cap filter;
  "add technicals to top 20" toggle; disclaimer.
- **🧺 Mutual Funds / 🪙 Crypto / 🚀 IPOs:** each has a run button → ranked grid + disclaimer; shows a
  clear "configure watchlist / add key" message when not set up. Each sub-tab is wrapped in `_safe(...)`
  so one section's error can't red-screen the whole page.

### 3.6 Sidebar — Integration Setup
- **Data mode** radio: **CSV Mode** vs **Live API Mode** (persisted to `.env`; controls whether the
  Binance API is used).
- Expanders: Groww holdings CSV upload; Binance (read-only) key/secret; Telegram token/chat; Email
  (SMTP host/port/from/to/user/pass); Target allocation (%); Sentiment (Anthropic key).
- **Save settings**: secrets → keyring (`config.set_secret`); non-secret toggles → `.env`
  (`dotenv.set_key`). Masked "already set / — not set" status per secret. `type="password"` inputs;
  secret values are **never pre-filled** back into fields.

## 4. States

- **Onboarding (no data):** if no Groww CSV and no Binance key → a file-uploader screen ("Let's get
  your first data source connected"). Uploading saves to `data/groww_holdings.csv` and reruns.
- **Loading:** `st.spinner` around network operations (load/score/scan/screen).
- **Error isolation:** engine calls wrapped in try/except → `st.error` with a friendly message; a
  hint to restart the server if a stale imported module is suspected. Portfolio-tab uses `st.stop`
  on unrecoverable load errors (not caught by the section wrapper).

## 5. Theme mechanics & accessibility

- Dark-first; colors defined so they read in Streamlit's dark theme. Wide content (grids, donut)
  scrolls within its own container; body never scrolls horizontally.
- Color is paired with text labels (Signal words, "Why", numbers) so meaning is not color-only.
- Disclaimers appear under every analytical surface (scores, screens, digest) — consistent, visible.
