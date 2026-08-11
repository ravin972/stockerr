# Stockerr — Security & Access Document

**Status:** Living document · **Scope:** a personal, local, read-only finance tool (single user).

> Stockerr handles API keys and real financial data. This document defines how those are protected,
> and the access model. It is **not** a claim of regulatory compliance — Stockerr is a personal tool,
> not a financial product.

---

## 1. Security principles

1. **Read-only by design** — the tool can *analyze* but can never *trade*.
2. **Least privilege** — every credential is created with the minimum scope needed (reading only).
3. **Secrets never touch code or git** — stored in the OS keyring; only referenced by name.
4. **Local-first** — keys and holdings stay on the user's machine; nothing is sent to Stockerr
   servers (there are none).
5. **Fail safe & loud** — one failing source degrades to a partial result; secrets are redacted in
   any log/console/report output.

## 2. Threat model (lightweight)

| Threat | Mitigation |
|---|---|
| API key theft enabling trades/withdrawals | Keys created **read-only**; `doctor` verifies Binance perms; no order endpoints in code |
| Secret leakage via git | `.env`, `data/`, `exports/`, `state/`, logs gitignored; pre-push secret audit |
| Secret leakage via logs/reports | Redaction filter scrubs keys, Telegram bot-token, Binance signature |
| Holdings/PII exposure | Real holdings live only in gitignored `data/`; reports gitignored, local-only |
| Malicious input (news → LLM) | Sentiment output clamped 0–100, low weight, no code execution |
| Dashboard exposure | Streamlit bound to localhost; do not port-forward / bind 0.0.0.0 |

## 3. Secrets management

- **Store:** OS keyring (Windows Credential Manager) under service **`stockerr`**. Set interactively
  via `stockerr init` (uses `getpass` — never argv/shell history).
- **Reference:** `config.get_secret(name)` reads `STOCKERR_<NAME>` env override first (for
  headless/CI), then keyring. `config.set_secret` writes to keyring.
- **Non-secret config** lives in `.env` (thresholds, paths, channel toggles) — **secrets do not go in
  `.env`** by default (env override is supported but keyring is preferred).
- **Redaction** (`logging_setup.py`): a filter + `redact()` scrub `api_key/secret/token/password/
  authorization/x-mbx-apikey/chat_id/signature=…` **and** Telegram `bot<id>:<token>` URLs. Applied on
  logging handlers and to error strings before they reach reports/console.

**Secret names (keyring keys under service `stockerr`):**
`binance_api_key`, `binance_api_secret`, `telegram_bot_token`, `telegram_chat_id`,
`email_smtp_user`, `email_smtp_password`, `anthropic_api_key`, `ipo_guru_api_key`, `coingecko_api_key`.

## 4. Read-only enforcement (the core safety guarantee)

- **Binance:** create the API key with **"Enable Reading" only** — Spot/Margin trading OFF,
  Withdrawals OFF, IP-whitelisted. The code only calls `GET /api/v3/account` + public market data;
  **no order endpoints are imported anywhere**. `stockerr doctor` calls
  `GET /sapi/v1/account/apiRestrictions` and **WARNs if the key can trade or withdraw**.
- **Groww:** v1 uses the holdings **CSV export** — there is no order-capable Groww key in the tool.
  (The optional paid Groww Trading API is a stub only; its docstring warns it can place orders.)
- **Net effect:** even with a code bug, Stockerr cannot place a trade.

## 5. Per-integration access & least privilege

| Integration | Credential | Required scope | Notes |
|---|---|---|---|
| Binance | API key + secret | **Enable Reading only** (trading/withdrawals OFF) | IP-whitelist recommended |
| Telegram | Bot token + chat id | Send messages to your own chat | `telegram-test` auto-detects chat id |
| Email (SMTP) | Username + **App Password** | Send mail | Gmail App Password (2-Step ON); not the account password |
| Anthropic | API key | Messages API | Optional (sentiment / `--analyze`); data sent = headlines / report |
| CoinGecko | Demo key | Read market data | Optional; free demo tier |
| IPO Guru | API key | Read IPO data | Optional; free key |

## 6. Data handling & privacy

- **Gitignored (never committed):** `.env`, `data/` (real holdings + Screener export), `exports/`
  (reports with balances), `state/` (snapshots), `*.log`.
- **Local-only:** reports are written to `exports/` on disk; treat them as sensitive.
- **Third-party data egress (opt-in only):** enabling **sentiment** sends company names/headlines to
  Anthropic; `stockerr run --analyze` sends the **full report (incl. net worth + holdings)** to the
  Anthropic API. Off by default (no key = feature skipped).

## 7. Network & transport

- All HTTP via `net.py` using `requests` defaults — **TLS verification ON** (no `verify=False`
  anywhere). Bot token / signatures kept in headers or redacted, never in logs.
- No inbound network surface. The Streamlit dashboard listens on **localhost** only.

## 8. Access model

- **Single user, single machine.** No authentication layer (it's a local tool). Access = OS user
  account + keyring (encrypted per-user via DPAPI on Windows).
- Scheduled runs (`run-digest.bat`) must execute **under the user's account while logged in** so they
  can read the keyring.

## 9. Source control hygiene

- `.gitignore` excludes all sensitive paths (verified).
- **Pre-push audit** (run before every push): `git ls-files` to confirm no `data/`/`.env`; and a
  grep of tracked content for token/PII patterns. Test fixtures contain **fake** data only.
- Recommend a **private** GitHub repo for a personal finance tool.

## 10. Incident response

- **Suspected key exposure:** revoke/rotate immediately.
  - Telegram: `@BotFather` → `/revoke` → new token → update config.
  - Binance: delete + recreate the API key (read-only).
  - Gmail: revoke the App Password.
  - Anthropic/CoinGecko/IPO Guru: rotate the key in the respective console.
- **Accidental commit of a secret:** rotate the secret (assume compromised), then purge from git
  history (`git filter-repo` / BFG) and force-push; a private repo limits blast radius.

## 11. Regulatory / financial notes (informational, India)

- **Binance** is FIU-IND-registered and accessible from India (since Aug 2024), **Spot only**
  (Futures restricted); status has changed before — verify before relying on it.
- **Crypto tax:** 30% on gains + 1% TDS; losses not offsettable. Surface where P&L is shown.
- Stockerr provides **decision support, not investment advice**, and is **not** a
  SEBI-registered/regulated product. The user makes and places all decisions.

## 12. Security checklist (before daily use / before push)

- [ ] Binance key is **read-only** (`stockerr doctor` shows read-only OK).
- [ ] Secrets stored via `stockerr init` (keyring), not hardcoded.
- [ ] `.env`, `data/`, `exports/`, `state/` gitignored; pre-push audit clean.
- [ ] Dashboard on localhost only.
- [ ] Tokens rotated if ever exposed (logs/screenshots/paste).
- [ ] GitHub repo is **private**.
