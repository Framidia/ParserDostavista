from __future__ import annotations

from datetime import datetime
import html
import logging
import time
from typing import Any

import requests

from config import Config, load_config
from dostavista_client import DostavistaClient
from storage import load_session, save_session
from telegram_client import TelegramClient, build_yandex_maps_url


def configure_logging(log_path: str) -> None:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)


def extract_order_id(order: dict[str, Any]) -> str | None:
    for key in ("order_id", "id", "task_id", "request_id", "delivery_id"):
        value = order.get(key)
        if value is not None and value != "":
            return str(value)
    return None


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).strip().replace(",", ".")
        return float(text)
    except (ValueError, TypeError):
        return None


def extract_addresses(order: dict[str, Any]) -> tuple[str, str]:
    points = order.get("points") or []
    pickup = ""
    delivery = ""
    if len(points) >= 1 and isinstance(points[0], dict):
        pickup = str(points[0].get("address") or "").strip()
    if len(points) >= 2 and isinstance(points[1], dict):
        delivery = str(points[1].get("address") or "").strip()
    elif len(points) >= 1 and isinstance(points[-1], dict):
        delivery = str(points[-1].get("address") or "").strip()
    return pickup, delivery


def extract_distance_m(order: dict[str, Any]) -> float | None:
    points = order.get("points") or []
    if len(points) >= 1 and isinstance(points[0], dict):
        return parse_float(points[0].get("courier_distance_m"))
    return None


def extract_between_distance_m(order: dict[str, Any]) -> float | None:
    points = order.get("points") or []
    if len(points) >= 2 and isinstance(points[1], dict):
        for key in (
            "previous_point_distance_m",
            "distance_from_prev_point_m",
            "distance_from_previous_point_m",
            "distance_from_prev_m",
            "distance_m",
        ):
            value = parse_float(points[1].get(key))
            if value is not None:
                return value
    for key in ("route_distance_m", "delivery_distance_m", "distance_m", "route_distance"):
        value = parse_float(order.get(key))
        if value is not None:
            return value
    return None


def extract_cargo_info(order: dict[str, Any]) -> str:
    cargo_name = ""

    matter = order.get("matter")
    if matter:
        cargo_name = str(matter).strip()

    cargo = order.get("cargo")
    if isinstance(cargo, dict) and not cargo_name:
        cargo_name = str(cargo.get("name") or cargo.get("title") or "").strip()

    if not cargo_name:
        for key in ("cargo_name", "goods_name", "item_name", "package_name", "cargo_title"):
            value = order.get(key)
            if value:
                cargo_name = str(value).strip()
                break

    return cargo_name


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if dt.tzinfo:
        dt = dt.astimezone()
    return dt


def _format_dt_with_bold_time(dt: datetime) -> str:
    return f"{dt:%Y-%m-%d} <b>{dt:%H:%M}</b>"


def _format_time_window(start_value: Any, finish_value: Any) -> str | None:
    start_dt = _parse_iso_datetime(start_value)
    finish_dt = _parse_iso_datetime(finish_value)
    if start_dt and finish_dt:
        if start_dt.date() == finish_dt.date():
            return f"{start_dt:%Y-%m-%d} <b>{start_dt:%H:%M}</b>-<b>{finish_dt:%H:%M}</b>"
        return (
            f"{start_dt:%Y-%m-%d} <b>{start_dt:%H:%M}</b>-"
            f"{finish_dt:%Y-%m-%d} <b>{finish_dt:%H:%M}</b>"
        )
    if start_dt:
        return _format_dt_with_bold_time(start_dt)
    if finish_dt:
        return _format_dt_with_bold_time(finish_dt)
    return None


def extract_point_time_windows(order: dict[str, Any]) -> tuple[str | None, str | None]:
    points = order.get("points") or []
    first = None
    second = None
    if len(points) >= 1 and isinstance(points[0], dict):
        first = _format_time_window(
            points[0].get("courier_start_datetime"),
            points[0].get("courier_finish_datetime"),
        )
    if len(points) >= 2 and isinstance(points[1], dict):
        second = _format_time_window(
            points[1].get("courier_start_datetime"),
            points[1].get("courier_finish_datetime"),
        )
    return first, second


