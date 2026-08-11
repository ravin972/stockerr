<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/stockerr-wordmark-dark.svg">
    <img alt="Stockerr" src="assets/stockerr-wordmark.svg" width="360">
  </picture>
</p>

<p align="center"><em>Unified, read-only investment analysis — Groww stocks &amp; MFs + Binance crypto, scored and screened. Never trades.</em></p>

A **personal, read-only** tool that pulls your **Groww** (Indian stocks + mutual funds) and
**Binance** (crypto) holdings, merges them into one **INR net-worth / asset-allocation** view,
scores your stocks with an **AI Confidence Engine**, writes report files you can drop into a
**Claude Project**, and sends **email + Telegram + report** alerts when things move.

> ⚠️ **Not investment advice. Never places trades.** Every data source is read-only by design.
> Confidence scores are a systematic *screen*, not a recommendation or a guarantee. Always do
> your own due diligence before deploying capital.

---

## What it does

```
Groww CSV (stocks + MFs) ─┐
                          ├─► merge to INR ─► confidence scoring ─► report (.md/.json/.csv)
Binance API (read-only) ──┘         │                                     │
                                    └── alerts (drift / price move) ──► email + Telegram
```

- **Binance**: genuine read-only API key → Spot balances, priced via USDT then converted to INR.
- **Groww**: your exported holdings CSV (free, safe, and the only route that includes mutual funds).
- **Confidence score** per stock (0–100): `Fundamental×0.50 + Technical×0.30 + Sentiment×0.20`.
- **Alerts**: allocation drift, sharp price moves, and high-confidence stocks — to email + Telegram.

---

## Documentation

