import json
import logging
import os
import socket
import time
import paho.mqtt.client as mqtt
from datetime import datetime, timezone


BROKER_HOST = os.getenv("BROKER_HOST", "mosquitto")
BROKER_PORT = int(os.getenv("BROKER_PORT", 1883))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", 5))
SERVICE_PORT = os.getenv("SERVICE_PORT", "NA")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger("monitor-agent")


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


def build_heartbeat(service_id):
    return {
        "type": "heartbeat",
        "service_id": service_id,
        "status": "alive",
        "timestamp": current_timestamp()
    }


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Ligação ao broker MQTT estabelecida")
    else:
        logger.error(f"Falha na ligação MQTT (rc={rc})")


def on_disconnect(client, userdata, rc):
    if rc != 0:
        logger.warning("Ligação MQTT perdida. A tentar reconectar...")


def connect_mqtt(service_id):
    client = mqtt.Client(client_id=f"agent-{service_id}")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    client.reconnect_delay_set(min_delay=1, max_delay=10)

    logger.info(f"A conectar ao broker MQTT em {BROKER_HOST}:{BROKER_PORT}")

    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()

    return client


def publish_metadata(client, topic, service_id, container_ip):
    """Agora recebe o IP como parâmetro."""
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


def heartbeat_loop(client, topic, service_id):
    while True:
        heartbeat = build_heartbeat(service_id)

        result = client.publish(
            topic,
            json.dumps(heartbeat),
            qos=1
        )

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"Heartbeat enviado: {service_id}")
        else:
            logger.warning("Falha ao enviar heartbeat")

        time.sleep(HEARTBEAT_INTERVAL)


def main():
    service_id = socket.gethostname()
    
    container_ip = get_container_ip()
    logger.info(f"IP do container: {container_ip}")

    metadata_topic = f"monitor/{service_id}/metadata"
    heartbeat_topic = f"monitor/{service_id}/heartbeat"

    client = connect_mqtt(service_id)

    try:
        publish_metadata(client, metadata_topic, service_id, container_ip)
        heartbeat_loop(client, heartbeat_topic, service_id)

    except KeyboardInterrupt:
        logger.info("Encerrando agente...")

    except Exception as err:
        logger.exception(f"Erro inesperado: {err}")

    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
