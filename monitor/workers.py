import json
import threading
import time
import uuid
from queue import Empty, Queue

from message_processor import process_event
from state_store import StateStore


def _persist_ping_timeout(service_id: str, now_ts: float, store: StateStore, db, realtime_store=None) -> None:
    if db is None:
        if realtime_store is None:
            return
    if db is not None:
        db.record_event(service_id, "ping_timeout", now_ts, None)
    state = store.get_service_copy(service_id)
    if state is not None and db is not None:
        db.upsert_service(state, now_ts)
    if state is not None and realtime_store is not None:
        realtime_store.upsert_service_realtime(state, now_ts)


def _publish_ping_for_service(client, service_id: str, store: StateStore, logger) -> None:
    ping_id = uuid.uuid4().hex
    sent_at = time.time()
    ping_topic = f"monitor/{service_id}/ping"
    ping_payload = {
        "type": "ping",
        "service_id": service_id,
        "ping_id": ping_id,
        "sent_at": sent_at,
    }

    result = client.publish(ping_topic, json.dumps(ping_payload), qos=1)
    if result.rc == 0:
        store.mark_ping_sent(service_id, ping_id, sent_at)
        logger.info(f"Ping enviado para {service_id} | ping_id={ping_id}")
    else:
        logger.warning(f"Falha ao publicar ping para {service_id}")


def start_ingest_worker(ingest_queue: Queue, store: StateStore, logger, stop_event: threading.Event, db=None, realtime_store=None) -> threading.Thread:
    def _run():
        while not stop_event.is_set():
            try:
                event = ingest_queue.get(timeout=0.5)
            except Empty:
                continue

            try:
                process_event(event, store, logger, db, realtime_store)
            finally:
                ingest_queue.task_done()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def start_timeout_worker(store: StateStore, settings, logger, stop_event: threading.Event, db=None, realtime_store=None) -> threading.Thread:
    def _run():
        while not stop_event.is_set():
            time.sleep(2)
            now_ts = time.time()
            transitions = store.check_timeouts(now_ts, settings.timeout_seconds, settings.max_missed_checks)
            for item in transitions:
                logger.warning(
                    f"Service DOWN: {item['service_id']} "
                    f"(missed_checks={item['missed_checks']}, elapsed={item['elapsed']:.1f}s)"
                )
                if db is not None:
                    db.record_event(
                        item["service_id"],
                        "service_down",
                        now_ts,
                        {
                            "missed_checks": item["missed_checks"],
                            "elapsed": round(item["elapsed"], 3),
                        },
                    )
                    state = store.get_service_copy(item["service_id"])
                    if state is not None:
                        db.upsert_service(state, now_ts)
                else:
                    state = store.get_service_copy(item["service_id"])

                if realtime_store is not None and state is not None:
                    realtime_store.upsert_service_realtime(state, now_ts)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def start_ping_worker(client, store: StateStore, settings, logger, stop_event: threading.Event, db=None, realtime_store=None) -> threading.Thread:
    def _run():
        while not stop_event.is_set():
            time.sleep(settings.ping_interval_seconds)

            now_ts = time.time()
            expired = store.expire_pending_pings(now_ts, settings.ping_response_timeout)
            for service_id in expired:
                logger.warning(f"Ping timeout for {service_id}; allowing new RTT probe")
                _persist_ping_timeout(service_id, now_ts, store, db, realtime_store)

            for service_id in store.get_ping_targets():
                _publish_ping_for_service(client, service_id, store, logger)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
