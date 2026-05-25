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
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)

logger = logging.getLogger("monitor")

services = {}
services_lock = threading.Lock()


def build_service_state(service_id):
    return {
        "service_id": service_id,
        "status": "UNKNOWN",
        "last_heartbeat": 0.0,
        "last_status_change": 0.0,
        "heartbeat_count": 0,
        "message_count": 0,
        "rtt_ms": None,
        "network": {
            "ip": "?",
            "port": "?",
        },
        "metadata": {},
    }


def set_status(service, new_status, now_ts):
    if service.get("status") != new_status:
        service["status"] = new_status
        service["last_status_change"] = now_ts
        logger.info(f"Service {service['service_id']} changed to {new_status}")


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.0f}m"
    return f"{seconds/3600:.1f}h"


def format_timestamp(timestamp):
    if not timestamp:
        return "-"
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


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

    print(
        f"{'SERVICE':<20} {'IP':<16} {'PORT':<8} {'STATUS':<8} "
        f"{'LAST HB':<10} {'LAST CHG':<10} {'RTT':<10}"
    )

    now = time.time()

    with services_lock:
        snapshot = dict(services)

    if not snapshot:
        print("Nenhum servico ativo ainda...")
        return

    for service_id, data in snapshot.items():
        net = data.get("network", {})

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
        last_change = format_timestamp(data.get("last_status_change", 0))
        rtt = data.get("rtt_ms")
        rtt_str = f"{rtt}ms" if rtt is not None else "-"

        print(
            f"{service_id:<20} {ip:<16} {port:<8} {status_str:<8} "
            f"{last_str:<10} {last_change:<10} {rtt_str:<10}"
        )


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
            services[service_id] = build_service_state(service_id)
            logger.info(f"New service detected: {service_id}")

        service = services[service_id]
        now_ts = time.time()
        service["message_count"] += 1

        if msg_type == "metadata":
            service["metadata"] = payload
            network = payload.get("network", {})
            service["network"]["ip"] = network.get("ip", service["network"]["ip"])
            service["network"]["port"] = network.get("port", service["network"]["port"])
            service["last_heartbeat"] = now_ts
            set_status(service, "UP", now_ts)
        elif msg_type == "heartbeat":
            service["heartbeat_count"] += 1
            service["last_heartbeat"] = now_ts
            set_status(service, "UP", now_ts)
            sent_ts_str = payload.get("timestamp")
            if sent_ts_str:
                try:
                    from datetime import timezone
                    sent_dt = datetime.fromisoformat(sent_ts_str)
                    if sent_dt.tzinfo is None:
                        sent_dt = sent_dt.replace(tzinfo=timezone.utc)
                    sent_epoch = sent_dt.timestamp()
                    rtt = (now_ts - sent_epoch) * 1000
                    if 0 <= rtt < 60000:
                        service["rtt_ms"] = round(rtt, 2)
                except (ValueError, TypeError):
                    pass


def timeout_worker():
    while True:
        time.sleep(2)

        now = time.time()
        with services_lock:
            for service_id, data in services.items():
                last = data.get("last_heartbeat", 0)
                if last and now - last > TIMEOUT_SECONDS and data["status"] != "DOWN":
                    set_status(data, "DOWN", now)
                    logger.warning(f"Service DOWN: {service_id}")


def main():
    logger.info("Starting monitor...")

    client = mqtt.Client()
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
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