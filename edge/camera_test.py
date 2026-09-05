"""
AgriSentinel - Edge Camera Test Module

This module provides a local FastAPI server streaming live video from:
1. Standard OpenCV VideoCapture (Driverless USB webcam / UVC capture)
2. Synthetic animated test pattern (fallback for headless / simulation environments)

Usage:
    python -m edge.camera_test
    OR
    uvicorn edge.camera_test:app --host 0.0.0.0 --port 8000
"""

import os
import sys
import time
import logging
import threading
from typing import Generator, Optional
from contextlib import asynccontextmanager


import platform
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AgriSentinel-Camera")

# --- Edge Impulse & Buzzer Integration ---
try:
    from edge.drivers.piezo import buzzer
except ImportError:
    buzzer = None
    logger.warning("Buzzer driver not available.")

IS_WINDOWS = platform.system() == 'Windows'
runner = None
labels = []
if not IS_WINDOWS:
    try:
        from edge_impulse_linux.image import ImageImpulseRunner
        model_path = Path(__file__).parent / "models" / "agrisentinel-linux-aarch64-v5-impulse-#1.eim"
        runner = ImageImpulseRunner(str(model_path))
        model_info = runner.init()
        labels = model_info['model_parameters']['labels']
        logger.info(f"Edge Impulse Runner Initialized with labels: {labels}")
    except Exception as e:
        logger.error(f"Failed to initialize Edge Impulse runner: {e}")
        runner = None

# Configuration via environment variables
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
STREAM_FPS = int(os.getenv("STREAM_FPS", "30"))
STREAM_WIDTH = int(os.getenv("STREAM_WIDTH", "1920"))
STREAM_HEIGHT = int(os.getenv("STREAM_HEIGHT", "1080"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "80"))
CAMERA_BACKEND_OVERRIDE = os.getenv("CAMERA_BACKEND", "").lower().strip()  # "opencv", "synthetic"



# Buzzer State
auto_buzz = False
pest_detected = False
manual_buzz = False

# Logs Feature State
LOG_CONFIDENCE_THRESHOLD = 0.5
pest_tracker = {
    "first_seen": 0.0,
    "last_seen": 0.0,
    "logged": False,
    "name": ""
}

def get_log_confidence_threshold():
    global LOG_CONFIDENCE_THRESHOLD
    return LOG_CONFIDENCE_THRESHOLD

def set_log_confidence_threshold(val):
    global LOG_CONFIDENCE_THRESHOLD
    LOG_CONFIDENCE_THRESHOLD = float(val)

latest_detection = {
    "name": "None",
    "confidence": 0.0,
    "action": "Standing by for robot detection telemetry...",
    "signal": "Normal",
    "detected": False,
    "timestamp": 0
}

def buzzer_monitor_loop():
    while True:
        should_buzz = (auto_buzz and pest_detected) or manual_buzz
        if should_buzz:
            if buzzer:
                buzzer.start(duty_cycle=1.0)
            time.sleep(0.025)
            if buzzer:
                buzzer.stop()
            time.sleep(0.025)
        else:
            time.sleep(0.03)

# Start Buzzer Thread
buzzer_thread = threading.Thread(target=buzzer_monitor_loop, daemon=True)
buzzer_thread.start()

