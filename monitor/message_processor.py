import time
from typing import Any, Dict

from state_store import StateStore


def _handle_metadata(service_id: str, payload: Dict[str, Any], now_ts: float, store: StateStore, logger) -> None:
    store.apply_metadata(service_id, payload, now_ts)
    if store.set_status(service_id, "UP", now_ts):
        logger.info(f"Service {service_id} changed to UP")


def _handle_heartbeat(service_id: str, now_ts: float, store: StateStore, logger) -> None:
    store.apply_heartbeat(service_id, now_ts)
    if store.set_status(service_id, "UP", now_ts):
        logger.info(f"Service {service_id} changed to UP")


def _handle_pong(service_id: str, payload: Dict[str, Any], now_ts: float, store: StateStore, logger) -> None:
    ping_id = payload.get("ping_id")
    sent_at = payload.get("sent_at")
    if not ping_id or sent_at is None:
        return

    try:
        rtt_ms = store.apply_pong(service_id, str(ping_id), float(sent_at), now_ts)
        if rtt_ms is not None:
            logger.info(f"RTT for {service_id}: {rtt_ms} ms")
    except (TypeError, ValueError):
        logger.warning(f"Invalid RTT pong payload from {service_id}")


def process_event(event: Dict[str, Any], store: StateStore, logger) -> None:
    topic = event.get("topic", "")
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return

    parts = topic.split("/")
    if len(parts) < 2:
        return

    service_id = parts[1]
    msg_type = payload.get("type")
    now_ts = event.get("received_at", time.time())

    _, created = store.get_or_create(service_id)
    if created:
        logger.info(f"New service detected: {service_id}")

    handlers = {
        "metadata": lambda: _handle_metadata(service_id, payload, now_ts, store, logger),
        "heartbeat": lambda: _handle_heartbeat(service_id, now_ts, store, logger),
        "pong": lambda: _handle_pong(service_id, payload, now_ts, store, logger),
    }

    handler = handlers.get(msg_type)
    if handler:
        handler()
