import json
import logging
import os
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

BROKER_HOST = os.getenv("BROKER_HOST", "localhost")
BROKER_PORT = int(os.getenv("BROKER_PORT", 1883))
TIMEOUT_SECONDS = int(os.getenv("DOWN_TIMEOUT", os.getenv("TIMEOUT_SECONDS", 15)))
LOG_FILE = os.getenv("LOG_FILE", "monitor.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)

logger = logging.getLogger("monitor")

services = {}
services_lock = threading.Lock()


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.0f}m"
    return f"{seconds/3600:.1f}h"


def print_dashboard():
    clear_screen()

    green = "\033[92m"
    red = "\033[91m"
    yellow = "\033[93m"
    reset = "\033[0m"
    bold = "\033[1m"

    print(bold + "=" * 80 + reset)
    print(bold + "DOCKER MONITOR" + reset)
    print(bold + "=" * 80 + reset)

    print(f"Atualizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Timeout: {TIMEOUT_SECONDS}s")
    print(f"Log: {LOG_FILE}")
    print("-" * 80)

    print(f"{'SERVICE':<20} {'IP':<16} {'PORT':<8} {'STATUS':<8} {'LAST HB':<10}")

    now = time.time()

    with services_lock:
        snapshot = dict(services)

    if not snapshot:
        print("Nenhum servico ativo ainda...")
        return

    for service_id, data in snapshot.items():
        meta = data.get("metadata", {})
        net = meta.get("network", {})

        ip = net.get("ip", "?")
        port = net.get("port", "?")

        status = data.get("status", "UNKNOWN")
        if status == "UP":
            status_str = green + "UP" + reset
        elif status == "DOWN":
            status_str = red + "DOWN" + reset
        else:
            status_str = yellow + status + reset

        last = data.get("last_heartbeat", 0)
        last_str = format_time(now - last) if last else "-"

        print(f"{service_id:<20} {ip:<16} {port:<8} {status_str:<8} {last_str:<10}")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"Connected to MQTT broker {BROKER_HOST}:{BROKER_PORT}")
        client.subscribe("monitor/+/metadata")
        client.subscribe("monitor/+/heartbeat")
    else:
        logger.error(f"MQTT connection failed: {rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        logger.warning("Invalid JSON received")
        return

    parts = msg.topic.split("/")
    if len(parts) < 2:
        return

    service_id = parts[1]
    msg_type = payload.get("type")

    with services_lock:
        if service_id not in services:
            services[service_id] = {
                "metadata": None,
                "last_heartbeat": 0,
                "status": "UNKNOWN",
            }
            logger.info(f"New service detected: {service_id}")

        service = services[service_id]

        if msg_type == "metadata":
            service["metadata"] = payload
            service["last_heartbeat"] = time.time()
            service["status"] = "UP"
        elif msg_type == "heartbeat":
            service["last_heartbeat"] = time.time()
            service["status"] = "UP"


def timeout_worker():
    while True:
        time.sleep(2)

        now = time.time()
        with services_lock:
            for service_id, data in services.items():
                last = data.get("last_heartbeat", 0)
                if last and now - last > TIMEOUT_SECONDS and data["status"] != "DOWN":
                    data["status"] = "DOWN"
                    logger.warning(f"Service DOWN: {service_id}")


def main():
    logger.info("Starting monitor...")

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER_HOST, BROKER_PORT, 60)
    except Exception as err:
        logger.error(f"Connection error: {err}")
        return

    threading.Thread(target=timeout_worker, daemon=True).start()
    client.loop_start()

    try:
        while True:
            print_dashboard()
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("Stopping monitor...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()