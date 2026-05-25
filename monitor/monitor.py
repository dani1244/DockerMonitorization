import json
import logging
import os
import uuid
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

BROKER_HOST = os.getenv("BROKER_HOST", "localhost")
BROKER_PORT = int(os.getenv("BROKER_PORT", 1883))
TIMEOUT_SECONDS = int(os.getenv("DOWN_TIMEOUT", os.getenv("TIMEOUT_SECONDS", 15)))
MAX_MISSED_CHECKS = int(os.getenv("MAX_MISSED_CHECKS", 2))
PING_INTERVAL_SECONDS = float(os.getenv("PING_INTERVAL_SECONDS", 5.0))
PING_RESPONSE_TIMEOUT = float(os.getenv("PING_RESPONSE_TIMEOUT", 2.0))
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


def build_service_state(service_id):
    return {
        "service_id": service_id,
        "status": "UNKNOWN",
        "last_heartbeat": 0.0,
        "last_status_change": 0.0,
        "heartbeat_count": 0,
        "message_count": 0,
        "missed_checks": 0,
        "last_ping_id": None,
        "ping_sent_at": 0.0,
        "pending_ping": False,
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
        f"{'LAST HB':<10} {'LAST CHG':<10} {'RTT':<10} {'PING':<8}"
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
        ping_status = "WAIT" if data.get("pending_ping") else "-"

        print(
            f"{service_id:<20} {ip:<16} {port:<8} {status_str:<8} "
            f"{last_str:<10} {last_change:<10} {rtt_str:<10} {ping_status:<8}"
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
            service["missed_checks"] = 0
            set_status(service, "UP", now_ts)
        elif msg_type == "heartbeat":
            service["heartbeat_count"] += 1
            service["last_heartbeat"] = now_ts
            service["missed_checks"] = 0
            set_status(service, "UP", now_ts)
        elif msg_type == "pong":
            ping_id = payload.get("ping_id")
            sent_at = payload.get("sent_at")
            if ping_id and sent_at is not None and ping_id == service.get("last_ping_id"):
                try:
                    rtt = (now_ts - float(sent_at)) * 1000
                    if 0 <= rtt < 60000:
                        service["rtt_ms"] = round(rtt, 2)
                        service["pending_ping"] = False
                        logger.info(f"RTT for {service_id}: {service['rtt_ms']} ms")
                except (TypeError, ValueError):
                    logger.warning(f"Invalid RTT pong payload from {service_id}")


def timeout_worker():
    while True:
        time.sleep(2)

        now = time.time()
        with services_lock:
            for service_id, data in services.items():
                last = data.get("last_heartbeat", 0)
                if not last:
                    continue

                elapsed = now - last
                if elapsed > TIMEOUT_SECONDS:
                    data["missed_checks"] = data.get("missed_checks", 0) + 1
                    if data["missed_checks"] >= MAX_MISSED_CHECKS and data["status"] != "DOWN":
                        set_status(data, "DOWN", now)
                        logger.warning(
                            f"Service DOWN: {service_id} "
                            f"(missed_checks={data['missed_checks']}, elapsed={elapsed:.1f}s)"
                        )


def ping_worker(client):
    while True:
        time.sleep(PING_INTERVAL_SECONDS)

        now = time.time()

        with services_lock:
            for service_id, data in services.items():
                ping_sent_at = data.get("ping_sent_at", 0.0)
                if data.get("pending_ping") and ping_sent_at and now - ping_sent_at > PING_RESPONSE_TIMEOUT:
                    data["pending_ping"] = False
                    logger.warning(f"Ping timeout for {service_id}; allowing new RTT probe")

            targets = [
                (service_id, data)
                for service_id, data in services.items()
                if data.get("status") == "UP" and not data.get("pending_ping")
            ]

            for service_id, data in targets:
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
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    data["last_ping_id"] = ping_id
                    data["ping_sent_at"] = sent_at
                    data["pending_ping"] = True
                    logger.info(f"Ping enviado para {service_id} | ping_id={ping_id}")
                else:
                    logger.warning(f"Falha ao publicar ping para {service_id}")


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
    threading.Thread(target=ping_worker, args=(client,), daemon=True).start()
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