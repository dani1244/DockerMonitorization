import logging
import threading
import time
from queue import Queue

from config import Settings
from dashboard import render_dashboard
from mqtt_receiver import build_mqtt_client
from redis_store import RedisRealtimeStore
from sqlite_store import SQLiteStore
from state_store import StateStore
from web_dashboard import start_web_dashboard
from workers import start_ingest_worker, start_ping_worker, start_timeout_worker

settings = Settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(settings.log_file), logging.StreamHandler()],
)

logger = logging.getLogger("monitor")

def main():
    logger.info("Starting monitor...")
    stop_event = threading.Event()
    ingest_queue: Queue = Queue(maxsize=10000)
    store = StateStore()
    db = SQLiteStore(settings.db_path)
    realtime_store = None

    try:
        realtime_store = RedisRealtimeStore(
            settings.redis_host,
            settings.redis_port,
            alert_cooldown_seconds=settings.alert_cooldown_seconds,
        )
        logger.info(f"Connected to Redis realtime store at {settings.redis_host}:{settings.redis_port}")
    except Exception as err:
        logger.warning(f"Redis realtime store unavailable: {err}")

    client = build_mqtt_client(settings, ingest_queue, logger)

    try:
        client.connect(settings.broker_host, settings.broker_port, 60)
    except Exception as err:
        logger.exception(f"Connection error: {err}")
        return

    start_ingest_worker(ingest_queue, store, logger, stop_event, db=db, realtime_store=realtime_store)
    start_timeout_worker(store, settings, logger, stop_event, db=db, realtime_store=realtime_store)
    start_ping_worker(client, store, settings, logger, stop_event, db=db, realtime_store=realtime_store)

    web_thread = threading.Thread(
        target=start_web_dashboard,
        args=((realtime_store or store), db, settings.web_dashboard_host, settings.web_dashboard_port, logger),
        daemon=True,
    )
    web_thread.start()

    client.loop_start()

    try:
        while True:
            if settings.terminal_dashboard_enabled:
                domain_events = []
                if realtime_store is not None:
                    summary = realtime_store.get_dashboard_summary()
                    snapshot = summary.get("services", {})
                    domain_events = summary.get("domain_events", [])
                else:
                    snapshot = store.get_snapshot()

                render_dashboard(
                    snapshot,
                    settings.timeout_seconds,
                    settings.log_file,
                    domain_events=domain_events,
                    module_filter=settings.dashboard_module_filter,
                )
            time.sleep(settings.dashboard_refresh_seconds)
    except KeyboardInterrupt:
        logger.info("Stopping monitor...")
    finally:
        stop_event.set()
        client.loop_stop()
        client.disconnect()
        if realtime_store is not None:
            realtime_store.close()
        db.close()


if __name__ == "__main__":
    main()