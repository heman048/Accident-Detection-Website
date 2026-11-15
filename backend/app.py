import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import cv2
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
MODEL_PATH = Path(os.getenv("MODEL_PATH", BASE_DIR / "models" / "best.pt"))
DB_PATH = BASE_DIR / "accidents.db"

for folder in (UPLOAD_DIR, OUTPUT_DIR, BASE_DIR / "models"):
    folder.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 150 * 1024 * 1024  # 150 MB
model = None


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                media_type TEXT NOT NULL,
                original_name TEXT NOT NULL,
                status TEXT NOT NULL,
                detections INTEGER NOT NULL,
                confidence REAL NOT NULL,
                result_file TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                history_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                FOREIGN KEY(history_id) REFERENCES history(id)
            )
        """)


def get_model():
    global model
    if model is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Trained model not found at {MODEL_PATH}. "
                "Place the accident-trained best.pt file in the models folder."
            )
        model = YOLO(str(MODEL_PATH))
    return model


def save_record(media_type, original_name, accident, detections, confidence, result_file):
    now = datetime.now().isoformat(timespec="seconds")
    status = "Accident detected" if accident else "No accident detected"
    with db() as con:
        cur = con.execute(
            """INSERT INTO history
            (created_at, media_type, original_name, status, detections, confidence, result_file)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (now, media_type, original_name, status, detections, confidence, result_file),
        )
        history_id = cur.lastrowid
        if accident:
            con.execute(
                "INSERT INTO alerts (history_id, created_at, message) VALUES (?, ?, ?)",
                (history_id, now, f"Possible accident detected in {original_name}. Review required."),
            )
    return history_id, now, status


@app.get("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/api/stats")
def stats():
    with db() as con:
        total = con.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        accidents = con.execute(
            "SELECT COUNT(*) FROM history WHERE status='Accident detected'"
        ).fetchone()[0]
        pending = con.execute(
            "SELECT COUNT(*) FROM alerts WHERE status='Pending'"
        ).fetchone()[0]
        recent = con.execute(
            "SELECT * FROM history ORDER BY id DESC LIMIT 5"
        ).fetchall()
    return jsonify({
        "total": total,
        "accidents": accidents,
        "safe": total - accidents,
        "pending_alerts": pending,
        "recent": [dict(row) for row in recent],
    })


@app.get("/api/history")
def history():
    with db() as con:
        rows = con.execute("SELECT * FROM history ORDER BY id DESC LIMIT 100").fetchall()
    return jsonify([dict(row) for row in rows])


@app.get("/api/alerts")
def alerts():
    with db() as con:
        rows = con.execute("""
            SELECT alerts.*, history.original_name
            FROM alerts JOIN history ON history.id = alerts.history_id
            ORDER BY alerts.id DESC
        """).fetchall()
    return jsonify([dict(row) for row in rows])


@app.post("/api/alerts/<int:alert_id>/resolve")
def resolve_alert(alert_id):
    with db() as con:
        con.execute("UPDATE alerts SET status='Reviewed' WHERE id=?", (alert_id,))
    return jsonify({"ok": True})


@app.post("/api/detect/image")
def detect_image():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "Choose an image file first."}), 400
    ext = Path(upload.filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        return jsonify({"error": "Supported images: JPG, JPEG, PNG, BMP, WEBP."}), 400

    safe_name = secure_filename(upload.filename)
    token = uuid.uuid4().hex
    input_path = UPLOAD_DIR / f"{token}_{safe_name}"
    output_name = f"{token}_detected.jpg"
    output_path = OUTPUT_DIR / output_name
    upload.save(input_path)

    try:
        yolo = get_model()
        results = yolo.predict(source=str(input_path), conf=0.25, verbose=False)
        result = results[0]
        plotted = result.plot()
        cv2.imwrite(str(output_path), plotted)
        boxes = result.boxes
        count = len(boxes) if boxes is not None else 0
        confidence = float(boxes.conf.max().item()) if count else 0.0
        # This assumes the supplied checkpoint was trained to label accident regions.
        accident = count > 0
        _, created_at, status = save_record(
            "Image", safe_name, accident, count, confidence, output_name
        )
        return jsonify({
            "status": status,
            "accident": accident,
            "detections": count,
            "confidence": round(confidence, 4),
            "created_at": created_at,
            "result_url": f"/outputs/{output_name}",
        })
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        app.logger.exception("Image detection failed")
        return jsonify({"error": f"Detection failed: {exc}"}), 500
    finally:
        input_path.unlink(missing_ok=True)


@app.post("/api/detect/video")
def detect_video():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "Choose a video file first."}), 400
    ext = Path(upload.filename).suffix.lower()
    if ext not in {".mp4", ".avi", ".mov", ".mkv"}:
        return jsonify({"error": "Supported videos: MP4, AVI, MOV, MKV."}), 400

    safe_name = secure_filename(upload.filename)
    token = uuid.uuid4().hex
    input_path = UPLOAD_DIR / f"{token}_{safe_name}"
    output_name = f"{token}_analysed.mp4"
    output_path = OUTPUT_DIR / output_name
    upload.save(input_path)

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        input_path.unlink(missing_ok=True)
        return jsonify({"error": "Could not open this video file."}), 400

    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )

    try:
        yolo = get_model()
        frame_count = 0
        detected_frames = 0
        max_confidence = 0.0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            result = yolo.predict(source=frame, conf=0.25, verbose=False)[0]
            boxes = result.boxes
            count = len(boxes) if boxes is not None else 0
            if count:
                detected_frames += 1
                max_confidence = max(max_confidence, float(boxes.conf.max().item()))
            writer.write(result.plot())
            frame_count += 1
        accident = detected_frames > 0
        _, created_at, status = save_record(
            "Video", safe_name, accident, detected_frames, max_confidence, output_name
        )
        return jsonify({
            "status": status,
            "accident": accident,
            "frames_analysed": frame_count,
            "frames_with_detections": detected_frames,
            "confidence": round(max_confidence, 4),
            "created_at": created_at,
            "result_url": f"/outputs/{output_name}",
        })
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        app.logger.exception("Video detection failed")
        return jsonify({"error": f"Video detection failed: {exc}"}), 500
    finally:
        cap.release()
        writer.release()
        input_path.unlink(missing_ok=True)


@app.get("/outputs/<path:filename>")
def output_file(filename):
    return send_from_directory(OUTPUT_DIR, filename)


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
