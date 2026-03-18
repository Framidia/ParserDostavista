from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_float(name: str, default: float, required: bool = False) -> float:
    raw = _env(name, str(default), required=required)
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid float for {name}: {raw}") from exc


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name, None)
    if raw is None or raw == "":
        return default
    value = raw.strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _env_float_optional(name: str) -> float | None:
    raw = _env(name, None)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid float for {name}: {raw}") from exc


@dataclass(frozen=True)
class Config:
    api_base_url: str
    api_version: str
    api_endpoint: str
    request_reason: str
    take_order_endpoint: str
    device_id: str
    session: str | None
    user_agent: str
    accept_encoding: str
    poll_interval_seconds: float
    min_price: float
    max_distance_m: float
    http_timeout_seconds: float
    show_all_orders: bool
    courier_latitude: float | None
    courier_longitude: float | None
    telegram_bot_token: str
    telegram_chat_id: str
    session_cache_path: str
    log_path: str

    @property
    def api_root(self) -> str:
        base = self.api_base_url.rstrip("/") + "/"
        return f"{base}{self.api_version.strip('/')}/"

    @property
    def api_url(self) -> str:
        return f"{self.api_root}{self.api_endpoint.lstrip('/')}"

    @property
    def take_order_url(self) -> str:
        return f"{self.api_root}{self.take_order_endpoint.lstrip('/')}"


def load_config() -> Config:
    load_dotenv()

    poll_interval = _env_float("POLL_INTERVAL_SECONDS", 4.0)
    if poll_interval < 3.0:
        poll_interval = 3.0

    return Config(
        api_base_url=_env("API_BASE_URL", "https://robot.dostavista.ru/api/courier/") or "",
        api_version=_env("API_VERSION", "2.75") or "2.75",
        api_endpoint=_env("API_ENDPOINT", "available-mixed-list-compact") or "available-mixed-list-compact",
        request_reason=_env("REQUEST_REASON", "auto_by_ui") or "auto_by_ui",
        take_order_endpoint=_env("TAKE_ORDER_ENDPOINT", "take-order") or "take-order",
        device_id=_env("DV_DEVICE_ID", required=True) or "",
        session=_env("DV_SESSION", None),
        user_agent=_env("USER_AGENT", "ru-courier-app-main-android/2.125.0.3309") or "",
        accept_encoding=_env("ACCEPT_ENCODING", "gzip") or "gzip",
        poll_interval_seconds=poll_interval,
        min_price=_env_float("MIN_PRICE", 0.0),
        max_distance_m=_env_float("MAX_DISTANCE_M", 999999.0),
        http_timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 10.0),
        show_all_orders=_env_bool("SHOW_ALL_ORDERS", False),
        courier_latitude=_env_float_optional("COURIER_LATITUDE"),
        courier_longitude=_env_float_optional("COURIER_LONGITUDE"),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN", required=True) or "",
        telegram_chat_id=_env("TELEGRAM_CHAT_ID", required=True) or "",
        session_cache_path=_env("SESSION_CACHE_PATH", ".session_cache") or ".session_cache",
        log_path=_env("LOG_PATH", "parser.log") or "parser.log",
    )
