import json
import socket
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

BROKER_HOST = "mosquitto"
BROKER_PORT = 1883
HEARTBEAT_INTERVAL_SECONDS = 5


def build_payload(service_id: str) -> str:
    payload = {
        "service_id": service_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "alive",
    }
    return json.dumps(payload)


def main() -> None:
    service_id = socket.gethostname()
    topic = f"heartbeat/{service_id}"

    client = mqtt.Client(client_id=f"agent-{service_id}")
    client.connect(BROKER_HOST, BROKER_PORT, 60)
    client.loop_start()

    try:
        while True:
            client.publish(topic, build_payload(service_id), qos=1)
            time.sleep(HEARTBEAT_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