Full project docs live in **[`docs/`](docs/)**:
[PRD](docs/PRD.md) ·
[Technical Architecture](docs/TECHNICAL_ARCHITECTURE.md) ·
[Security & Access](docs/SECURITY_AND_ACCESS.md) ·
[Frontend Spec](docs/FRONTEND_SPEC.md) ·
[Feature Tickets](docs/FEATURE_TICKETS.md).
Contributing / dev workflow: [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Setup (you're comfortable with tooling, so this is brief)

```powershell
# from the project root
uv sync                       # or: python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e .
uv sync --extra scoring       # optional: adds yfinance + anthropic for the confidence engine

copy .env.example .env        # then edit .env (paths, thresholds, channel toggles)
stockerr init                 # store secrets in Windows Credential Manager (interactive)
```

### 1. Binance — create a **READ-ONLY** API key
On Binance → *Account → API Management → Create API*:
- ✅ **Enable Reading** (this is all you need)
- ❌ **Enable Spot & Margin Trading** — OFF
- ❌ **Enable Withdrawals** — OFF
- 🔒 Restrict access to your **IP** (recommended)

Then `stockerr init` and paste the key + secret. (India note: Binance is FIU-registered and
accessible again since Aug 2024, but Spot only — Futures are restricted.)

### 2. Groww — export your holdings
In the Groww app/web, export/download your **holdings** (stocks) and, if you hold them, your
**mutual funds** as CSV. Put the file paths in `.env`:
```
STOCKERR_GROWW_CSV=C:\Users\You\Downloads\groww_stocks.csv;C:\Users\You\Downloads\groww_mf.csv
```
The parser auto-detects columns; if it can't, it tells you exactly what it found and what it needs.

### 3. Alerts — Telegram + Email
- **Telegram**: message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the **bot token**.
  Get your **chat id** (e.g. message [@userinfobot](https://t.me/userinfobot)). Put both into
  `stockerr init`, and set `STOCKERR_TELEGRAM_ENABLED=true` in `.env`.
- **Email**: for Gmail, create an **App Password** (Google Account → Security → App passwords).
  Put the SMTP user + app password into `stockerr init`, set `STOCKERR_EMAIL_ENABLED=true` and
  `STOCKERR_EMAIL_FROM` / `STOCKERR_EMAIL_TO` in `.env`.

### 4. Confidence scoring (optional inputs)
- **Fundamentals**: export a CSV from [screener.in](https://www.screener.in/) with columns for
  Debt-to-Equity, ROE, ROCE, Free Cash Flow, and (optionally) `Price to Earning` (PE), then set
  `STOCKERR_SCREENER_CSV=...`. Any missing column is skipped and the score renormalizes.
- **Technical**: uses free daily prices via `yfinance` — no key needed.
- **Sentiment**: needs an **Anthropic API key** (stored via `stockerr init`); it classifies recent
  news headlines. Skipped gracefully if absent (weights renormalize).
- **Watchlist**: score stocks you don't own yet with `STOCKERR_SCORE_WATCHLIST=TCS,INFY`.

---

## Dashboard (Streamlit UI)

A wide, dark-mode dashboard — 4 metric cards (Direct Equity / Mutual Funds / Crypto / Net Worth),
an allocation donut vs your target with a blinking drift banner, and the color-coded AI Confidence
grid (>75 green / 50–75 yellow / <50 red). The sidebar **Integration Setup** lets you toggle
**CSV ↔ Live API mode** and store keys (Binance, Telegram, SMTP, Anthropic) securely, and the
**Trigger Manual Scan & Alert** button runs the full pipeline and pushes to Telegram + Email.

```powershell
uv run --extra ui streamlit run app.py        # add --extra scoring for the confidence engine
```

If `data/groww_holdings.csv` is missing, the dashboard shows a file-uploader instead of crashing.

## Discover opportunities — Buffett-style stock screener

Beyond tracking what you hold, Stockerr can screen the market for ideas. Export a **screen from
[screener.in](https://www.screener.in/)** (include columns like PE, ROE, ROCE, Debt/Equity, Free
cash flow, EPS, Book value, CMP, Market Cap), then:

```powershell
stockerr discover stocks --csv path\to\screen.csv          # ranked table in the terminal
stockerr discover stocks --csv path\to\screen.csv --enrich  # + yfinance technicals for the top 20
```

Or use the dashboard's **🔎 Opportunities → Stocks** tab (upload the CSV there). Each stock gets a
0–100 **confidence** from *quality* (fundamentals) + *valuation* (Graham margin-of-safety), tagged
small/mid/large cap, with a plain-English rationale and a **Strong Buy / Watch / Avoid** signal.
It's a systematic screen — **not advice**, and never a "Strong Buy" without a valuation.

### Other discovery streams

```powershell
stockerr discover ipo       # upcoming IPOs + fundamentals score (needs IPO Guru key or `pip install nse`)
stockerr discover mf        # rank funds in STOCKERR_MF_WATCHLIST (AMFI scheme codes)
stockerr discover crypto    # momentum screen of STOCKERR_CRYPTO_WATCHLIST (Binance USDT symbols)
```

- **Mutual funds**: ranked by rolling-return consistency + risk-adjusted return (Sortino) + drawdown
  + expense ratio, from free AMFI/`mfapi.in` NAV history. Set `STOCKERR_MF_WATCHLIST` to scheme codes.
- **Crypto**: a light momentum filter (EMA/RSI + relative strength vs BTC + cap tier) over
  **Binance USDT** pairs — speculative, with volatility and India-tax caveats shown.
- **IPOs**: upcoming/open IPOs with an RHP-fundamentals score; subscription is the key signal and
  **GMP is labeled unofficial**. Add a free IPO Guru key via `stockerr init`, or `pip install nse`.

All four also appear as tabs in the dashboard's **🔎 Opportunities** section. They're screens —
**not advice**, and never a profit guarantee.

## Usage (CLI)

```powershell
stockerr run                 # fetch + merge + report + alerts
stockerr run --score         # also compute confidence scores
stockerr run --dry-run       # do everything except sending alerts / saving snapshot
stockerr run --analyze       # also call Claude to write analysis_<date>.md (needs Anthropic key)
stockerr score               # just print the confidence table
```

Output lands in `exports/`:
- `report_<date>.md` — **drag this into a Claude Project** for deep analysis.
- `holdings_<date>.json` — machine-readable artifact (with FX rate, source status, scores).
- `holdings_<date>.csv` — flat holdings table.

## Scheduling (Windows Task Scheduler)
Create a Basic Task → daily → *Start a program*:
- Program: `powershell.exe`
- Arguments: `-Command "cd 'C:\Users\You\Desktop\Ravin\Stockerr'; uv run stockerr run --score"`

> The scheduled run only fires while the laptop is **on**. For crypto (which moves fast), a more
> frequent trigger makes sense; stocks/MFs are fine daily.

## Configuration
All non-secret settings live in `.env` (see `.env.example` for every option and default).
Secrets live only in Windows Credential Manager (via `stockerr init`) — never in `.env` or git.

## Security notes
- Read-only is enforced **at the source** — the Binance key can't trade; Groww uses a CSV (no
  order-capable key). The tool imports no order endpoints.
- Secrets are stored in the OS keyring; logs are redacted; `exports/` and `state/` (which hold
  real balances) are gitignored — treat them as sensitive.

## Health check

Before relying on the outputs, run the self-check — it confirms your **Binance key is read-only**,
your CSVs parse, and each free feed is reachable:

```powershell
stockerr doctor
```

## Reliability notes
- All network calls go through `net.py` (retry + backoff on 429/5xx, on-disk TTL cache) so live use
  stays resilient under NSE / yfinance / CoinGecko rate limits.
- Stock cap tags use AMFI's official file when `STOCKERR_AMFI_CSV` is set (else market-cap
  thresholds). Thin-data stocks are demoted and flagged **"Insufficient"** so they can't over-rank.
- `stockerr discover stocks --enrich` adds a **3-4 yr consistency** score (ROE/growth/FCF) to the
  shortlist via yfinance.

## Daily automation (digest)

Get a **daily digest** at market open — fresh prices (yfinance), re-scored holdings with the
plain-English *why*, day-over-day changes, and alerts — pushed to **Telegram + Email**. It
automates the *analysis*, not the decision: it never says "buy X", never guarantees profit, and
never trades. Holdings quantities come from your CSV (update it when you actually buy/sell); only
prices refresh daily.

```powershell
stockerr digest              # build + send the digest now
stockerr digest --dry-run    # preview only (no send, no state saved)
```

**1. Set up the channels** (one time): `stockerr init` to store your Telegram bot token + chat id
and SMTP app-password, then in `.env`:
```
STOCKERR_TELEGRAM_ENABLED=true
STOCKERR_EMAIL_ENABLED=true
STOCKERR_EMAIL_FROM=you@gmail.com
STOCKERR_EMAIL_TO=you@gmail.com
```
Then verify: **`stockerr telegram-test`** (auto-detects your chat id from your message to the bot
and sends a test — the reliable way to get the chat id right), and `stockerr doctor`.

**2. Schedule it** (Windows Task Scheduler → runs `run-digest.bat` daily at 9:20 AM):
```powershell
schtasks /Create /SC DAILY /ST 09:20 /TN "Stockerr Daily Digest" ^
  /TR "C:\Users\Lenovo\Desktop\Ravin\Stockerr\run-digest.bat"
```
> The task must run **under your user account while logged in** (so it can read secrets from
> Windows Credential Manager). It only fires while the laptop is **on** at 9:20 — for always-on
> delivery you'd move it to a small cloud/VPS or a scheduled cloud agent later.

## Tests
```powershell
uv run pytest            # or: pytest   (55 tests)
```

## Roadmap / optional
- `stockerr[groww-api]` — swap the Groww CSV for the paid Trading API (TOTP) for hands-off *stock*
  pulls (~₹499/mo, stocks/F&O only, no MFs, keys can also trade — see `sources/groww_api.py`).
