# Contributing to Stockerr

Stockerr is a personal, **read-only** finance tool. Contributions must preserve two invariants:
it **never places trades**, and it **never leaks secrets or holdings**. Everything else is fair game.

## Dev setup

```powershell
uv sync --extra dev --extra ui --extra scoring --extra discovery
uv run pytest            # 60 tests
```

- Python ≥ 3.10, managed with `uv`. Package lives in `src/stockerr/`.
- Run the dashboard: `uv run --extra ui streamlit run app.py` (localhost only).
- Run the CLI: `uv run stockerr <command>` (`init`, `doctor`, `run`, `score`, `discover`, `digest`,
  `telegram-test`).

## Golden rules (non-negotiable)

1. **Read-only.** Never import or call an order/withdrawal endpoint. New sources fetch data only.
2. **No secrets in code or git.** Read via `config.get_secret(name)` (keyring); never hardcode a key,
   token, email, or real holding. `.env`, `data/`, `exports/`, `state/` are gitignored — keep them so.
3. **Redact.** Any log/error that could contain a URL, key, or token must pass through
   `logging_setup.redact` (already applied on handlers).
4. **Network through `net.py`.** Use `net.get` / `net.get_json` (retry/backoff/cache); don't call
   `requests` directly in new fetchers.
5. **Honest outputs.** Scores are decision-support. Keep disclaimers; flag missing data; never imply
   guaranteed profit.

## Adding things

- **A data source:** implement `sources/base.Source.fetch_holdings()` and return `Holding` rows in
  native currency; wire it into `engine.build_sources()`.
- **A sub-score / discovery stream:** follow `scoring/*` (return a `SubScore`) or `discovery/*`
  (pure compute + a graceful `fetch_*` + a `screen_*`/`build_*`), and add fixtures + tests.
- **Config:** add a `STOCKERR_*` var in `config.load_config`; document it in `.env.example`.

## Tests & PRs

- Add/keep unit tests with fixtures (no live network in tests — stub `net`/`requests`).
- Before pushing, run the **pre-push secret audit**: `git ls-files` (no `data/`/`.env`) and grep
  tracked content for token/PII patterns. Keep all tests green.
- Small, focused commits. Match the surrounding code style.

## Reporting security issues

Do not open a public issue for anything sensitive. Rotate any exposed credential immediately
(see [docs/SECURITY_AND_ACCESS.md](docs/SECURITY_AND_ACCESS.md) → Incident response).
