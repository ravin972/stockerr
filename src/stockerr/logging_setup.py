"""Logging configured with a redaction filter so secrets never reach a log file."""

from __future__ import annotations

import logging
import re
from pathlib import Path

# Matches key=value / key: value / "key": "value" for sensitive key names.
_SECRET_PATTERN = re.compile(
    r'(?i)(api[_-]?key|secret|token|password|authorization|x-mbx-apikey|chat[_-]?id|signature)'
    r'(["\']?\s*[:=]\s*["\']?)([^\s"\',&]+)'
)
# Telegram bot tokens appear inside URLs as bot<digits>:<token> — scrub those too.
_BOT_TOKEN_PATTERN = re.compile(r"bot\d{6,}:[A-Za-z0-9_\-]{20,}")


class RedactFilter(logging.Filter):
    """Replace secret-looking values in log records with ***."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = _BOT_TOKEN_PATTERN.sub("bot***", _SECRET_PATTERN.sub(r"\1\2***", msg))
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def redact(text: str) -> str:
    """Redact secrets in an arbitrary string (e.g. before printing an exception)."""
    out = _SECRET_PATTERN.sub(r"\1\2***", str(text))
    return _BOT_TOKEN_PATTERN.sub("bot***", out)


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> logging.Logger:
    logger = logging.getLogger("stockerr")
    if logger.handlers:  # already configured
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    redactor = RedactFilter()

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(redactor)
    logger.addHandler(console)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        fileh = logging.FileHandler(log_dir / "stockerr.log", encoding="utf-8")
        fileh.setFormatter(fmt)
        fileh.addFilter(redactor)
        logger.addHandler(fileh)

    logger.propagate = False
    return logger
