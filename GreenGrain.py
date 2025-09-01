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

# Per-user sessions
sessions = {}

# MQTT setup
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC_SENSOR = "greengrain/sensor"

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker with code", rc)
    client.subscribe(MQTT_TOPIC_SENSOR)

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)

        moisture = float(data.get("moisture", 0))
        temperature = float(data.get("temperature", 0))

        # Update all active sessions
        for username, session in sessions.items():
            if session["is_active"]:
                session["moisture"] = moisture
                session["temperature"] = temperature
                session["elapsed"] = int(time.time() - session["start_time"])
                session["moistures"].append(moisture)
                session["temperatures"].append(temperature)
    except Exception as e:
        print("MQTT message processing error:", e)

def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_forever()
        except Exception as e:
            print("MQTT connection failed, retrying in 5s:", e)
            time.sleep(5)

# Start MQTT client in background
threading.Thread(target=start_mqtt, daemon=True).start()

# --- Flask endpoints ---

@app.post("/start-monitoring")
def start_monitoring():
    data = request.get_json()
    username = data.get("username")
    if not username:
        return jsonify({"success": False, "message": "Missing username"}), 400

    session = {
        "is_active": True,
        "start_time": time.time(),
        "elapsed": 0,
        "moistures": [],
        "temperatures": [],
        "moisture": None,
        "temperature": None
    }
    sessions[username] = session
    return jsonify({"success": True, "message": "Monitoring started", "data": session})

@app.post("/stop-monitoring")
def stop_monitoring():
    data = request.get_json()
    username = data.get("username")
    if username not in sessions or not sessions[username]["is_active"]:
        return jsonify({"success": False, "message": "No active session"}), 400

    session = sessions[username]
    avg_temp = round(sum(session["temperatures"]) / len(session["temperatures"]), 2) if session["temperatures"] else None
    avg_moist = round(sum(session["moistures"]) / len(session["moistures"]), 2) if session["moistures"] else None
    monitoring_id = str(uuid.uuid4())

    try:
        ref = db.reference(f"users/{data['userId']}/monitoring/{monitoring_id}")
        ref.set({
            "date": data["date"],
            "startingTime": data["startedTime"],
            "endTime": data["endedTime"],
            "duration": data["duration"],
            "averageTemperature": avg_temp,
            "averageMoisture": avg_moist
        })
    except Exception as e:
        print("Firebase error:", e)
        return jsonify({"success": False, "message": "Failed to write to Firebase"}), 500

    del sessions[username]
    return jsonify({"success": True, "message": "Monitoring stopped", "monitoringId": monitoring_id})

@app.get("/status/<username>")
def get_status(username):
    session = sessions.get(username)
    if not session:
        return jsonify({"is_active": False})
    if session["is_active"] and session["start_time"]:
        session["elapsed"] = int(time.time() - session["start_time"])
    return jsonify(session)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
