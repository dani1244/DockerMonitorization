import time
from typing import Any, Dict

from state_store import StateStore


def _persist_service_snapshot(store: StateStore, service_id: str, db, now_ts: float) -> None:
    if db is None:
        return
    state = store.get_service_copy(service_id)
    if state is not None:
        db.upsert_service(state, now_ts)


def _handle_metadata(service_id: str, payload: Dict[str, Any], now_ts: float, store: StateStore, logger, db) -> None:
    store.apply_metadata(service_id, payload, now_ts)
    status_changed = store.set_status(service_id, "UP", now_ts)
    _persist_service_snapshot(store, service_id, db, now_ts)
    if db is not None:
        db.record_event(service_id, "metadata_updated", now_ts, payload)
    if status_changed:
        logger.info(f"Service {service_id} changed to UP")
        if db is not None:
            db.record_event(service_id, "service_up", now_ts, {"reason": "metadata"})


def _handle_heartbeat(service_id: str, now_ts: float, store: StateStore, logger, db) -> None:
    store.apply_heartbeat(service_id, now_ts)
    status_changed = store.set_status(service_id, "UP", now_ts)
    _persist_service_snapshot(store, service_id, db, now_ts)
    if db is not None:
        db.record_event(service_id, "heartbeat_received", now_ts, None)
    if status_changed:
        logger.info(f"Service {service_id} changed to UP")
        if db is not None:
            db.record_event(service_id, "service_up", now_ts, {"reason": "heartbeat"})


def _handle_pong(service_id: str, payload: Dict[str, Any], now_ts: float, store: StateStore, logger, db) -> None:
    ping_id = payload.get("ping_id")
    sent_at = payload.get("sent_at")
    if not ping_id or sent_at is None:
        return

    try:
        sent_at_val = float(sent_at)
        rtt_ms = store.apply_pong(service_id, str(ping_id), sent_at_val, now_ts)
        if rtt_ms is not None:
            logger.info(f"RTT for {service_id}: {rtt_ms} ms")
            _persist_service_snapshot(store, service_id, db, now_ts)
            if db is not None:
                db.record_rtt(service_id, str(ping_id), rtt_ms, sent_at_val, now_ts)
                db.record_event(service_id, "rtt_measured", now_ts, {"rtt_ms": rtt_ms, "ping_id": str(ping_id)})
    except (TypeError, ValueError):
        logger.warning(f"Invalid RTT pong payload from {service_id}")


def process_event(event: Dict[str, Any], store: StateStore, logger, db=None) -> None:
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
        if db is not None:
            db.record_event(service_id, "service_discovered", now_ts, None)

    handlers = {
        "metadata": lambda: _handle_metadata(service_id, payload, now_ts, store, logger, db),
        "heartbeat": lambda: _handle_heartbeat(service_id, now_ts, store, logger, db),
        "pong": lambda: _handle_pong(service_id, payload, now_ts, store, logger, db),
    }

    handler = handlers.get(msg_type)
    if handler:
        handler()
