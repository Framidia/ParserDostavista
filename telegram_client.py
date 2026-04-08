from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import quote_plus

import requests
from requests import Response
from requests.exceptions import HTTPError, RequestException

from config import Config


class TelegramClient:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._base_url = f"https://api.telegram.org/bot{config.telegram_bot_token}"
        self._timeout_seconds = max(config.http_timeout_seconds, 20.0)
        self._retries = 3
        self._backoff_seconds = 0.5
        self._log = logging.getLogger("telegram")

    def _request(self, method: str, path: str, **kwargs: Any) -> Response:
        last_exc: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                resp = requests.request(
                    method,
                    f"{self._base_url}/{path}",
                    timeout=self._timeout_seconds,
                    **kwargs,
                )
                resp.raise_for_status()
                return resp
            except HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status is not None and 400 <= status < 500:
                    raise
                last_exc = exc
            except RequestException as exc:
                last_exc = exc

            if attempt < self._retries:
                self._log.warning(
                    "Telegram request failed (attempt %s/%s). Retrying...",
                    attempt,
                    self._retries,
                )
                time.sleep(self._backoff_seconds * attempt)

        if last_exc:
            raise last_exc
        raise RuntimeError("Telegram request failed without exception")

    def send_message(
        self,
        text: str,
        button_url: str | None = None,
        accept_callback_data: str | None = None,
        extra_callback_button: tuple[str, str] | None = None,
        extra_callback_buttons: list[tuple[str, str]] | None = None,
        parse_mode: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": self._config.telegram_chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        keyboard: list[list[dict[str, Any]]] = []
        if accept_callback_data:
            keyboard.append([{"text": "Принять заказ", "callback_data": accept_callback_data}])
        if extra_callback_button:
            button_text, callback_data = extra_callback_button
            keyboard.append([{"text": button_text, "callback_data": callback_data}])
        if extra_callback_buttons:
            for button_text, callback_data in extra_callback_buttons:
                keyboard.append([{"text": button_text, "callback_data": callback_data}])
        if button_url:
            keyboard.append([{"text": "Открыть в Яндекс.Картах", "url": button_url}])
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}

        self._request("POST", "sendMessage", json=payload)

    def get_updates(self, offset: int | None = None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": 0}
        if offset is not None:
            payload["offset"] = offset
        resp = self._request("GET", "getUpdates", params=payload)
        data = resp.json()
        if not isinstance(data, dict):
            return []
        result = data.get("result")
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        return []

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        self._request("POST", "answerCallbackQuery", json=payload)

    def set_commands(self, commands: list[tuple[str, str]]) -> None:
        payload = {
            "commands": [
                {"command": command, "description": description} for command, description in commands
            ]
        }
        self._request("POST", "setMyCommands", json=payload)


def build_yandex_maps_url(pickup: str, delivery: str) -> str:
    pickup_enc = quote_plus(pickup)
    delivery_enc = quote_plus(delivery)
    return f"https://yandex.com/maps/?rtext={pickup_enc}~{delivery_enc}&rtt=auto"
