import json
import logging
import os
import random
import signal
import socket
import time
import paho.mqtt.client as mqtt
from datetime import datetime, timezone




BROKER_HOST = os.getenv("BROKER_HOST", "mosquitto")
BROKER_PORT = int(os.getenv("BROKER_PORT", 1883))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", 5))
PING_TIMEOUT = float(os.getenv("PING_TIMEOUT", 2.0))
SERVICE_PORT = os.getenv("SERVICE_PORT", "NA")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
SERVICE_ID = os.getenv("SERVICE_ID", socket.gethostname())
SERVICE_MODULE = os.getenv("SERVICE_MODULE", "rooms")
SERVICE_TYPE = os.getenv("SERVICE_TYPE", SERVICE_MODULE)
SERVICE_DEPARTMENT = os.getenv("SERVICE_DEPARTMENT", "DETI")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0")
STATUS_INTERVAL = float(os.getenv("STATUS_INTERVAL", 10.0))
DOMAIN_EVENT_INTERVAL = float(os.getenv("DOMAIN_EVENT_INTERVAL", 12.0))
PARKING_FULL_THRESHOLD = int(os.getenv("PARKING_FULL_THRESHOLD", 5))
PARKING_RECOVERED_THRESHOLD = int(os.getenv("PARKING_RECOVERED_THRESHOLD", 15))
ROOM_CLASS_ENDED_PROBABILITY = float(os.getenv("ROOM_CLASS_ENDED_PROBABILITY", 0.35))

TOPIC_PARKING_FULL = "campus/domain/parking/full"
TOPIC_ROOM_CLASS_ENDED = "campus/domain/room/class_ended"
TOPIC_TRANSPORT_BUS_ARRIVED = "campus/domain/transport/bus_arrived"
TOPIC_TRANSPORT_REINFORCEMENT = "campus/domain/transport/reinforcement_dispatched"
TOPIC_CANTEEN_ACTION_PREPARE_PEAK = "campus/domain/canteen/action_prepare_peak"
TOPIC_CANTEEN_EXPECTED_PEAK = "campus/domain/canteen/expected_peak"
TOPIC_LIBRARY_EXPECTED_PEAK = "campus/domain/library/expected_peak"
TOPIC_PARKING_RECOVERED = "campus/domain/parking/recovered"

