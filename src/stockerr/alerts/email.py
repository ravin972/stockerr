"""Email alert channel (SMTP + app password)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from ..config import (
    SECRET_EMAIL_PASSWORD,
    SECRET_EMAIL_USER,
    Config,
    get_secret,
)

log = logging.getLogger("stockerr.alerts.email")


def send_email(cfg: Config, subject: str, body: str) -> bool:
    """Send one email. Returns True on success; never raises to the caller."""
    if not cfg.email_enabled:
        return False
    user = get_secret(SECRET_EMAIL_USER)
    password = get_secret(SECRET_EMAIL_PASSWORD)
    if not (user and password and cfg.email_to):
        log.warning("Email enabled but user/password/recipient missing; skipping.")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.email_from or user
    msg["To"] = cfg.email_to
    msg.set_content(body)

    try:
        with smtplib.SMTP(cfg.email_smtp_host, cfg.email_smtp_port, timeout=30) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        log.info("Email alert sent to %s.", cfg.email_to)
        return True
    except Exception as exc:  # noqa: BLE001 - channel failure must not break the run
        log.warning("Email send failed: %s", exc)
        return False