def format_order_message(
    price: float | None,
    cargo_name: str,
    pickup: str,
    delivery: str,
    distance_to_pickup_m: float | None,
    between_distance_m: float | None,
    time_to_pickup: str | None,
    time_to_delivery: str | None,
) -> str:
    price_text = f"{price:.2f}" if price is not None else "нет данных"
    lines = [f"Цена: <b>{html.escape(price_text)}</b>"]
    lines.append(f"Что везти: {html.escape(cargo_name or 'нет данных')}")
    if time_to_pickup:
        lines.append(f"К первому адресу: {time_to_pickup}")
    if time_to_delivery:
        lines.append(f"Ко второму адресу: {time_to_delivery}")
    if distance_to_pickup_m is not None:
        lines.append(f"До первого адреса: {distance_to_pickup_m / 1000:.2f} км")
    if pickup:
        lines.append(f"Первый адрес: {html.escape(pickup)}")
    if delivery:
        lines.append(f"Второй адрес: {html.escape(delivery)}")
    if between_distance_m is not None:
        lines.append(f"Между адресами: {between_distance_m / 1000:.2f} км")
    return "\n".join(lines)


def format_short_order_message(
    price: float | None,
    cargo_name: str,
    pickup: str,
    delivery: str,
) -> str:
    price_text = f"{price:.2f}" if price is not None else "нет данных"
    lines = [f"Цена: <b>{html.escape(price_text)}</b>"]
    lines.append(f"Что везти: {html.escape(cargo_name or 'нет данных')}")
    if pickup:
        lines.append(f"Первый адрес: {html.escape(pickup)}")
    if delivery:
        lines.append(f"Второй адрес: {html.escape(delivery)}")
    return "\n".join(lines)


def order_passes_filters(order: dict[str, Any], config: Config) -> tuple[bool, float | None, float | None]:
    price = parse_float(order.get("list_currency"))
    distance_m = extract_distance_m(order)

    if price is None:
        return False, None, distance_m

    if price < config.min_price:
        return False, price, distance_m

    if distance_m is not None and distance_m > config.max_distance_m:
        return False, price, distance_m

    return True, price, distance_m


def send_all_orders(telegram: TelegramClient, latest_orders: list[dict[str, Any]]) -> None:
    if not latest_orders:
        telegram.send_message("Список заказов пока пуст.")
        return

    for order in latest_orders:
        order_id = extract_order_id(order)
        price = parse_float(order.get("list_currency"))
        pickup, delivery = extract_addresses(order)
        cargo_name = extract_cargo_info(order)

        message = format_short_order_message(price, cargo_name, pickup, delivery)
        maps_url = None
        if pickup and delivery:
            maps_url = build_yandex_maps_url(pickup, delivery)

        accept_data = f"accept:{order_id}" if order_id else None
        telegram.send_message(message, maps_url, accept_data, parse_mode="HTML")


def handle_telegram_updates(
    telegram: TelegramClient,
    client: DostavistaClient,
    config: Config,
    log: logging.Logger,
    last_offset: int,
    latest_orders: list[dict[str, Any]],
) -> int:
    new_offset = last_offset
    try:
        updates = telegram.get_updates(last_offset)
    except requests.RequestException:
        return new_offset

    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int) and update_id >= new_offset:
            new_offset = update_id + 1

        message = update.get("message")
        if isinstance(message, dict):
            text = str(message.get("text") or "").strip()
            command = text.split()[0] if text else ""
            if command.startswith("/orders"):
                send_all_orders(telegram, latest_orders)
                continue

        callback = update.get("callback_query")
        if not isinstance(callback, dict):
            continue

        data = str(callback.get("data") or "")
        callback_id = callback.get("id")

        if data == "show_all":
            if callback_id:
                telegram.answer_callback_query(callback_id, "Отправляю список...")
            send_all_orders(telegram, latest_orders)
            continue

        if data.startswith("accept:"):
            order_id = data.split(":", 1)[1].strip()
            if not order_id:
                continue

            if callback_id:
                telegram.answer_callback_query(callback_id, "Отправляю запрос...")

            if config.courier_latitude is None or config.courier_longitude is None:
                telegram.send_message(
                    "Не заданы COURIER_LATITUDE/COURIER_LONGITUDE. "
                    "Заполните их в .env для принятия заказов."
                )
                continue

            try:
                response = client.take_order(order_id, config.courier_latitude, config.courier_longitude)
            except requests.RequestException as exc:
                log.warning("Take-order request error: %s", exc)
                telegram.send_message(f"Не удалось принять заказ {order_id}: ошибка сети.")
                continue

            if response.new_session and response.new_session != client.session_value:
                client.update_session(response.new_session)
                save_session(config.session_cache_path, response.new_session)
                if response.session_source:
                    log.info("Session updated and cached (source=%s)", response.session_source)
                else:
                    log.info("Session updated and cached")

            if response.is_successful:
                telegram.send_message(f"Заказ {order_id} принят.")
            else:
                error_text = None
                if response.raw and isinstance(response.raw, dict):
                    error_text = (
                        response.raw.get("message")
                        or response.raw.get("error")
                        or response.raw.get("error_message")
                        or response.raw.get("deny_reason")
                    )
                if error_text:
                    telegram.send_message(
                        f"Не удалось принять заказ {order_id} (status={response.status_code}): {error_text}"
                    )
                else:
                    telegram.send_message(
                        f"Не удалось принять заказ {order_id} (status={response.status_code})."
                    )
        elif callback_id:
            telegram.answer_callback_query(callback_id, "Принято")

    return new_offset