ROUTE_STOPS = ["DETI", "Biblioteca", "Cantina", "Reitoria"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger("monitor-agent")


def _clamp(value, lower, upper):
    return max(lower, min(upper, value))


def _current_hour_fraction() -> float:
    now = datetime.now()
    return now.hour + (now.minute / 60.0)


def _profile_value(hour_value: float, points):
    points_sorted = sorted(points, key=lambda item: item[0])
    if hour_value <= points_sorted[0][0]:
        return points_sorted[0][1]

    for idx in range(1, len(points_sorted)):
        left_hour, left_val = points_sorted[idx - 1]
        right_hour, right_val = points_sorted[idx]
        if hour_value <= right_hour:
            span = max(0.001, right_hour - left_hour)
            ratio = (hour_value - left_hour) / span
            return left_val + (right_val - left_val) * ratio

    return points_sorted[-1][1]


def _smooth_update(current: float, target: float, max_step: float, jitter: float = 0.6):
    delta = target - current
    bounded = _clamp(delta, -max_step, max_step)
    noisy = bounded + random.uniform(-jitter, jitter)
    return current + noisy


def _init_simulation_state(module_name: str):
    module = module_name.lower()
    base = {
        "module": module,
        "updated_at": time.time(),
        "domain_boost": 0.0,
        "event_boost": 0.0,
    }

    if module in {"rooms", "room", "salas", "sala"}:
        base.update(
            {
                "total_rooms": 10,
                "occupied_rooms": 4,
                "pending_class_ended_students": 0,
            }
        )
    elif module in {"parking", "estacionamento"}:
        base.update(
            {
                "capacity": 120,
                "occupied_spots": 85,
            }
        )
    elif module in {"printing", "printers", "printer", "impressao", "impressora"}:
        base.update(
            {
                "active_printers": 2,
                "queue_size": 4,
                "jobs": 2,
            }
        )
    elif module in {"transport", "transports", "bus", "shuttle"}:
        base.update(
            {
                "route": list(ROUTE_STOPS),
                "stop_index": 0,
                "current_stop": ROUTE_STOPS[0],
                "next_stop": ROUTE_STOPS[1],
                "eta_to_next": 6,
                "capacity_remaining": 28,
                "just_arrived": False,
            }
        )
    elif module in {"canteen", "cantina"}:
        base.update(
            {
                "queue": 8,
                "available_meals": 150,
            }
        )
    elif module in {"library", "biblioteca"}:
        base.update(
            {
                "capacity": 220,
                "occupancy": 80,
            }
        )

    return base


def _update_room_state(sim_state: dict, hour_value: float):
    target_occ = _profile_value(
        hour_value,
        [(0, 1), (8, 2), (9, 6), (10.5, 4), (11, 7), (13, 5), (16, 6), (18, 3), (22, 1), (24, 1)],
    )
    previous = int(sim_state.get("occupied_rooms", 4))
    updated = int(round(_smooth_update(float(previous), float(target_occ), max_step=2.0, jitter=0.4)))
    updated = int(_clamp(updated, 0, int(sim_state.get("total_rooms", 10))))

    if updated < previous:
        ended_students = max(0, int((previous - updated) * 18 + random.randint(-4, 8)))
        sim_state["pending_class_ended_students"] = sim_state.get("pending_class_ended_students", 0) + ended_students

    sim_state["occupied_rooms"] = updated
    sim_state["free_rooms"] = int(sim_state.get("total_rooms", 10)) - updated


def _update_parking_state(sim_state: dict, hour_value: float):
    capacity = int(sim_state.get("capacity", 120))
    target_occ = _profile_value(
        hour_value,
        [(0, 25), (7.5, 60), (8.5, 105), (12, 88), (14, 95), (17, 52), (20, 28), (24, 22)],
    )
    current = float(sim_state.get("occupied_spots", 80))
    boosted_target = target_occ + float(sim_state.get("event_boost", 0.0))
    updated = int(round(_smooth_update(current, boosted_target, max_step=6.0, jitter=1.3)))
    updated = int(_clamp(updated, 0, capacity))

    sim_state["event_boost"] = float(sim_state.get("event_boost", 0.0)) * 0.65
    sim_state["occupied_spots"] = updated
    sim_state["free_spots"] = capacity - updated


def _update_printer_state(sim_state: dict, hour_value: float):
    load_factor = _profile_value(
        hour_value,
        [(0, 0.1), (8, 0.3), (10, 0.7), (12.5, 0.9), (15, 0.6), (18, 0.4), (22, 0.15), (24, 0.1)],
    )
    base_target = 2 + (load_factor * 14) + float(sim_state.get("domain_boost", 0.0))
    queue = float(sim_state.get("queue_size", 4))
    queue_updated = _smooth_update(queue, base_target, max_step=2.4, jitter=0.7)
    queue_updated = _clamp(queue_updated, 0, 45)

    jobs_target = min(queue_updated, 2 + (load_factor * 4))
    jobs_updated = _smooth_update(float(sim_state.get("jobs", 2)), jobs_target, max_step=1.5, jitter=0.4)
    jobs_updated = _clamp(jobs_updated, 0, 10)

    sim_state["domain_boost"] = float(sim_state.get("domain_boost", 0.0)) * 0.7
    sim_state["queue_size"] = int(round(queue_updated))
    sim_state["jobs"] = int(round(jobs_updated))


def _update_transport_state(sim_state: dict, hour_value: float):
    _ = hour_value
    eta = int(sim_state.get("eta_to_next", 5))
    if eta > 0:
        eta -= 1
        sim_state["just_arrived"] = False

    if eta <= 0:
        route = sim_state.get("route", ROUTE_STOPS)
        next_index = (int(sim_state.get("stop_index", 0)) + 1) % len(route)
        sim_state["stop_index"] = next_index
        sim_state["current_stop"] = route[next_index]
        sim_state["next_stop"] = route[(next_index + 1) % len(route)]
        sim_state["just_arrived"] = True
        eta = random.randint(3, 8)

    occupancy_factor = _profile_value(
        hour_value,
        [(0, 0.2), (8, 0.6), (10, 0.8), (12, 0.7), (15, 0.5), (18, 0.75), (21, 0.3), (24, 0.2)],
    )
    target_capacity_remaining = 40 - int(occupancy_factor * 30)
    updated_capacity = int(
        round(
            _smooth_update(
                float(sim_state.get("capacity_remaining", 25)),
                float(target_capacity_remaining),
                max_step=4.0,
                jitter=1.1,
            )
        )
    )
    sim_state["capacity_remaining"] = int(_clamp(updated_capacity, 4, 40))
    sim_state["eta_to_next"] = eta


def _update_canteen_state(sim_state: dict, hour_value: float):
    demand_factor = _profile_value(
        hour_value,
        [(0, 0.08), (8, 0.18), (11.5, 0.9), (13.5, 1.0), (15, 0.3), (19, 0.8), (21, 0.35), (24, 0.1)],
    )
    queue_target = 3 + (demand_factor * 35) + float(sim_state.get("domain_boost", 0.0))
    queue = _smooth_update(float(sim_state.get("queue", 8)), queue_target, max_step=3.0, jitter=0.8)
    queue = _clamp(queue, 0, 60)

    meals_target = 190 - (queue * 2.0)
    meals = _smooth_update(float(sim_state.get("available_meals", 150)), meals_target, max_step=7.5, jitter=2.2)
    meals = _clamp(meals, 20, 220)

    sim_state["domain_boost"] = float(sim_state.get("domain_boost", 0.0)) * 0.72
    sim_state["queue"] = int(round(queue))
    sim_state["available_meals"] = int(round(meals))


def _update_library_state(sim_state: dict, hour_value: float):
    capacity = int(sim_state.get("capacity", 220))
    demand_factor = _profile_value(
        hour_value,
        [(0, 0.1), (8, 0.25), (11, 0.45), (14, 0.78), (17, 0.88), (20, 0.5), (22, 0.25), (24, 0.12)],
    )
    occ_target = 25 + (demand_factor * 170) + float(sim_state.get("domain_boost", 0.0))
    current = float(sim_state.get("occupancy", 80))
    updated = _smooth_update(current, occ_target, max_step=5.0, jitter=1.0)
    updated = _clamp(updated, 0, capacity)

    sim_state["domain_boost"] = float(sim_state.get("domain_boost", 0.0)) * 0.74
    sim_state["occupancy"] = int(round(updated))
    sim_state["free_seats"] = int(capacity - sim_state["occupancy"])


def _update_simulation_state(sim_state: dict):
    hour_value = _current_hour_fraction()
    module = str(sim_state.get("module", "")).lower()

    if module in {"rooms", "room", "salas", "sala"}:
        _update_room_state(sim_state, hour_value)
    elif module in {"parking", "estacionamento"}:
        _update_parking_state(sim_state, hour_value)
    elif module in {"printing", "printers", "printer", "impressao", "impressora"}:
        _update_printer_state(sim_state, hour_value)
    elif module in {"transport", "transports", "bus", "shuttle"}:
        _update_transport_state(sim_state, hour_value)
    elif module in {"canteen", "cantina"}:
        _update_canteen_state(sim_state, hour_value)
    elif module in {"library", "biblioteca"}:
        _update_library_state(sim_state, hour_value)

    sim_state["updated_at"] = time.time()


def get_container_ip():
    """Obtém o IP atual do container na rede Docker."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.connect((BROKER_HOST, BROKER_PORT))
        return sock.getsockname()[0]

    except OSError as err:
        logger.warning(f"Não foi possível obter IP pela interface MQTT: {err}")

        try:
            return socket.gethostbyname(socket.gethostname())

        except socket.error:
            return "unknown"

    finally:
        sock.close()


def current_timestamp():
    return datetime.now(timezone.utc).isoformat()


def build_metadata(service_id, container_ip):
    return {
        "type": "metadata",
        "version": "1.0",
        "service_id": service_id,
        "container_name": service_id,
        "network": {
            "ip": container_ip,
            "port": SERVICE_PORT
        },
        "timestamp": current_timestamp()
    }


def build_register(service_id, container_ip):
    return {
        "type": "register",
        "service_id": service_id,
        "module": SERVICE_MODULE,
        "service_type": SERVICE_TYPE,
        "department": SERVICE_DEPARTMENT,
        "version": SERVICE_VERSION,
        "network": {
            "ip": container_ip,
            "port": SERVICE_PORT,
        },
        "timestamp": current_timestamp(),
    }


def build_unregister(service_id, reason="shutdown"):
    return {
        "type": "unregister",
        "service_id": service_id,
        "reason": reason,
        "timestamp": current_timestamp(),
    }


def build_heartbeat(service_id):
    return {
        "type": "heartbeat",
        "service_id": service_id,
        "status": "alive",
        "timestamp": current_timestamp()
    }


def build_service_status(service_id, sim_state):
    _update_simulation_state(sim_state)
    module = SERVICE_MODULE.lower()
    base = {
        "type": "status",
        "service_id": service_id,
        "module": SERVICE_MODULE,
        "timestamp": current_timestamp(),
    }

    if module in {"rooms", "room", "salas", "sala"}:
        base.update({
            "free_rooms": int(sim_state.get("free_rooms", 0)),
            "occupied_rooms": int(sim_state.get("occupied_rooms", 0)),
            "total_rooms": int(sim_state.get("total_rooms", 10)),
        })
    elif module in {"parking", "estacionamento"}:
        base.update({
            "free_spots": int(sim_state.get("free_spots", 0)),
            "occupied_spots": int(sim_state.get("occupied_spots", 0)),
            "capacity": int(sim_state.get("capacity", 120)),
        })
    elif module in {"printing", "printers", "printer", "impressao", "impressora"}:
        base.update({
            "jobs": int(sim_state.get("jobs", 0)),
            "queue_size": int(sim_state.get("queue_size", 0)),
            "active_printers": int(sim_state.get("active_printers", 2)),
        })
    elif module in {"transport", "transports", "bus", "shuttle"}:
        base.update({
            "current_stop": str(sim_state.get("current_stop", "DETI")),
            "next_stop": str(sim_state.get("next_stop", "Biblioteca")),
            "eta": f"{int(sim_state.get('eta_to_next', 0))}m",
            "capacity_remaining": int(sim_state.get("capacity_remaining", 20)),
        })
    elif module in {"canteen", "cantina"}:
        base.update({
            "avg_queue": int(sim_state.get("queue", 0)),
            "available_meals": int(sim_state.get("available_meals", 0)),
        })
    elif module in {"library", "biblioteca"}:
        base.update({
            "occupancy": int(sim_state.get("occupancy", 0)),
            "free_seats": int(sim_state.get("free_seats", 0)),
            "capacity": int(sim_state.get("capacity", 220)),
        })
    else:
        base.update({"health": "ok"})

    return base


def build_pong(service_id, ping_id, sent_at):
    return {
        "type": "pong",
        "service_id": service_id,
        "ping_id": ping_id,
        "sent_at": sent_at,
        "timestamp": current_timestamp(),
    }


def build_domain_event(service_id, event_type, data=None, severity="info"):
    return {
        "type": "domain_event",
        "event_type": event_type,
        "producer_service": service_id,
        "module": SERVICE_MODULE,
        "department": SERVICE_DEPARTMENT,
        "timestamp": current_timestamp(),
        "severity": severity,
        "data": data or {},
    }


def publish_domain_event(client, topic, payload):
    result = client.publish(topic, json.dumps(payload), qos=1)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info(f"Evento de dominio publicado: topic={topic} event={payload.get('event_type')}")
    else:
        logger.warning(f"Falha ao publicar evento de dominio em {topic}")


def get_domain_subscriptions(module_name):
    module = module_name.lower()
    if module == "transport":
        return [TOPIC_PARKING_FULL]
    if module in {"canteen", "cantina", "library"}:
        return [
            TOPIC_ROOM_CLASS_ENDED,
            TOPIC_TRANSPORT_BUS_ARRIVED,
        ]
    if module in {"printing", "printers", "printer", "impressao", "impressora"}:
        return [TOPIC_ROOM_CLASS_ENDED]
    return []


def _can_publish_with_cooldown(cooldowns, key, min_interval=8.0):
    now_ts = time.time()
    last_ts = cooldowns.get(key, 0.0)
    if now_ts - last_ts < min_interval:
        return False
    cooldowns[key] = now_ts
    return True


def _handle_domain_event_message(client, userdata, topic, payload):
    service_id = userdata.get("service_id")
    module = str(userdata.get("module", "")).lower()
    cooldowns = userdata.setdefault("domain_cooldowns", {})
    source_service = payload.get("producer_service")
    sim_state = userdata.get("sim_state", {})

    if topic == TOPIC_ROOM_CLASS_ENDED:
        if module in {"canteen", "cantina"}:
            sim_state["domain_boost"] = float(sim_state.get("domain_boost", 0.0)) + 7.0
        if module in {"library", "biblioteca"}:
            sim_state["domain_boost"] = float(sim_state.get("domain_boost", 0.0)) + 9.0
        if module in {"printing", "printers", "printer", "impressao", "impressora"}:
            sim_state["domain_boost"] = float(sim_state.get("domain_boost", 0.0)) + 6.0

    if topic == TOPIC_TRANSPORT_BUS_ARRIVED:
        if module in {"canteen", "cantina"}:
            sim_state["domain_boost"] = float(sim_state.get("domain_boost", 0.0)) + 5.0
        if module in {"library", "biblioteca"}:
            sim_state["domain_boost"] = float(sim_state.get("domain_boost", 0.0)) + 6.5

    if module == "transport" and topic == TOPIC_PARKING_FULL:
        sim_state["event_boost"] = float(sim_state.get("event_boost", 0.0)) + 8.0
        if _can_publish_with_cooldown(cooldowns, "transport_reinforcement", min_interval=10.0):
            event_payload = build_domain_event(
                service_id,
                "reinforcement_dispatched",
                {
                    "source_event": "parking_full",
                    "triggered_by": source_service,
                    "action": "extra_shuttle_dispatched",
                },
                severity="warning",
            )
            publish_domain_event(client, TOPIC_TRANSPORT_REINFORCEMENT, event_payload)

    if module in {"canteen", "cantina"} and topic in {
        TOPIC_ROOM_CLASS_ENDED,
        TOPIC_TRANSPORT_BUS_ARRIVED,
    }:
        if _can_publish_with_cooldown(cooldowns, "canteen_prepare_peak", min_interval=8.0):
            prepare_payload = build_domain_event(
                service_id,
                "action_prepare_peak",
                {
                    "source_topic": topic,
                    "triggered_by": source_service,
                    "action": "open_extra_line",
                },
            )
            publish_domain_event(client, TOPIC_CANTEEN_ACTION_PREPARE_PEAK, prepare_payload)

        if _can_publish_with_cooldown(cooldowns, "canteen_expected_peak", min_interval=8.0):
            peak_payload = build_domain_event(
                service_id,
                "expected_peak",
                {
                    "source_topic": topic,
                    "triggered_by": source_service,
                    "expected_queue_increase": random.randint(10, 35),
                },
                severity="warning",
            )
            publish_domain_event(client, TOPIC_CANTEEN_EXPECTED_PEAK, peak_payload)

    if module == "library" and topic in {
        TOPIC_ROOM_CLASS_ENDED,
        TOPIC_TRANSPORT_BUS_ARRIVED,
    }:
        if _can_publish_with_cooldown(cooldowns, "library_expected_peak", min_interval=8.0):
            peak_payload = build_domain_event(
                service_id,
                "expected_peak",
                {
                    "source_topic": topic,
                    "triggered_by": source_service,
                    "expected_new_visitors": random.randint(8, 30),
                },
                severity="warning",
            )
            publish_domain_event(client, TOPIC_LIBRARY_EXPECTED_PEAK, peak_payload)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Ligação ao broker MQTT estabelecida")
        service_id = userdata.get("service_id") if isinstance(userdata, dict) else None
        if service_id:
            client.subscribe(f"monitor/{service_id}/ping")
        if isinstance(userdata, dict):
            for topic in userdata.get("domain_subscriptions", []):
                client.subscribe(topic)
                logger.info(f"Subscrito ao topico de dominio: {topic}")

            # Re-publica estado base no connect/reconnect para bootstrap rápido do monitor.
            register_topic = userdata.get("register_topic")
            metadata_topic = userdata.get("metadata_topic")
            status_topic = userdata.get("status_topic")
            container_ip = userdata.get("container_ip")
            sim_state = userdata.get("sim_state")

            if service_id and container_ip and register_topic:
                publish_register(client, register_topic, service_id, container_ip)
            if service_id and container_ip and metadata_topic:
                publish_metadata(client, metadata_topic, service_id, container_ip)
            if service_id and status_topic and sim_state is not None:
                publish_status(client, status_topic, service_id, sim_state)
    else:
        logger.error(f"Falha na ligação MQTT (rc={rc})")


def on_disconnect(client, userdata, rc):
    if rc != 0:
        logger.warning("Ligação MQTT perdida. A tentar reconectar...")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        logger.warning("Mensagem MQTT inválida recebida")
        return

    if msg.topic.startswith("campus/domain/"):
        _handle_domain_event_message(client, userdata, msg.topic, payload)
        return

    if payload.get("type") != "ping":
        return

    service_id = payload.get("service_id")
    ping_id = payload.get("ping_id")
    sent_at = payload.get("sent_at")
    if not service_id or not ping_id or sent_at is None:
        logger.warning("Ping MQTT sem campos obrigatórios")
        return

    pong_topic = f"monitor/{service_id}/pong"
    pong = build_pong(service_id, ping_id, sent_at)

    result = client.publish(
        pong_topic,
        json.dumps(pong),
        qos=1
    )

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info(f"Pong enviado: {service_id} | ping_id={ping_id}")
    else:
        logger.warning(f"Falha ao enviar pong para {service_id}")


def connect_mqtt(service_id, domain_subscriptions, sim_state, register_topic, metadata_topic, status_topic, container_ip):
    client = mqtt.Client(client_id=f"agent-{service_id}")
    client.user_data_set(
        {
            "service_id": service_id,
            "module": SERVICE_MODULE,
            "domain_subscriptions": domain_subscriptions,
            "domain_cooldowns": {},
            "sim_state": sim_state,
            "register_topic": register_topic,
            "metadata_topic": metadata_topic,
            "status_topic": status_topic,
            "container_ip": container_ip,
        }
    )

    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    client.reconnect_delay_set(min_delay=1, max_delay=10)

    logger.info(f"A conectar ao broker MQTT em {BROKER_HOST}:{BROKER_PORT}")

    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()

    return client


def publish_metadata(client, topic, service_id, container_ip):
    metadata = build_metadata(service_id, container_ip)

    result = client.publish(
        topic,
        json.dumps(metadata),
        qos=1,
        retain=True
    )

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info(
            f"Metadata publicada | IP={metadata['network']['ip']} "
            f"PORT={metadata['network']['port']}"
        )
    else:
        logger.error("Erro ao publicar metadata")


def publish_register(client, topic, service_id, container_ip):
    payload = build_register(service_id, container_ip)
    result = client.publish(topic, json.dumps(payload), qos=1, retain=True)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info(f"REGISTER enviado: {service_id} | module={SERVICE_MODULE} dept={SERVICE_DEPARTMENT}")
    else:
        logger.error("Erro ao publicar register")


def publish_unregister(client, topic, service_id, reason="shutdown"):
    payload = build_unregister(service_id, reason)
    result = client.publish(topic, json.dumps(payload), qos=1, retain=False)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info(f"UNREGISTER enviado: {service_id} | reason={reason}")
    else:
        logger.warning("Falha ao publicar unregister")


def publish_status(client, topic, service_id, sim_state):
    payload = build_service_status(service_id, sim_state)
    result = client.publish(topic, json.dumps(payload), qos=1, retain=True)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info(f"Status enviado: {service_id} | module={SERVICE_MODULE}")
    else:
        logger.warning("Falha ao publicar status")
    return payload


def _maybe_publish_periodic_domain_event(client, service_id, domain_state, latest_status):
    module = SERVICE_MODULE.lower()

    if module == "parking":
        free_spots = int(latest_status.get("free_spots", 0) or 0)
        is_full = bool(domain_state.get("parking_full_active", False))

        if free_spots <= PARKING_FULL_THRESHOLD and not is_full:
            payload = build_domain_event(
                service_id,
                "parking_full",
                {
                    "free_spots": free_spots,
                    "module": SERVICE_MODULE,
                    "threshold": PARKING_FULL_THRESHOLD,
                },
                severity="warning",
            )
            publish_domain_event(client, TOPIC_PARKING_FULL, payload)
            domain_state["parking_full_active"] = True

        elif free_spots > PARKING_RECOVERED_THRESHOLD and is_full:
            payload = build_domain_event(
                service_id,
                "parking_recovered",
                {
                    "free_spots": free_spots,
                    "module": SERVICE_MODULE,
                    "threshold": PARKING_RECOVERED_THRESHOLD,
                },
            )
            publish_domain_event(client, TOPIC_PARKING_RECOVERED, payload)
            domain_state["parking_full_active"] = False

    elif module in {"rooms", "room", "salas", "sala"}:
        pending_students = int(domain_state.get("pending_class_ended_students", 0) or 0)
        if pending_students > 0 and random.random() < ROOM_CLASS_ENDED_PROBABILITY:
            estimated = int(_clamp(pending_students, 8, 120))
            payload = build_domain_event(
                service_id,
                "class_ended",
                {
                    "room_id": f"R-{random.randint(1, 20)}",
                    "estimated_students": estimated,
                    "probability": ROOM_CLASS_ENDED_PROBABILITY,
                },
            )
            publish_domain_event(client, TOPIC_ROOM_CLASS_ENDED, payload)
            domain_state["pending_class_ended_students"] = max(0, pending_students - estimated)

    elif module in {"transport", "transports", "bus", "shuttle"}:
        if domain_state.get("just_arrived"):
            payload = build_domain_event(
                service_id,
                "bus_arrived",
                {
                    "current_stop": latest_status.get("current_stop", "DETI"),
                    "eta": "0m",
                    "capacity_remaining": int(latest_status.get("capacity_remaining", 20) or 20),
                },
            )
            publish_domain_event(client, TOPIC_TRANSPORT_BUS_ARRIVED, payload)
            domain_state["just_arrived"] = False


def heartbeat_loop(client, heartbeat_topic, status_topic, service_id, sim_state, keep_running):
    last_status_at = 0.0
    last_domain_event_at = 0.0
    latest_status_payload = {}
    domain_state = {"parking_full_active": False}

    while keep_running():
        heartbeat = build_heartbeat(service_id)

        result = client.publish(
            heartbeat_topic,
            json.dumps(heartbeat),
            qos=1
        )

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"Heartbeat enviado: {service_id}")
        else:
            logger.warning("Falha ao enviar heartbeat")

        now = time.time()
        if now - last_status_at >= STATUS_INTERVAL:
            latest_status_payload = publish_status(client, status_topic, service_id, sim_state)
            if SERVICE_MODULE.lower() in {"rooms", "room", "salas", "sala"}:
                domain_state["pending_class_ended_students"] = int(sim_state.get("pending_class_ended_students", 0) or 0)
            if SERVICE_MODULE.lower() in {"transport", "transports", "bus", "shuttle"}:
                domain_state["just_arrived"] = bool(sim_state.get("just_arrived", False))
            last_status_at = now

        if now - last_domain_event_at >= DOMAIN_EVENT_INTERVAL:
            _maybe_publish_periodic_domain_event(client, service_id, domain_state, latest_status_payload)
            last_domain_event_at = now

        time.sleep(HEARTBEAT_INTERVAL)


def main():
    service_id = SERVICE_ID
    container_ip = get_container_ip()
    logger.info(f"IP do container: {container_ip}")

    register_topic = f"monitor/{service_id}/register"
    unregister_topic = f"monitor/{service_id}/unregister"
    metadata_topic = f"monitor/{service_id}/metadata"
    heartbeat_topic = f"monitor/{service_id}/heartbeat"
    status_topic = f"monitor/{service_id}/status"

    domain_subscriptions = get_domain_subscriptions(SERVICE_MODULE)
    sim_state = _init_simulation_state(SERVICE_MODULE)
    client = connect_mqtt(
        service_id,
        domain_subscriptions,
        sim_state,
        register_topic,
        metadata_topic,
        status_topic,
        container_ip,
    )
    should_run = {"value": True}

    def _stop_handler(_signum, _frame):
        should_run["value"] = False

    signal.signal(signal.SIGINT, _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)

    try:
        heartbeat_loop(client, heartbeat_topic, status_topic, service_id, sim_state, lambda: should_run["value"])

    except KeyboardInterrupt:
        logger.info("Encerrando agente...")

    except Exception as err:
        logger.exception(f"Erro inesperado: {err}")

    finally:
        publish_unregister(client, unregister_topic, service_id)
        time.sleep(0.2)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()