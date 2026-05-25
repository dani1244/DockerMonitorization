import logging
import threading
import time
from queue import Queue

from config import Settings
from dashboard import render_dashboard
from mqtt_receiver import build_mqtt_client
from sqlite_store import SQLiteStore
from state_store import StateStore
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

    client = build_mqtt_client(settings, ingest_queue, logger)

    try:
        client.connect(settings.broker_host, settings.broker_port, 60)
    except Exception as err:
        logger.exception(f"Connection error: {err}")
        return

    start_ingest_worker(ingest_queue, store, logger, stop_event, db=db)
    start_timeout_worker(store, settings, logger, stop_event, db=db)
    start_ping_worker(client, store, settings, logger, stop_event, db=db)

    client.loop_start()

    try:
        while True:
            render_dashboard(store.get_snapshot(), settings.timeout_seconds, settings.log_file)
            time.sleep(settings.dashboard_refresh_seconds)
    except KeyboardInterrupt:
        logger.info("Stopping monitor...")
    finally:
        stop_event.set()
        client.loop_stop()
        client.disconnect()
        db.close()


if __name__ == "__main__":
    main()