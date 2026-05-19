import json
import os
import threading
import time

import paho.mqtt.client as mqtt

network_state = {}
state_lock = threading.Lock()

BROKER = os.getenv("BROKER_HOST", "mosquitto")
PORT = int(os.getenv("BROKER_PORT", 1883))
DOWN_TIMEOUT_SECONDS = int(os.getenv("DOWN_TIMEOUT", 10))
REFRESH_INTERVAL_SECONDS = 2

# -----------------------------------
# MQTT CONNECTION
# -----------------------------------

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker")
    else:
        print(f"MQTT connection failed with code {rc}")

    client.subscribe("heartbeat/#")
    client.subscribe("metadata/#")

    print("Subscribed to topics")

# -----------------------------------
# RECEIVE MQTT MESSAGE
# -----------------------------------

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()

    topic_parts = topic.split("/", 1)
    if len(topic_parts) != 2:
        return

    container_name = topic_parts[1]

    current_time = time.time()

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        data = {"status": payload}

    with state_lock:
        current_entry = network_state.get(container_name, {})
        current_entry.update(data)
        current_entry["last_seen"] = current_time
        current_entry["status"] = "UP"
        network_state[container_name] = current_entry

# -----------------------------------
# DASHBOARD
# -----------------------------------

def dashboard():
    while True:
        os.system("clear")

        print("==========================")
        print("   NETWORK STATUS")
        print("==========================\n")

        current_time = time.time()

        with state_lock:
            for container, data in network_state.items():
                last_seen = data.get("last_seen", 0)
                delay = current_time - last_seen

                if delay > DOWN_TIMEOUT_SECONDS:
                    data["status"] = "DOWN"

                status = data.get("status", "UNKNOWN")
                cpu = data.get("cpu", "-")
                print(
                    f"{container:<20} {status:<6} CPU: {cpu:<6} "
                    f"Last heartbeat: {delay:>5.1f}s ago"
                )

        time.sleep(REFRESH_INTERVAL_SECONDS)

# -----------------------------------
# START DASHBOARD THREAD
# -----------------------------------

dashboard_thread = threading.Thread(target=dashboard)

dashboard_thread.daemon = True

dashboard_thread.start()

# -----------------------------------
# START MQTT CLIENT
# -----------------------------------

client = mqtt.Client()

client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)

client.loop_forever()
