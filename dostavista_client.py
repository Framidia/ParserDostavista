from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import requests

from config import Config


@dataclass
class AvailableOrdersResponse:
    is_successful: bool
    orders: list[dict[str, Any]]
    new_session: str | None
    session_source: str | None
    status_code: int
    raw: dict[str, Any] | None


@dataclass
class TakeOrderResponse:
    is_successful: bool
    new_session: str | None
    session_source: str | None
    status_code: int
    raw: dict[str, Any] | None


class DostavistaClient:
    def __init__(self, config: Config, session_value: str) -> None:
        self._config = config
        self._session_value = session_value
        self._http = requests.Session()
        self._log = logging.getLogger("dostavista")

    @property
    def session_value(self) -> str:
        return self._session_value

    def update_session(self, new_session: str) -> None:
        self._session_value = new_session

    @staticmethod
    def _is_valid_session(session: str | None) -> bool:
        return isinstance(session, str) and len(session) == 32

    def _extract_session(self, resp: requests.Response, raw: dict[str, Any] | None) -> tuple[str | None, str | None]:
        header_session = (
            resp.headers.get("x-dv-session")
            or resp.headers.get("X-Dv-Session")
            or resp.headers.get("X-DV-Session")
        )
        body_session = None
        if raw and isinstance(raw, dict):
            body_session = raw.get("session")

        # priority: header
        candidate = header_session or body_session
        if self._is_valid_session(candidate):
            return candidate, ("header" if header_session else "body")
        return None, None

    def fetch_available_orders(self) -> AvailableOrdersResponse:
        headers = {
            "x-dv-device-id": self._config.device_id,
            "x-dv-session": self._session_value,
            "user-agent": self._config.user_agent,
            "accept-encoding": self._config.accept_encoding,
            "accept": "application/json",
        }
        params = {"request_reason": self._config.request_reason}

        resp = self._http.get(
            self._config.api_url,
            headers=headers,
            params=params,
            timeout=self._config.http_timeout_seconds,
        )

        raw: dict[str, Any] | None = None
        is_successful = True
        orders: list[dict[str, Any]] = []

        try:
            raw_candidate = resp.json()
            if isinstance(raw_candidate, dict):
                raw = raw_candidate
        except ValueError:
            raw = None

        if resp.status_code != 200:
            if raw:
                error_text = (
                    raw.get("message")
                    or raw.get("error")
                    or raw.get("error_message")
                    or raw.get("deny_reason")
                )
                if error_text:
                    self._log.warning("Non-200 response: %s, error=%s", resp.status_code, error_text)
                else:
                    self._log.warning("Non-200 response: %s", resp.status_code)
            else:
                self._log.warning("Non-200 response: %s", resp.status_code)

        if raw and isinstance(raw, dict):
            is_successful = bool(raw.get("is_successful", True))
            if resp.status_code == 200:
                available = raw.get("available_objects") or {}
                orders = list(available.get("orders") or [])

        if resp.status_code in (401, 403):
            is_successful = False

        new_session, session_source = self._extract_session(resp, raw)

        return AvailableOrdersResponse(
            is_successful=is_successful,
            orders=orders,
            new_session=new_session,
            session_source=session_source,
            status_code=resp.status_code,
            raw=raw,
        )

    def take_order(self, order_id: str, latitude: float, longitude: float) -> TakeOrderResponse:
        headers = {
            "x-dv-device-id": self._config.device_id,
            "x-dv-session": self._session_value,
            "user-agent": self._config.user_agent,
            "accept-encoding": self._config.accept_encoding,
            "accept": "application/json",
            "content-type": "application/json; charset=UTF-8",
        }
        payload = {
            "order_id": str(order_id),
            "latitude": latitude,
            "longitude": longitude,
            "is_by_autoclicker": False,
        }

        resp = self._http.post(
            self._config.take_order_url,
            headers=headers,
            json=payload,
            timeout=self._config.http_timeout_seconds,
        )

        raw: dict[str, Any] | None = None
        is_successful = True

        try:
            raw_candidate = resp.json()
            if isinstance(raw_candidate, dict):
                raw = raw_candidate
        except ValueError:
            raw = None

        if resp.status_code != 200:
            if raw:
                error_text = (
                    raw.get("message")
                    or raw.get("error")
                    or raw.get("error_message")
                    or raw.get("deny_reason")
                )
                if error_text:
                    self._log.warning("Take-order non-200: %s, error=%s", resp.status_code, error_text)
                else:
                    self._log.warning("Take-order non-200: %s", resp.status_code)
            else:
                self._log.warning("Take-order non-200: %s", resp.status_code)

        if raw and isinstance(raw, dict):
            is_successful = bool(raw.get("is_successful", True))

        if resp.status_code in (401, 403):
            is_successful = False

        new_session, session_source = self._extract_session(resp, raw)

        return TakeOrderResponse(
            is_successful=is_successful,
            new_session=new_session,
            session_source=session_source,
            status_code=resp.status_code,
            raw=raw,
        )
