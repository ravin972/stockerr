# Stockerr — Feature Ticket List

**Status legend:** ✅ Done · 🔵 Planned/Deferred · **Priority:** P0 (must) · P1 (should) · P2 (nice)

Tickets reflect the built system (60 passing tests) plus a deferred backlog. IDs are stable.

---

## Epic A — Foundation (config, secrets, networking)

| ID | Title | Pri | Status | Acceptance criteria |
|---|---|---|---|---|
| A1 | Project scaffold (uv, `src/` layout, extras) | P0 | ✅ | `uv sync` installs; `stockerr` console script works |
| A2 | Config from `.env` + `STOCKERR_*` env | P0 | ✅ | `load_config()` reads all documented vars with defaults |
| A3 | Secrets in OS keyring + `stockerr init` | P0 | ✅ | `init` stores via getpass; `get_secret` env-override→keyring |
| A4 | Redacted logging | P0 | ✅ | Secrets/token/signature scrubbed in logs & report errors |
| A5 | Shared HTTP layer `net.py` (retry/backoff/cache) | P1 | ✅ | 429/5xx retried; TTL cache; unit-tested with stubbed session |

## Epic B — Data sources & portfolio

| ID | Title | Pri | Status | Acceptance criteria |
|---|---|---|---|---|
| B1 | Groww holdings CSV source | P0 | ✅ | Parses stocks+MFs; auto-detects columns; clear error on bad file |
| B2 | Binance read-only source | P0 | ✅ | Signed `GET /account`; non-zero balances; USDT valuation |
| B3 | FX USD→INR (Frankfurter + fallback) | P0 | ✅ | Rate + timestamp; graceful fallback; cached |
| B4 | Merge to unified INR view + allocation | P0 | ✅ | Net worth, `alloc_pct` sums ~100%, category rollup |
| B5 | Report export (md/json/csv) | P1 | ✅ | Metadata (FX, sources), tables, Claude prompt, disclaimer |
| B6 | Live price refresh (yfinance) | P1 | ✅ | INR stock holdings repriced; crypto untouched |

## Epic C — Confidence scoring

| ID | Title | Pri | Status | Acceptance criteria |
|---|---|---|---|---|
| C1 | Fundamental sub-score (Screener CSV) | P0 | ✅ | D/E, ROE, ROCE, FCF, PE graded; renormalized; partial-data note |
| C2 | Technical sub-score (EMA/RSI) | P0 | ✅ | EMA50/200 + RSI band; unit-tested pure compute |
| C3 | Sentiment sub-score (Claude, optional) | P2 | ✅ | Headlines→0-100; graceful if no key |
| C4 | Combine 0.50/0.30/0.20 + rank | P0 | ✅ | Renormalized over available; ranked table |
| C5 | Plain-English **"Why"** rationale | P1 | ✅ | Trend/valuation/debt/RSI/loss-making + missing-data tail |

## Epic D — Opportunity discovery

| ID | Title | Pri | Status | Acceptance criteria |
|---|---|---|---|---|
| D1 | Stock screener (quality+valuation+technical) | P0 | ✅ | Graham MoS; ranked; rationale; Strong Buy/Watch/Avoid |
| D2 | Cap tiers (AMFI file / thresholds) | P1 | ✅ | Large/Mid/Small; AMFI file overrides thresholds |
| D3 | Thin-data guard | P1 | ✅ | <3 signals → demoted + "Insufficient"; no Strong Buy w/o valuation |
| D4 | Multi-year consistency (Stage-2) | P1 | ✅ | ROE/growth/FCF streak from yfinance financials (top-N, enriched) |
| D5 | Mutual fund screener | P1 | ✅ | Rolling returns + Sortino + drawdown + TER; NAV robust to bad values |
| D6 | Crypto momentum screener | P1 | ✅ | USDT pairs; trend/RSI + rel-strength vs BTC; cap tier; liquidity floor |
| D7 | IPO tracker | P1 | ✅ | Calendar + subscription + fundamentals score; GMP flagged unofficial |

## Epic E — Alerts, digest & automation

| ID | Title | Pri | Status | Acceptance criteria |
|---|---|---|---|---|
| E1 | Snapshot state + change detection | P0 | ✅ | Drift / price-move / net-worth / high-score alerts |
| E2 | Email + Telegram channels | P0 | ✅ | Independent, failure-isolated; token never logged |
| E3 | Daily digest (`stockerr digest`) | P0 | ✅ | Fresh prices→re-score→changes→Telegram+Email; report written |
| E4 | Task Scheduler recipe | P1 | ✅ | `run-digest.bat` + `schtasks` documented |
| E5 | `telegram-test` (auto chat-id + test) | P1 | ✅ | Detects chat id via getUpdates; sends test; instructs config fix |

## Epic F — Frontend (Streamlit)

| ID | Title | Pri | Status | Acceptance criteria |
|---|---|---|---|---|
| F1 | Dark wide dashboard + tabs | P0 | ✅ | Portfolio + Opportunities tabs; localhost only |
| F2 | Metric cards + donut + drift banner | P0 | ✅ | 4 cards; blinking banner when drift >5pts |
| F3 | Color-coded confidence grid + Why | P0 | ✅ | Signal→color; Why column; disclaimer |
| F4 | Opportunities sub-tabs (stocks/mf/crypto/ipo) | P1 | ✅ | Run buttons; grids; per-section error isolation |
| F5 | Sidebar Integration Setup | P1 | ✅ | CSV↔Live toggle; keyring/.env saves; masked status |
| F6 | Onboarding file-uploader fallback | P1 | ✅ | Missing data → uploader, never a crash |

## Epic G — Hardening, ops & docs

| ID | Title | Pri | Status | Acceptance criteria |
|---|---|---|---|---|
| G1 | `stockerr doctor` self-check | P0 | ✅ | Sources + channels + Binance read-only verification |
| G2 | Security review + fixes | P0 | ✅ | Signature/token redaction; `data/` gitignored; pre-push audit |
| G3 | Test suite | P0 | ✅ | 60 tests; fixtures per source; AppTest for UI |
| G4 | Documentation set | P1 | ✅ | PRD, architecture, security, frontend, tickets |

## Deferred backlog

| ID | Title | Pri | Status | Notes |
|---|---|---|---|---|
| X1 | Rebalancing suggestions | P1 | 🔵 | Current vs target → suggested (not executed) actions |
| X2 | Screener backtesting | P1 | 🔵 | Validate the score vs historical outcomes; honest metrics |
| X3 | Always-on cloud scheduling | P2 | 🔵 | Move digest to a small VPS/cloud cron (laptop-off resilience) |
| X4 | Optional Groww Trading API (TOTP) | P2 | 🔵 | Hands-off stock pulls; ~₹499/mo; keys can trade → careful |
| X5 | 10-yr fundamentals automation | P2 | 🔵 | Beyond yfinance's 3-4yr (Screener per-company export) |
| X6 | Broader Screener universe for discovery | P1 | 🔵 | New-idea discovery beyond own holdings |
