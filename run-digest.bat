@echo off
REM Stockerr daily digest — run by Windows Task Scheduler at market open.
REM Refreshes prices, re-scores, and sends the digest to Telegram + Email.
cd /d "C:\Users\Lenovo\Desktop\Ravin\Stockerr"
if not exist logs mkdir logs
"C:\Users\Lenovo\.local\bin\uv.exe" run --extra scoring stockerr digest >> "logs\digest.log" 2>&1