class CameraManager:
    """Unified camera manager handling OpenCV and Synthetic modes."""

    def __init__(self, camera_index: int = CAMERA_INDEX):
        self.camera_index = camera_index
        self.active_backend = "uninitialized"  # "rpicam", "opencv", "synthetic"
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.lock = threading.Lock()
        self.frame_count = 0

    def start(self):
        """Selects and starts the optimal camera backend."""
        with self.lock:
            if self.is_running:
                return

            # 1. Check if user forced a specific backend
            if CAMERA_BACKEND_OVERRIDE == "synthetic":
                self.active_backend = "synthetic"
                self.is_running = True
                logger.info("[CameraManager] Backend forced to Synthetic.")
                return

            # 2. Try OpenCV (for USB webcams)
            logger.info(f"[CameraManager] Attempting OpenCV capture on device index {self.camera_index}...")
            if sys.platform.startswith("win"):
                self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(self.camera_index)
            else:
                self.cap = cv2.VideoCapture(self.camera_index)

            if self.cap and self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, STREAM_WIDTH)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, STREAM_HEIGHT)
                self.cap.set(cv2.CAP_PROP_FPS, STREAM_FPS)
                self.active_backend = f"opencv (index {self.camera_index})"
                self.is_running = True
                logger.info(f"[CameraManager] Hardware camera opened via OpenCV index {self.camera_index}.")
                return

            # 3. Fallback to synthetic mode
            self.active_backend = "synthetic"
            self.is_running = True
            logger.warning("[CameraManager] No physical camera found/opened. Falling back to synthetic test pattern.")

    def stop(self):
        """Releases all active camera resources."""
        with self.lock:
            self.is_running = False
            if self.cap is not None:
                if self.cap.isOpened():
                    self.cap.release()
                self.cap = None
            logger.info("[CameraManager] Camera resources successfully stopped.")

    def get_status(self) -> dict:
        """Returns the current camera diagnostic status."""
        width, height, fps = STREAM_WIDTH, STREAM_HEIGHT, STREAM_FPS
        if self.cap and self.cap.isOpened():
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or STREAM_WIDTH
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or STREAM_HEIGHT
            fps = int(self.cap.get(cv2.CAP_PROP_FPS)) or STREAM_FPS

        return {
            "is_running": self.is_running,
            "backend": self.active_backend,
            "is_synthetic": "synthetic" in self.active_backend,
            "camera_index": self.camera_index,
            "resolution": f"{width}x{height}",
            "fps": fps,
            "frames_served": self.frame_count,
        }

    def _generate_synthetic_frame(self, width: int = STREAM_WIDTH, height: int = STREAM_HEIGHT) -> np.ndarray:
        """Generates an animated test card when physical camera is unavailable."""
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:] = (24, 28, 36)

        # Grid lines
        for x in range(0, width, 40):
            cv2.line(img, (x, 0), (x, height), (38, 44, 56), 1)
        for y in range(0, height, 40):
            cv2.line(img, (0, y), (width, y), (38, 44, 56), 1)

        # Crosshair center
        cx, cy = width // 2, height // 2
        cv2.circle(img, (cx, cy), 80, (59, 130, 246), 2)
        cv2.circle(img, (cx, cy), 4, (59, 130, 246), -1)
        cv2.line(img, (cx - 100, cy), (cx + 100, cy), (59, 130, 246), 1)
        cv2.line(img, (cx, cy - 100), (cx, cy + 100), (59, 130, 246), 1)

        # Animated bouncing target
        t = time.time()
        bx = int(cx + (width // 3) * np.sin(t * 1.5))
        by = int(cy + (height // 3) * np.cos(t * 2.0))
        cv2.circle(img, (bx, by), 24, (16, 185, 129), -1)
        cv2.putText(img, "TARGET", (bx - 26, by - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (16, 185, 129), 1, cv2.LINE_AA)

        # Overlay banner
        cv2.rectangle(img, (10, 10), (width - 10, 80), (30, 41, 59), -1)
        cv2.rectangle(img, (10, 10), (width - 10, 80), (100, 116, 139), 1)

        cv2.putText(img, "AGRISENTINEL - CAMERA HARDWARE TEST", (24, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(img, "Mode: SYNTHETIC TEST PATTERN (Physical Camera Not Connected / Simulated)", (24, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (234, 179, 8), 1, cv2.LINE_AA)

        # Timestamp
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S") + f".{int((t % 1) * 1000):03d}"
        cv2.putText(img, f"Timestamp: {ts_str}  |  Frame: {self.frame_count}", (20, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (148, 163, 184), 1, cv2.LINE_AA)

        return img

    def get_jpeg_frame(self) -> Optional[bytes]:
        """Returns the current JPEG frame from the active backend."""
        self.frame_count += 1

# 1. From OpenCV VideoCapture
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret and frame is not None:
                ts_str = time.strftime("%Y-%m-%d %H:%M:%S")
                
                # --- INFERENCE INJECTION ---
                global pest_detected, latest_detection
                current_pest = False
                frame_h, frame_w = frame.shape[:2]
                
                if IS_WINDOWS:
                    # Mock Mode on Windows (simulated detection for testing UI)
                    if int(time.time()) % 5 in [0, 1]:
                        current_pest = True
                        label = "Armyworm"
                        conf = 0.94
                        
                        cx, cy = frame_w // 2, frame_h // 2
                        bw, bh = int(frame_w * 0.28), int(frame_h * 0.28)
                        real_x, real_y = cx - bw // 2, cy - bh // 2
                        
                        # High-contrast amber/gold bounding box with filled header tag
                        cv2.rectangle(frame, (real_x, real_y), (real_x + bw, real_y + bh), (0, 215, 255), 3)
                        tag_text = f"{label}: {conf*100:.0f}%"
                        (tw, th), _ = cv2.getTextSize(tag_text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
                        tag_top = max(0, real_y - th - 10)
                        cv2.rectangle(frame, (real_x, tag_top), (real_x + tw + 12, real_y), (0, 215, 255), -1)
                        cv2.putText(frame, tag_text, (real_x + 6, max(th + 2, real_y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2, cv2.LINE_AA)
                        
                        latest_detection = {
                            "name": label,
                            "confidence": conf,
                            "action": "Immediate treatment recommended (targeted biological control / Bt)",
                            "signal": "High",
                            "detected": True,
                            "timestamp": time.time()
                        }
                else:
                    if runner:
                        try:
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            features, cropped = runner.get_features_from_image(rgb_frame)
                            res = runner.classify(features)
                            
                            crop_h, crop_w = cropped.shape[:2]
                            aspect_model = crop_w / crop_h
                            aspect_frame = frame_w / frame_h

                            if aspect_frame > aspect_model:
                                box_h = frame_h
                                box_w = int(frame_h * aspect_model)
                                offset_x = (frame_w - box_w) // 2
                                offset_y = 0
                            else:
                                box_w = frame_w
                                box_h = int(frame_w / aspect_model)
                                offset_x = 0
                                offset_y = (frame_h - box_h) // 2

                            scale_x = box_w / crop_w
                            scale_y = box_h / crop_h

                            if "bounding_boxes" in res.get("result", {}):
                                for bb in res["result"]["bounding_boxes"]:
                                    conf = bb.get('value', 0.0)
                                    if conf > 0.5:
                                        current_pest = True
                                        label = bb.get('label', 'unknown')
                                        
                                        # Transform coordinates from model crop space to full frame
                                        raw_x = offset_x + bb['x'] * scale_x
                                        raw_y = offset_y + bb['y'] * scale_y
                                        raw_w = bb['width'] * scale_x
                                        raw_h = bb['height'] * scale_y
                                        
                                        # Expand FOMO point centroids to visible targets
                                        min_size = int(min(frame_w, frame_h) * 0.12)
                                        if raw_w < min_size or raw_h < min_size:
                                            cx = int(raw_x + raw_w / 2)
                                            cy = int(raw_y + raw_h / 2)
                                            real_x = max(0, cx - min_size // 2)
                                            real_y = max(0, cy - min_size // 2)
                                            real_w = min(frame_w - real_x, min_size)
                                            real_h = min(frame_h - real_y, min_size)
                                        else:
                                            real_x = max(0, min(frame_w - 1, int(raw_x)))
                                            real_y = max(0, min(frame_h - 1, int(raw_y)))
                                            real_w = max(10, min(frame_w - real_x, int(raw_w)))
                                            real_h = max(10, min(frame_h - real_y, int(raw_h)))

                                        # Draw Bounding Box & High-Contrast Label Tag
                                        cv2.rectangle(frame, (real_x, real_y), (real_x + real_w, real_y + real_h), (0, 215, 255), 3)
                                        tag_text = f"{label}: {conf*100:.0f}%"
                                        (tw, th), _ = cv2.getTextSize(tag_text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
                                        tag_top = max(0, real_y - th - 10)
                                        cv2.rectangle(frame, (real_x, tag_top), (real_x + tw + 12, real_y), (0, 215, 255), -1)
                                        cv2.putText(frame, tag_text, (real_x + 6, max(th + 2, real_y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2, cv2.LINE_AA)

                                        latest_detection = {
                                            "name": label,
                                            "confidence": float(conf),
                                            "action": "Immediate treatment recommended",
                                            "signal": "High",
                                            "detected": True,
                                            "timestamp": time.time()
                                        }
                            elif "classification" in res.get("result", {}):
                                for label, conf in res["result"]["classification"].items():
                                    if conf > 0.5:
                                        current_pest = True
                                        tag_text = f"{label}: {conf*100:.0f}%"
                                        cv2.putText(frame, tag_text, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 215, 255), 2, cv2.LINE_AA)
                                        latest_detection = {
                                            "name": label,
                                            "confidence": float(conf),
                                            "action": "Inspection advised",
                                            "signal": "Medium",
                                            "detected": True,
                                            "timestamp": time.time()
                                        }
                        except Exception as e:
                            logger.error(f"Inference error: {e}")
                
                pest_detected = current_pest
                
                # --- Logs > 1s tracking ---
                global pest_tracker, LOG_CONFIDENCE_THRESHOLD
                now = time.time()
                
                # Determine if we should track this frame
                if current_pest and latest_detection["confidence"] >= LOG_CONFIDENCE_THRESHOLD:
                    if now - pest_tracker["last_seen"] > 2.0 or pest_tracker["name"] != latest_detection["name"]:
                        # Reset tracking if grace period exceeded or pest changed
                        pest_tracker["first_seen"] = now
                        pest_tracker["logged"] = False
                    
                    pest_tracker["last_seen"] = now
                    pest_tracker["name"] = latest_detection["name"]
                    
                    # If seen for > 1 second and not logged yet
                    if now - pest_tracker["first_seen"] >= 1.0 and not pest_tracker["logged"]:
                        pest_tracker["logged"] = True
                        try:
                            from edge.database import get_db_connection
                            from edge.web_app import gps_reader
                            import datetime
                            
                            # 1. Save frame to disk
                            os.makedirs("web/static/logs", exist_ok=True)
                            filename = f"{int(now)}_{pest_tracker['name']}.jpg"
                            img_path = os.path.join("web", "static", "logs", filename)
                            cv2.imwrite(img_path, frame)
                            
                            # 2. Get GPS
                            raw_gps = gps_reader.read_gps_data()
                            is_synth = gps_reader.is_synthetic
                            is_live = bool(raw_gps.get("gps_fix"))
                            lat = raw_gps.get("latitude") if is_live else (6.681023 if is_synth else 0.0)
                            lon = raw_gps.get("longitude") if is_live else (124.689331 if is_synth else 0.0)
                            loc_str = f"{lat:.6f}, {lon:.6f}" if (is_live or is_synth) else "No GPS Fix"
                            
                            # 3. Insert into DB
                            dt = datetime.datetime.now()
                            date_str = dt.strftime("%Y-%m-%d")
                            time_str = dt.strftime("%H:%M:%S")
                            
                            conn = get_db_connection()
                            conn.execute("""
                                INSERT INTO detection_logs (PEST, CONFIDENCE, LOCATION, DATE, TIME, IMAGE_PATH, IS_LIVE_LOCATION)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (pest_tracker["name"], latest_detection["confidence"], loc_str, date_str, time_str, f"logs/{filename}", is_live))
                            conn.commit()
                            conn.close()
                            logger.info(f"Logged detection: {pest_tracker['name']} at {loc_str}")
                        except Exception as e:
                            logger.error(f"Failed to log detection: {e}")
                
                # Draw Timestamp
                cv2.putText(frame, f"AgriSentinel Live | {ts_str}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
                
                ret_enc, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
                if ret_enc:
                    return buffer.tobytes()

        # 2. From Synthetic Generator
        synth_frame = self._generate_synthetic_frame()
        ret_enc, buffer = cv2.imencode(".jpg", synth_frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if ret_enc:
            return buffer.tobytes()

        return None

# Global camera manager instance
camera_manager = CameraManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context to manage camera startup and shutdown."""
    camera_manager.start()
    yield
    camera_manager.stop()



app = FastAPI(
    title="AgriSentinel Camera Test Service",
    description="Local camera stream preview and hardware diagnostic server supporting rpicam and OpenCV",
    version="1.1.0",
    lifespan=lifespan,
)

from edge.web_app import router as web_app_router
app.include_router(web_app_router)
app.mount("/static", StaticFiles(directory="web/static"), name="static")


class AutoBuzzRequest(BaseModel):
    enabled: bool

class ManualBuzzRequest(BaseModel):
    active: Optional[bool] = None

@app.post("/api/buzzer/auto")
def set_auto_buzz(req: AutoBuzzRequest):
    global auto_buzz
    auto_buzz = req.enabled
    return {"auto_buzz": auto_buzz}

@app.post("/api/buzzer/manual")
def manual_buzzer(req: Optional[ManualBuzzRequest] = None):
    global manual_buzz
    if req and req.active is not None:
        manual_buzz = req.active
    else:
        def _pulse():
            global manual_buzz
            manual_buzz = True
            time.sleep(0.2)
            manual_buzz = False
        threading.Thread(target=_pulse, daemon=True).start()
    return {"status": "success", "manual_buzz": manual_buzz}

@app.get("/api/detection/status")
def get_detection_status():
    global latest_detection, pest_detected
    is_recent = (time.time() - latest_detection.get("timestamp", 0)) < 3.0
    return {
        "pest_detected": pest_detected and is_recent,
        "latest": latest_detection if is_recent else {
            "name": "None",
            "confidence": 0.0,
            "action": "Standing by for robot detection telemetry...",
            "signal": "Normal",
            "detected": False,
            "timestamp": 0
        }
    }

def frame_generator() -> Generator[bytes, None, None]:
    """Generates MJPEG multipart stream chunks."""
    target_frame_time = 1.0 / STREAM_FPS
    while True:
        start_time = time.time()
        frame_bytes = camera_manager.get_jpeg_frame()

        if frame_bytes:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame_bytes)).encode() + b"\r\n\r\n" +
                frame_bytes +
                b"\r\n"
            )

        elapsed = time.time() - start_time
        sleep_time = max(0.001, target_frame_time - elapsed)
        time.sleep(sleep_time)


@app.get("/video_feed")
def video_feed():
    """Video streaming route yielding multipart MJPEG stream."""
    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/camera/status")
def get_camera_status():
    """Returns camera diagnostic status as JSON."""
    return camera_manager.get_status()


@app.get("/api/camera/snapshot")
def get_snapshot():
    """Returns a single JPEG image snapshot."""
    frame_bytes = camera_manager.get_jpeg_frame()
    if frame_bytes is None:
        return Response(status_code=500, content="Failed to capture snapshot")
    return Response(content=frame_bytes, media_type="image/jpeg")


@app.get("/camera_diagnostic", response_class=HTMLResponse)
def index_page():
    """Serves the test interface HTML page with live video preview and diagnostics."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgriSentinel - Camera Hardware Test</title>
    <style>
        :root {
            --bg-main: #0f172a;
            --bg-card: #1e293b;
            --border: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-green: #10b981;
            --accent-blue: #3b82f6;
            --accent-yellow: #f59e0b;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        body {
            background-color: var(--bg-main);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 24px 16px;
        }

        .header {
            max-width: 900px;
            width: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }

        .title-group h1 {
            font-size: 1.5rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .badge {
            font-size: 0.75rem;
            padding: 4px 8px;
            border-radius: 9999px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .badge-live {
            background-color: rgba(16, 185, 129, 0.2);
            color: var(--accent-green);
            border: 1px solid var(--accent-green);
        }

        .title-group p {
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin-top: 4px;
        }

        .main-container {
            max-width: 900px;
            width: 100%;
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
        }

        @media (min-width: 768px) {
            .main-container {
                grid-template-columns: 2fr 1fr;
            }
        }

        .card {
            background-color: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4);
        }

        .card-header {
            padding: 14px 18px;
            background-color: rgba(15, 23, 42, 0.5);
            border-bottom: 1px solid var(--border);
            font-size: 0.95rem;
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .video-wrapper {
            position: relative;
            width: 100%;
            background-color: #000;
            aspect-ratio: 4/3;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .video-stream {
            width: 100%;
            height: 100%;
            object-fit: contain;
            display: block;
        }

        .stats-panel {
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .stat-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 12px;
            background-color: rgba(15, 23, 42, 0.4);
            border-radius: 8px;
            border: 1px solid rgba(51, 65, 85, 0.6);
        }

        .stat-label {
            font-size: 0.825rem;
            color: var(--text-secondary);
        }

        .stat-value {
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--text-primary);
        }

        .controls {
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .btn {
            background-color: var(--accent-blue);
            color: white;
            border: none;
            padding: 10px 16px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.875rem;
            cursor: pointer;
            transition: opacity 0.2s;
            text-align: center;
            text-decoration: none;
        }

        .btn:hover {
            opacity: 0.9;
        }

        .btn-secondary {
            background-color: var(--border);
            color: var(--text-primary);
        }

        .footer {
            margin-top: 30px;
            text-align: center;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="title-group">
            <h1>AgriSentinel Vision <span class="badge badge-live">Live Stream</span></h1>
            <p>Hardware Vision Capture & Diagnostics (USB Webcam / OpenCV)</p>
        </div>
    </div>

    <div class="main-container">
        <!-- Video Stream Card -->
        <div class="card">
            <div class="card-header">
                <span>Camera Feed (/video_feed)</span>
                <span id="fps-badge" style="color: var(--accent-green); font-size: 0.85rem;">● Streaming</span>
            </div>
            <div class="video-wrapper">
                <img id="stream-img" class="video-stream" src="/video_feed" alt="Live Camera Feed" />
            </div>
        </div>

        <!-- Diagnostics & Info Card -->
        <div class="card">
            <div class="card-header">
                <span>Hardware Diagnostics</span>
            </div>
            <div class="stats-panel">
                <div class="stat-item">
                    <span class="stat-label">Active Backend:</span>
                    <span id="stat-backend" class="stat-value">Detecting...</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Resolution:</span>
                    <span id="stat-resolution" class="stat-value">640x480</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Target FPS:</span>
                    <span id="stat-fps" class="stat-value">30</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Frames Served:</span>
                    <span id="stat-frames" class="stat-value">0</span>
                </div>
            </div>

            <div class="controls">
                <button class="btn btn-secondary" onclick="reloadStream()">Refresh Stream</button>
                <a class="btn" href="/api/camera/snapshot" target="_blank">Capture Snapshot</a>
            </div>
        </div>
    
        <!-- Inference Controls Card -->
        <div class="card">
            <div class="card-header">
                <span>Inference & Buzzer Controls</span>
            </div>
            <div class="controls">
                <label style="display: flex; align-items: center; gap: 8px; font-weight: 600; cursor: pointer;">
                    <input type="checkbox" id="auto-buzz-check" onchange="toggleAutoBuzz(this.checked)" style="width: 18px; height: 18px;">
                    Auto-Buzz on Detection
                </label>
                <button class="btn btn-secondary" onclick="triggerManualBuzzer()">Trigger Manual Buzzer (or press 'B')</button>
            </div>
        </div>
    </div>

    <div class="footer">
        AgriSentinel Autonomous Crop Protection Robot • Camera Subsystem
    </div>

    <script>
        function reloadStream() {
            const img = document.getElementById('stream-img');
            img.src = '/video_feed?t=' + new Date().getTime();
        }

        async function updateDiagnostics() {
            try {
                const res = await fetch('/api/camera/status');
                if (res.ok) {
                    const data = await res.json();
                    document.getElementById('stat-backend').textContent = data.backend;
                    document.getElementById('stat-backend').style.color = data.is_synthetic ? 'var(--accent-yellow)' : 'var(--accent-green)';
                    document.getElementById('stat-resolution').textContent = data.resolution;
                    document.getElementById('stat-fps').textContent = data.fps;
                    document.getElementById('stat-frames').textContent = data.frames_served;
                }
            } catch (e) {
                console.error("Failed to fetch diagnostics", e);
            }
        }

        
        let isBuzzerHeld = false;

        async function toggleAutoBuzz(enabled) {
            await fetch('/api/buzzer/auto', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: enabled })
            });
        }
        
        async function setManualBuzzer(active) {
            try {
                await fetch('/api/buzzer/manual', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ active: active })
                });
            } catch(e) {
                console.error("Buzzer request failed", e);
            }
        }

        document.addEventListener('keydown', (e) => {
            if (e.key.toLowerCase() === 'b' && !e.repeat && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
                isBuzzerHeld = true;
                setManualBuzzer(true);
            }
        });

        document.addEventListener('keyup', (e) => {
            if (e.key.toLowerCase() === 'b' && isBuzzerHeld) {
                isBuzzerHeld = false;
                setManualBuzzer(false);
            }
        });

        window.addEventListener('blur', () => {
            if (isBuzzerHeld) {
                isBuzzerHeld = false;
                setManualBuzzer(false);
            }
        });

        setInterval(updateDiagnostics, 1000);
        updateDiagnostics();
    </script>
</body>
</html>
"""


def main():
    """CLI Entry point for direct execution."""
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    print(f"\n==================================================")
    print(f" AgriSentinel Camera Test Server Starting")
    print(f" Local Web Interface: http://localhost:{port}")
    print(f" Network Web Interface: http://{host}:{port}")
    print(f" Video Stream Endpoint: http://localhost:{port}/video_feed")
    print(f"==================================================\n")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
