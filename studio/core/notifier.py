"""Telegram notifications.

Hardened vs. the original: a request timeout (so the trading loop can never
hang on a slow Telegram call), graceful no-op when credentials are missing, and
returns a bool so callers can tell whether the message went out.
"""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str | None, chat_id: str | None, timeout: float = 10.0):
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout
        self.enabled = bool(token) and bool(chat_id) and "your_bot_token" not in str(token)
        if not self.enabled:
            log.warning("Telegram disabled (missing/placeholder credentials).")
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send_message(self, message: str) -> bool:
        if not self.enabled:
            log.info("[telegram disabled] %s", message)
            return False
        try:
            resp = requests.post(
                self.url,
                data={"chat_id": self.chat_id, "text": message},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            log.error("Telegram error: %s", e)
            return False
