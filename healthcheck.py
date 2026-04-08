from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import threading


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


@dataclass(frozen=True)
class HealthSnapshot:
    status: str
    started_at: str
    last_poll_started_at: str | None
    last_success_at: str | None
    last_status_code: int | None
    last_error: str | None
    consecutive_failures: int
    last_orders_count: int | None
    seconds_since_success: float | None


class HealthState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = _utc_now()
        self._last_poll_started_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._last_status_code: int | None = None
        self._last_error: str | None = None
        self._consecutive_failures = 0
        self._last_orders_count: int | None = None

    def mark_poll_started(self) -> None:
        with self._lock:
            self._last_poll_started_at = _utc_now()

    def mark_success(self, status_code: int, orders_count: int) -> None:
        now = _utc_now()
        with self._lock:
            self._last_success_at = now
            self._last_status_code = status_code
            self._last_error = None
            self._consecutive_failures = 0
            self._last_orders_count = orders_count

    def mark_failure(self, status_code: int | None, error_text: str) -> None:
        with self._lock:
            self._last_status_code = status_code
            self._last_error = error_text
            self._consecutive_failures += 1

    def snapshot(self, poll_interval_seconds: float) -> HealthSnapshot:
        with self._lock:
            last_success_at = self._last_success_at
            threshold_seconds = max(poll_interval_seconds * 3, 15.0)
            seconds_since_success = None
            if last_success_at is not None:
                seconds_since_success = (_utc_now() - last_success_at).total_seconds()

            if last_success_at is None:
                status = "starting"
            elif seconds_since_success is not None and seconds_since_success <= threshold_seconds:
                status = "ok"
            else:
                status = "stale"

            return HealthSnapshot(
                status=status,
                started_at=_isoformat(self._started_at) or "",
                last_poll_started_at=_isoformat(self._last_poll_started_at),
                last_success_at=_isoformat(last_success_at),
                last_status_code=self._last_status_code,
                last_error=self._last_error,
                consecutive_failures=self._consecutive_failures,
                last_orders_count=self._last_orders_count,
                seconds_since_success=seconds_since_success,
            )


def start_healthcheck_server(
    host: str,
    port: int,
    state: HealthState,
    poll_interval_seconds: float,
) -> ThreadingHTTPServer:
    logger = logging.getLogger("healthcheck")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path not in ("/health", "/healthz"):
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"error":"not_found"}')
                return

            snapshot = state.snapshot(poll_interval_seconds)
            status_code = 200 if snapshot.status == "ok" else 503
            payload = {
                "status": snapshot.status,
                "started_at": snapshot.started_at,
                "last_poll_started_at": snapshot.last_poll_started_at,
                "last_success_at": snapshot.last_success_at,
                "last_status_code": snapshot.last_status_code,
                "last_error": snapshot.last_error,
                "consecutive_failures": snapshot.consecutive_failures,
                "last_orders_count": snapshot.last_orders_count,
                "seconds_since_success": snapshot.seconds_since_success,
            }
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")

            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            logger.debug("%s - %s", self.address_string(), format % args)

    server = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="healthcheck-server")
    thread.start()
    logger.info("Health check listening on http://%s:%s/health", host, port)
    return server