def main() -> None:
    config = load_config()
    configure_logging(config.log_path)
    log = logging.getLogger("main")

    cached_session = load_session(config.session_cache_path)
    session_value = cached_session or config.session
    if not session_value:
        raise RuntimeError("No x-dv-session provided. Set DV_SESSION or .session_cache")

    if cached_session:
        log.info("Loaded session from cache")
    else:
        log.info("Using session from environment")

    client = DostavistaClient(config, session_value)
    telegram = TelegramClient(config)

    seen_orders: set[str] = set()
    last_session_alert_ts = 0.0
    telegram_offset = 0
    latest_orders: list[dict[str, Any]] = []

    try:
        telegram.set_commands([("orders", "Показать все заказы")])
    except requests.RequestException as exc:
        log.warning("Telegram set commands failed: %s", exc)

    try:
        telegram.send_message(
            "Панель управления",
            extra_callback_button=("Показать все заказы", "show_all"),
        )
    except requests.RequestException as exc:
        log.warning("Telegram control panel send failed: %s", exc)

    log.info("Starting polling: interval=%.1fs", config.poll_interval_seconds)

    while True:
        cycle_start = time.time()
        try:
            telegram_offset = handle_telegram_updates(
                telegram,
                client,
                config,
                log,
                telegram_offset,
                latest_orders,
            )
            response = client.fetch_available_orders()

            if response.new_session and response.new_session != client.session_value:
                client.update_session(response.new_session)
                save_session(config.session_cache_path, response.new_session)
                if response.session_source:
                    log.info("Session updated and cached (source=%s)", response.session_source)
                else:
                    log.info("Session updated and cached")

            if not response.is_successful:
                log.warning("API reported is_successful=false (status=%s)", response.status_code)
                now = time.time()
                if now - last_session_alert_ts > 60:
                    telegram.send_message(
                        "Сессия истекла или недействительна (is_successful=false). "
                        "Обновите x-dv-session через mitmproxy."
                    )
                    last_session_alert_ts = now
                continue

            latest_orders = response.orders

            for order in response.orders:
                order_id = extract_order_id(order)
                if not order_id:
                    continue
                if order_id in seen_orders:
                    continue

                passes, price, distance_m = order_passes_filters(order, config)
                seen_orders.add(order_id)

                if not passes:
                    continue

                pickup, delivery = extract_addresses(order)
                cargo_name = extract_cargo_info(order)
                between_distance_m = extract_between_distance_m(order)
                time_pickup, time_delivery = extract_point_time_windows(order)

                message = format_order_message(
                    price,
                    cargo_name,
                    pickup,
                    delivery,
                    distance_m,
                    between_distance_m,
                    time_pickup,
                    time_delivery,
                )
                maps_url = None
                if pickup and delivery:
                    maps_url = build_yandex_maps_url(pickup, delivery)

                accept_data = f"accept:{order_id}"
                telegram.send_message(message, maps_url, accept_data, parse_mode="HTML")
                log.info("Sent order %s", order_id)

        except requests.RequestException as exc:
            log.warning("Request error: %s", exc)
        except Exception as exc:
            log.exception("Unexpected error: %s", exc)
        finally:
            elapsed = time.time() - cycle_start
            sleep_for = max(0.0, config.poll_interval_seconds - elapsed)
            time.sleep(sleep_for)


if __name__ == "__main__":
    main()
