import json
import time
import threading
import os

import paho.mqtt.client as mqtt

network_state = {}

BROKER = "localhost"
PORT = 1883

# -----------------------------------
# MQTT CONNECTION
# -----------------------------------

def on_connect(client, userdata, flags, rc):

    print("Connected to MQTT Broker")

    client.subscribe("heartbeat/#")
    client.subscribe("metadata/#")

    print("Subscribed to topics")

# -----------------------------------
# RECEIVE MQTT MESSAGE
# -----------------------------------

def on_message(client, userdata, msg):

    topic = msg.topic
    payload = msg.payload.decode()

    container_name = topic.split("/")[1]

    try:

        data = json.loads(payload)

        network_state[container_name] = data

    except json.JSONDecodeError:

        network_state[container_name] = {
            "status": payload
        }

    network_state[container_name]["last_seen"] = time.time()

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

        for container, data in network_state.items():

            status = data.get("status", "UNKNOWN")

            last_seen = data.get("last_seen", 0)

            delay = current_time - last_seen

            if delay > 10:
                status = "DOWN"

            cpu = data.get("cpu", "-")

            print(f"{container:<10} {status:<8} CPU: {cpu}")

        time.sleep(2)

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
