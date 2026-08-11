# Stockerr — Product Requirements Document (PRD)

**Status:** Living document · **Owner:** ravin972 · **Type:** Personal finance tool (not a commercial product)

---

## 1. Summary

**Stockerr** is a personal, **read-only** unified investment analysis tool for an Indian retail
investor. It pulls the user's own holdings from **Groww** (stocks + mutual funds) and **Binance**
(crypto), merges them into one INR net-worth / asset-allocation view, **scores** stocks with an AI
Confidence Engine, screens the market for ideas (stocks / MFs / crypto / IPOs), and sends a **daily
digest** (Telegram + Email). It helps the user *analyze and decide* — it **never places trades**.

## 2. Problem & motivation

- No single free tool combines **Indian stocks/MFs (Groww)** and **global crypto (Binance)** into one
  view — largely due to regulatory/data-privacy separation.
- Retail investors lack a private, transparent way to (a) see unified net worth, (b) get an
  evidence-based read on what they hold, and (c) discover opportunities — without handing credentials
  to third-party apps or paying for premium trackers.
- Goal: a **local, private, read-only** tool the user runs on their own laptop, feeding into
  their own decisions toward financial independence.

## 3. Goals / non-goals

**Goals**
- One INR-denominated view of stocks + MFs + crypto.
- A transparent 0–100 **confidence score** per stock with a plain-English **"why"**.
- Opportunity discovery across small/mid/large cap and asset types.
- Automated **daily digest** at market open (Telegram + Email).
- **Maximum privacy**: keys and holdings stay on the user's machine.

**Non-goals (explicit)**
- ❌ **No auto-trading / order placement** of any kind.
- ❌ Not investment advice; **no guaranteed-profit claims**.
- ❌ Not a multi-user SaaS, not a regulated financial product.
- ❌ No storage of secrets or holdings in the cloud or the code repo.

## 4. Users & personas

- **Primary user:** a single retail investor (the owner), comfortable running commands, investing via
  Groww (mainly stocks + some MFs) and a little via Binance (crypto). Wants a morning read + ideas.

## 5. Guardrails (product principles — non-negotiable)

| Principle | Implementation |
|---|---|
| Read-only | Binance key created read-only; Groww via CSV (no order-capable key); no order endpoints called |
| Not advice | Every output carries a disclaimer; scores are decision-support, never "buy X" |
| No profit promise | Estimates are labeled estimates; "Why" explains evidence, not outcomes |
| Privacy | Secrets in OS keyring; holdings/`.env`/exports gitignored, local-only |
| Honesty on data gaps | Missing sub-scores flagged; thin-data stocks demoted ("Insufficient") |

## 6. Functional requirements

### 6.1 Portfolio (holdings)
- Ingest Groww holdings from an exported CSV (stocks + MFs); Binance crypto from a read-only API.
- Merge into a canonical INR view: net worth, allocation by category, per-holding value.
- Crypto priced via Binance (USDT) → INR using a separate FX feed.
- Optional **live price refresh** (yfinance) so a daily run values holdings at today's prices.

### 6.2 AI Confidence Scoring (holdings + watchlist)
- Score = **Fundamental × 0.50 + Technical × 0.30 + Sentiment × 0.20**, renormalized over available
  sub-scores.
- Fundamental from a Screener.in CSV (PE, D/E, ROE, ROCE, FCF); Technical from yfinance (EMA50/200,
  RSI); Sentiment from news headlines classified by Claude (optional).
- Output: 0–100 confidence, **Signal** (Strong Buy / Hold / Avoid), and a plain-English **"Why"**.

### 6.3 Opportunity discovery
- **Stocks:** Buffett-style screen of a Screener.in export → quality + valuation (Graham margin of
  safety) + technicals + multi-year consistency; cap-tagged (AMFI); ranked with rationale.
- **Mutual funds:** rank by rolling-return consistency + risk-adjusted return (Sortino) + drawdown +
  expense ratio (AMFI/mfapi NAV).
- **Crypto:** light momentum screen of Binance USDT pairs (trend/RSI + relative strength vs BTC + cap
  tier via CoinGecko + liquidity floor) — speculative, with heavy caveats.
- **IPOs:** upcoming/open IPO calendar + subscription + a fundamentals score; GMP flagged unofficial.

### 6.4 Alerts & daily digest
- Alerts on allocation drift, sharp price moves, net-worth swings, and high-confidence ideas.
- `stockerr digest`: refresh prices → re-score → day-over-day changes → **Telegram + Email**.
- Report artifacts (`.md` / `.json` / `.csv`) written to `exports/` for Claude-Project analysis.

### 6.5 Dashboard (Streamlit)
- Wide, dark-mode UI: 4 metric cards, allocation donut vs target with a blinking drift banner,
  color-coded confidence grid with "Why", sidebar integration setup, "Opportunities" tabs.
- Graceful onboarding (file-uploader) when data is missing; per-section error isolation.

### 6.6 Operations
- CLI: `init`, `doctor`, `run`, `score`, `discover <target>`, `digest`, `telegram-test`.
- `stockerr doctor` self-check of every data source + channel (incl. Binance read-only verification).
- Windows Task Scheduler recipe for daily runs (`run-digest.bat`).

## 7. Non-functional requirements

- **Security:** see `docs/SECURITY_AND_ACCESS.md`. Read-only, keyring secrets, redacted logs,
  gitignored sensitive data.
- **Reliability:** all network calls via a shared layer with retry/backoff + on-disk TTL cache;
  one failing source produces a **partial** result, never a crash.
- **Cost:** free by default (yfinance, mfapi, AMFI, NSE, CoinGecko, Frankfurter). Optional paid:
  Anthropic (sentiment/analyze), Groww Trading API (~₹499/mo, not used in v1).
- **Portability:** Python ≥3.10, `uv`-managed, Windows-first (keyring = Credential Manager).
- **Quality:** unit + integration tests (60 passing) with fixtures for each source.

## 8. Success metrics (personal)

- Daily digest delivered reliably at market open.
- Net worth in Stockerr matches Groww/Binance within rounding.
- Confidence scores + "Why" are trusted enough to inform (not dictate) decisions.
- Zero secret/PII leakage; zero trades ever placed by the tool.

## 9. Assumptions & risks

- Free data sources (mfapi, yfinance, NSE) have **no SLA** and can break — mitigated by caching +
  graceful degradation, but must be monitored.
- yfinance Indian fundamentals are **partial** (ROE/ROCE/FCF gaps; financials' D/E misleading).
- Binance India access is **currently open** (FIU-registered) but has changed before.
- Scores are **heuristic, not a validated model**; user must diversify and do own diligence.

## 10. Roadmap

- **v1 (done):** portfolio, scoring, alerts, dashboard, discovery (4 streams), digest, hardening.
- **Next (deferred):** rebalancing suggestions, screener backtesting, always-on cloud scheduling,
  optional Groww Trading API (TOTP) for hands-off stock pulls, 10-yr fundamentals automation.
