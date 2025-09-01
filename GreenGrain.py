import uuid, time, threading, json
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, db
import os
import paho.mqtt.client as mqtt

app = Flask(__name__)

# Firebase setup
firebase_config = json.loads(os.getenv("FIREBASE_CREDENTIALS"))
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred)

# Shared monitoring session
session = {
    "is_active": False,
    "owner": None,
    "start_time": None,
    "elapsed": 0,
    "moistures": [],
    "temperatures": [],
    "moisture": None,
    "temperature": None
}

# MQTT setup
MQTT_BROKER = "broker.hivemq.com"  # Or your own broker IP
MQTT_PORT = 1883
MQTT_TOPIC_SENSOR = "greengrain/sensor"

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker with code", rc)
    client.subscribe(MQTT_TOPIC_SENSOR)

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
        moisture = data.get("moisture")
        temperature = data.get("temperature")

        if session["is_active"]:
            session["moisture"] = moisture
            session["temperature"] = temperature
            session["elapsed"] = int(time.time() - session["start_time"]) if session["start_time"] else 0
            if moisture is not None:
                session["moistures"].append(moisture)
            if temperature is not None:
                session["temperatures"].append(temperature)
            print("Updated sensor data:", session)

    except Exception as e:
        print("Failed to process MQTT message:", e)

def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()

# Start MQTT client in a background thread
threading.Thread(target=start_mqtt, daemon=True).start()

# --- Flask endpoints ---

@app.post("/start-monitoring")
def start_monitoring():
    data = request.get_json()
    if not data or not data.get("username"):
        return jsonify({"success": False, "message": "Missing username"}), 400

    username = data["username"]

    if session["is_active"]:
        if session["owner"] != username:
            return jsonify({
                "success": False,
                "message": f"Monitoring already running by {session['owner']}"
            }), 403
        else:
            session.update({
                "start_time": time.time(),
                "elapsed": 0,
                "moistures": [],
                "temperatures": [],
                "moisture": None,
                "temperature": None
            })
            return jsonify({"success": True, "message": "Monitoring restarted", "data": session})

    session.update({
        "is_active": True,
        "owner": username,
        "start_time": time.time(),
        "elapsed": 0,
        "moistures": [],
        "temperatures": [],
        "moisture": None,
        "temperature": None
    })
    return jsonify({"success": True, "message": "Monitoring started", "data": session})

@app.post("/stop-monitoring")
def stop_monitoring():
    data = request.get_json()
    required_keys = ["username", "userId", "startedTime", "endedTime", "duration", "date"]
    if not data or not all(k in data for k in required_keys):
        return jsonify({"success": False, "message": "Missing fields"}), 400

    username = data["username"]

    if session["owner"] != username:
        return jsonify({"success": False, "message": f"Only {session['owner']} can stop the monitoring"}), 403

    if not session["is_active"] or len(session.get("temperatures", [])) == 0:
        return jsonify({"success": False, "message": "No active monitoring session"}), 400

    avg_temp = sum(session["temperatures"]) / len(session["temperatures"])
    avg_moist = sum(session["moistures"]) / len(session["moistures"])
    monitoring_id = str(uuid.uuid4())

    try:
        ref = db.reference(f"users/{data['userId']}/monitoring/{monitoring_id}")
        ref.set({
            "date": data["date"],
            "startingTime": data["startedTime"],
            "endTime": data["endedTime"],
            "duration": data["duration"],
            "averageTemperature": round(avg_temp, 2),
            "averageMoisture": round(avg_moist, 2)
        })
    except Exception as e:
        print("Firebase error:", e)
        return jsonify({"success": False, "message": "Failed to write to Firebase"}), 500

    # Reset session
    session.update({
        "is_active": False,
        "owner": None,
        "start_time": None,
        "elapsed": 0,
        "moistures": [],
        "temperatures": [],
        "moisture": None,
        "temperature": None
    })

    return jsonify({"success": True, "message": "Monitoring stopped", "monitoringId": monitoring_id})

@app.get("/status")
def get_status():
    return jsonify(session)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
