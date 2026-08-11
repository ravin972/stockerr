@echo off
REM Stockerr daily digest — run by Windows Task Scheduler at market open.
REM Refreshes prices, re-scores, and sends the digest to Telegram + Email.
REM %~dp0 = this script's own folder, so it works wherever the repo is cloned.
cd /d "%~dp0"
if not exist logs mkdir logs
uv run --extra scoring stockerr digest >> "logs\digest.log" 2>&1
