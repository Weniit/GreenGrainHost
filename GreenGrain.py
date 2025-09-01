import uuid
import time
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, db, initialize_app
import os,json

app = Flask(__name__)

# Firebase setup
firebase_config = json.loads(os.getenv("FIREBASE_CREDENTIALS"))
firebase_config["private_key"] = firebase_config["private_key"].replace("\\n", "\n")

cred = credentials.Certificate(firebase_config)
initialize_app(cred, {
    "databaseURL": "https://greengrain-45f6d-default-rtdb.firebaseio.com"
})


# Per-user monitoring sessions
user_sessions = {}


@app.post("/start-monitoring")
def start_monitoring():
    user_id = request.form.get("userId")
    if not user_id:
        return jsonify({"success": False, "message": "Missing userId"}), 400

    # Start a new session for this user regardless of previous sessions
    user_sessions[user_id] = {
        "is_active": True,
        "start_time": time.time(),
        "elapsed": 0,
        "moistures": [],
        "temperatures": [],
        "moisture": None,
        "temperature": None
    }

    return jsonify({"success": True, "message": "Monitoring started"})


@app.post("/update-monitoring")
def update_monitoring():
    user_id = request.form.get("userId")
    if not user_id or user_id not in user_sessions or not user_sessions[user_id]["is_active"]:
        return jsonify({"success": False, "message": "Monitoring not active"}), 400

    try:
        moisture = request.form.get("moisture")
        temperature = request.form.get("temperature")

        if moisture is not None and moisture != "":
            user_sessions[user_id]["moistures"].append(float(moisture))
            user_sessions[user_id]["moisture"] = float(moisture)

        if temperature is not None and temperature != "":
            user_sessions[user_id]["temperatures"].append(float(temperature))
            user_sessions[user_id]["temperature"] = float(temperature)

        user_sessions[user_id]["elapsed"] = int(time.time() - user_sessions[user_id]["start_time"])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.post("/stop-monitoring")
def stop_monitoring():
    user_id = request.form.get("userId")
    username = request.form.get("username")
    start_time = request.form.get("startedTime")
    end_time = request.form.get("endedTime")
    duration = request.form.get("duration")
    date = request.form.get("date")

    if not all([user_id, username, start_time, end_time, duration, date]):
        return jsonify({"success": False, "message": "Missing fields"}), 400

    if user_id not in user_sessions or not user_sessions[user_id]["is_active"]:
        return jsonify({"success": False, "message": "No active monitoring"}), 400

    session = user_sessions[user_id]

    if len(session["temperatures"]) == 0 or len(session["moistures"]) == 0:
        return jsonify({"success": False, "message": "No data recorded"}), 400

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

    # Reset user's session
    del user_sessions[user_id]

    return jsonify({"success": True, "message": "Monitoring stopped", "monitoringId": monitoring_id})


@app.get("/status")
def get_status():
    """Return status of a specific user's session"""
    user_id = request.args.get("userId")
    if not user_id or user_id not in user_sessions:
        return jsonify({"success": False, "message": "No active monitoring"}), 400

    return jsonify(user_sessions[user_id])


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
