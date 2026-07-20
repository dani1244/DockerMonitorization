import json
import time
from queue import Queue

import paho.mqtt.client as mqtt


def build_mqtt_client(settings, ingest_queue: Queue, logger):
    client = mqtt.Client()

    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

    def on_connect(mqtt_client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"Connected to MQTT broker {settings.broker_host}:{settings.broker_port}")
            mqtt_client.subscribe("monitor/+/register")
            mqtt_client.subscribe("monitor/+/unregister")
            mqtt_client.subscribe("monitor/+/metadata")
            mqtt_client.subscribe("monitor/+/heartbeat")
            mqtt_client.subscribe("monitor/+/status")
            mqtt_client.subscribe("monitor/+/pong")
            mqtt_client.subscribe("campus/domain/#")
        else:
            logger.error(f"MQTT connection failed: {rc}")

    def on_message(_mqtt_client, _userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            logger.warning("Invalid JSON received")
            return

        ingest_queue.put(
            {
                "topic": msg.topic,
                "payload": payload,
                "received_at": time.time(),
            }
        )

    client.on_connect = on_connect
    client.on_message = on_message

    return client
