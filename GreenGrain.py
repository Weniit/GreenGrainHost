import uuid, time, threading, requests
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, db
import os, json

app = Flask(__name__)

# Firebase setup
firebase_config = json.loads(os.getenv("FIREBASE_CREDENTIALS"))
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred)


ESP32_URL = "http://esp32.local/"

# Shared monitoring session
session = {
    "is_active": False,
    "start_time": None,
    "elapsed": 0,
    "moistures": [],
    "temperatures": [],
    "moisture": None,
    "temperature": None
}


def poll_esp32():
    while True:
        if session["is_active"]:
            try:
                resp = requests.get(ESP32_URL, timeout=3)
                data = resp.json()
                session["moisture"] = data.get("moisture")
                session["temperature"] = float(data.get("temperature", 0))
                session["elapsed"] = int(time.time() - session["start_time"])
                # Save history
                if session["temperature"] is not None:
                    session["temperatures"].append(session["temperature"])
                if session["moisture"] is not None:
                    session["moistures"].append(session["moisture"])
            except Exception as e:
                print("ESP32 fetch failed:", e)
        time.sleep(3)


threading.Thread(target=poll_esp32, daemon=True).start()


@app.post("/start-monitoring")
def start_monitoring():
    if session["is_active"]:
        return jsonify({"success": False, "message": "Already running"}), 400

    session["is_active"] = True
    session["start_time"] = time.time()
    session["elapsed"] = 0
    session["moistures"] = []
    session["temperatures"] = []
    return jsonify({"success": True, "message": "Monitoring started"})


@app.post("/stop-monitoring")
def stop_monitoring():
    username = request.form.get('username')
    start_time = request.form.get('startedTime')
    end_time = request.form.get('endedTime')
    duration = request.form.get('duration')
    date = request.form.get('date')
    user_id = request.form.get('userId')

    if not all([username, start_time, end_time, duration, date, user_id]):
        return jsonify({"success": False, "message": "Missing fields"}), 400

    if len(session["temperatures"]) == 0:
        return jsonify({"success": False, "message": "No data found"}), 400

    avg_temp = sum(session["temperatures"]) / len(session["temperatures"])
    avg_moist = sum(session["moistures"]) / len(session["moistures"])

    monitoring_id = str(uuid.uuid4())
    try:
        ref = db.reference(f"users/{user_id}/monitoring/{monitoring_id}")
        ref.set({
            "date": date,
            "startingTime": start_time,
            "endTime": end_time,
            "duration": duration,
            "averageTemperature": round(avg_temp, 2),
            "averageMoisture": round(avg_moist, 2)
        })
    except Exception as e:
        print("Firebase error:", e)
        return jsonify({"success": False, "message": "Failed to write to Firebase"}), 500

    # Reset session
    session["is_active"] = False
    session["start_time"] = None
    session["elapsed"] = 0
    session["moistures"] = []
    session["temperatures"] = []
    session["moisture"] = None
    session["temperature"] = None

    return jsonify({"success": True, "message": "Monitoring stopped", "monitoringId": monitoring_id})


@app.get("/status")
def get_status():
    """Any user can check live monitoring data"""
    return jsonify(session)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
