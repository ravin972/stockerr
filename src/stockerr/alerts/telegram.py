"""Telegram alert channel (Bot API) + a connection helper.

`send_telegram` is the notification path. `detect_chat_id` / `send_message` back
the `stockerr telegram-test` command, which auto-finds the user's chat id (the
usual setup snag) and sends a test message. The bot token never reaches a log.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from .. import net
from ..config import (
    SECRET_TELEGRAM_CHAT,
    SECRET_TELEGRAM_TOKEN,
    Config,
    get_secret,
)
from ..logging_setup import redact

log = logging.getLogger("stockerr.alerts.telegram")

BASE = "https://api.telegram.org/bot{token}/{method}"


def send_message(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    """Send one message. Returns (ok, error). Never raises; token never logged."""
    try:
        resp = requests.post(
            BASE.format(token=token, method="sendMessage"),
            data={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True},
            timeout=15,
        )
        resp.raise_for_status()
        return True, ""
    except Exception as exc:  # noqa: BLE001 - channel failure must not break the run
        return False, redact(str(exc))


def get_updates(token: str) -> list:
    """Recent updates (messages users sent the bot). [] on failure."""
    try:
        data = net.get_json(BASE.format(token=token, method="getUpdates"), timeout=15)
        return data.get("result", []) if data.get("ok") else []
    except Exception as exc:  # noqa: BLE001
        log.warning("getUpdates failed: %s", redact(str(exc)))
        return []


def detect_chat_id(token: str) -> Optional[tuple[str, str]]:
    """Newest chat id that messaged the bot + sender's name. None if no messages."""
    for upd in reversed(get_updates(token)):
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid is not None:
            who = chat.get("first_name") or chat.get("username") or "you"
            return str(cid), str(who)
    return None


def send_telegram(cfg: Config, text: str) -> bool:
    """Send one Telegram alert. Returns True on success; never raises."""
    if not cfg.telegram_enabled:
        return False
    token = get_secret(SECRET_TELEGRAM_TOKEN)
    chat_id = get_secret(SECRET_TELEGRAM_CHAT)
    if not (token and chat_id):
        log.warning("Telegram enabled but token/chat id missing; skipping.")
        return False
    ok, err = send_message(token, chat_id, text)
    if ok:
        log.info("Telegram alert sent.")
    else:
        log.warning("Telegram send failed: %s", err)
    return ok
