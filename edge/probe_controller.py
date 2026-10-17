"""
AgriSentinel - Smart Crop Probe Controller

Coordinates the smart probe stick hardware and software subsystems:
1. Camera video streaming and frame capture
2. AI Pest Detection & Bounding Box Annotation
3. Agricultural Knowledge Base & Pesticide Recommendations
4. Auto-Pause & Confirmation Capture Loop
5. SQLite DBMS persistence & WebSocket alert notifications
"""

import os
import sys
import time
import math
import uuid
import datetime
import logging
import threading
from typing import Dict, Any, Optional, List, Callable
import cv2
import numpy as np

from edge.knowledge_base import knowledge_base
from edge.vision.detector import get_detector, annotate_frame, DetectionBox
from edge.database import insert_detection, get_recent_detections, DETECTIONS_DIR

logger = logging.getLogger("AgriSentinel-ProbeController")

# Configuration via environment variables
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
STREAM_WIDTH = int(os.getenv("STREAM_WIDTH", "640"))
STREAM_HEIGHT = int(os.getenv("STREAM_HEIGHT", "480"))
AUTO_TRIGGER_COOLDOWN_SEC = float(os.getenv("AUTO_TRIGGER_COOLDOWN_SEC", "15.0"))


class ProbeController:
    """Central Controller for the AgriSentinel Smart Crop Probe Stick."""

    def __init__(self, probe_id: str = "PROBE-01"):
        self.probe_id = probe_id
        self.active_crop = "corn"
        self.farm_area = "Plot 1 - North Field"

        # Subsystems
        self.detector = get_detector()

        # Operational state
        self.is_paused = False
        self._pause_lock = threading.Lock()
        self._last_auto_detection_time = 0.0
        self.alert_callbacks: List[Callable[[Dict[str, Any]], None]] = []

        # Latest readings cache
        self.latest_detections: List[DetectionBox] = []
        self.latest_health = "Healthy / Pest-Free"
        self.latest_infestation = "None"
        self.latest_annotated_frame: Optional[np.ndarray] = None

        # Camera Management
        self.cap: Optional[cv2.VideoCapture] = None
        self._camera_lock = threading.Lock()
        self._running = True
        self._camera_thread = threading.Thread(target=self._camera_loop, daemon=True)
        self._camera_thread.start()

        logger.info(f"[ProbeController] Initialized probe {self.probe_id} for crop '{self.active_crop}'.")

    def register_alert_callback(self, cb: Callable[[Dict[str, Any]], None]):
        """Registers a callback for WebSocket alert broadcasting."""
        self.alert_callbacks.append(cb)

    def _broadcast_alert(self, payload: Dict[str, Any]):
        """Dispatches alert to all registered callbacks."""
        for cb in self.alert_callbacks:
            try:
                cb(payload)
            except Exception as e:
                logger.error(f"[ProbeController] Alert callback error: {e}")

    def set_active_crop(self, crop_key: str):
        """Sets the host crop being inspected."""
        crop_clean = crop_key.lower().strip()
        supported = [c["key"] for c in knowledge_base.get_supported_crops()]
        if crop_clean in supported:
            self.active_crop = crop_clean
            logger.info(f"[ProbeController] Active crop changed to: {self.active_crop}")
        else:
            logger.warning(f"[ProbeController] Unsupported crop '{crop_key}', keeping '{self.active_crop}'")

    def set_farm_area(self, area: str):
        """Updates the farm plot or zone designation."""
        self.farm_area = area.strip()
        logger.info(f"[ProbeController] Farm area updated to: {self.farm_area}")

    def _init_camera(self):
        """Initializes OpenCV video capture or synthetic fallback."""
        try:
            # Try DirectShow on Windows or standard V4L2 on Linux
            backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_V4L2
            self.cap = cv2.VideoCapture(CAMERA_INDEX, backend)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(CAMERA_INDEX)

            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, STREAM_WIDTH)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, STREAM_HEIGHT)
                logger.info(f"[ProbeController] Physical camera opened on index {CAMERA_INDEX}.")
            else:
                logger.info("[ProbeController] Physical camera not opened. Using synthetic crop simulation feed.")
                self.cap = None
        except Exception as e:
            logger.warning(f"[ProbeController] Camera open failed: {e}. Falling back to simulation pattern.")
            self.cap = None

    def _generate_synthetic_frame(self) -> np.ndarray:
        """Generates a realistic animated plant canopy background frame."""
        frame = np.zeros((STREAM_HEIGHT, STREAM_WIDTH, 3), dtype=np.uint8)

        # Foliage green gradient background
        for y in range(STREAM_HEIGHT):
            shade = int(35 + (y / STREAM_HEIGHT) * 45)
            frame[y, :] = [20, shade, 15]

        # Draw animated leaf veins and crop canopy elements
        t = time.time()
        center_x = int(STREAM_WIDTH // 2 + math.sin(t * 0.5) * 30)
        center_y = int(STREAM_HEIGHT // 2)

        # Plant stem / leaf shapes
        cv2.ellipse(frame, (center_x - 80, center_y), (140, 70), 35, 0, 360, (25, 120, 35), -1)
        cv2.ellipse(frame, (center_x + 90, center_y + 40), (160, 80), -25, 0, 360, (20, 105, 30), -1)
        cv2.ellipse(frame, (center_x, center_y - 60), (120, 60), 10, 0, 360, (30, 140, 40), -1)

        # Add simulated natural texture
        noise = np.random.randint(-10, 10, (STREAM_HEIGHT, STREAM_WIDTH, 3), dtype=np.int16)
        frame_noisy = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        return frame_noisy

    def _camera_loop(self):
        """Continuous camera frame acquisition and detection stream loop."""
        self._init_camera()

        while self._running:
            if self.is_paused:
                time.sleep(0.05)
                continue

            frame = None
            if self.cap and self.cap.isOpened():
                with self._camera_lock:
                    ret, raw_frame = self.cap.read()
                    if ret and raw_frame is not None:
                        frame = raw_frame

            if frame is None:
                frame = self._generate_synthetic_frame()

            # Run detection inference
            crop_name = knowledge_base.get_crop(self.active_crop).get("name", self.active_crop.capitalize())
            detections = self.detector.detect(frame, self.active_crop)
            self.latest_detections = detections

            # Derive metrics
            pest_count = len(detections)
            infestation = knowledge_base.calculate_infestation_level(
                self.active_crop,
                detections[0].pest_key if detections else "",
                pest_count
            )
            self.latest_infestation = infestation
            self.latest_health = knowledge_base.evaluate_plant_health(
                pest_count,
                infestation
            )

            # Annotate frame
            model_status = "Online" if getattr(self.detector, "is_model_loaded", False) else "Offline (Missing)"
            annotated = annotate_frame(
                frame,
                detections,
                crop_name=crop_name,
                health_status=self.latest_health,
                model_status=model_status
            )

            with self._camera_lock:
                self.latest_annotated_frame = annotated

            # Check Auto-Pause & Confirmation Trigger (only active when model is loaded)
            now = time.time()
            min_conf = getattr(self.detector, "conf_threshold", 0.25)
            is_loaded = getattr(self.detector, "is_model_loaded", False)
            if (
                is_loaded
                and pest_count > 0
                and detections[0].confidence >= min_conf
                and (now - self._last_auto_detection_time) > AUTO_TRIGGER_COOLDOWN_SEC
            ):
                self._trigger_auto_confirmation(frame, detections)

            time.sleep(0.03)

    def _trigger_auto_confirmation(self, raw_frame: np.ndarray, detections: List[DetectionBox]):
        """
        Executes the 2-step Auto-Pause & Re-verification workflow:
        1. Halt frame acquisition for 0.5s to eliminate motion blur.
        2. Capture a fresh still frame from camera.
        3. Re-run inference on still frame.
        4. If verified, save snapshot image, insert DBMS record, and broadcast alert.
        5. Resume preview.
        """
        self._last_auto_detection_time = time.time()
        logger.info("[ProbeController] Pest candidate detected. Executing 2-Step Auto-Pause & Verification...")

        self.is_paused = True
        try:
            # 1. Stabilization pause to eliminate motion blur
            time.sleep(0.5)

            # 2. Capture clean still frame from camera
            still_frame = None
            if self.cap and self.cap.isOpened():
                with self._camera_lock:
                    ret, frame_cap = self.cap.read()
                    if ret and frame_cap is not None:
                        still_frame = frame_cap

            if still_frame is None:
                still_frame = raw_frame

            # 3. Re-verify detection on clean still frame
            verified_pests = self.detector.detect(still_frame, self.active_crop)

            # 4. Save and broadcast if verified
            if verified_pests and len(verified_pests) > 0:
                logger.info(
                    f"[ProbeController] Detections verified on still frame ({len(verified_pests)} found). Logging alert..."
                )
                self._process_and_save_detection(still_frame, verified_pests, trigger_type="AUTO")
            else:
                logger.info(
                    "[ProbeController] Pest not verified on clean still frame (unconfirmed motion blur/candidate). Resuming stream."
                )
        finally:
            self.is_paused = False
            logger.info("[ProbeController] Confirmation complete. Resumed preview stream.")

    def _process_and_save_detection(
        self,
        frame: np.ndarray,
        detections: List[DetectionBox],
        trigger_type: str = "AUTO"
    ) -> Dict[str, Any]:
        """Saves annotated snapshot to disk, inserts into DBMS, and broadcasts alerts."""
        ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        crop_clean = self.active_crop
        crop_data = knowledge_base.get_crop(crop_clean)
        crop_name = crop_data.get("name", crop_clean.capitalize()) if crop_data else crop_clean.capitalize()

        primary_pest = detections[0] if detections else None
        pest_name = primary_pest.pest_key if primary_pest else "none"
        pest_count = len(detections)
        confidence = primary_pest.confidence if primary_pest else 1.0

        # Query recommendation & plant health
        rec = knowledge_base.get_recommendation(
            crop_key=crop_clean,
            pest_name=pest_name,
            confidence=confidence,
            pest_count=pest_count
        )

        # Annotate snapshot
        annotated_snapshot = annotate_frame(
            frame,
            detections,
            crop_name=crop_name,
            health_status=rec["plant_health_status"]
        )

        # Save snapshot file
        filename = f"det_{ts_str}_{crop_clean}_{uuid.uuid4().hex[:6]}.jpg"
        full_path = os.path.join(DETECTIONS_DIR, filename)
        cv2.imwrite(full_path, annotated_snapshot, [cv2.IMWRITE_JPEG_QUALITY, 85])
        rel_path = f"/static/detections/{filename}"

        # Insert to SQLite
        db_payload = {
            "timestamp": datetime.datetime.now().isoformat(),
            "crop_type": crop_clean,
            "farm_area": self.farm_area,
            "detected_pest": rec["detected_pest"],
            "pest_count": pest_count,
            "infestation_level": rec["infestation_level"],
            "soil_moisture_percent": 0.0,
            "soil_status": "N/A",
            "plant_health_status": rec["plant_health_status"],
            "confidence": confidence,
            "recommended_pesticide": rec.get("recommended_pesticide", ""),
            "organic_alternative": rec.get("organic_alternative", ""),
            "dosage_instruction": rec.get("dosage_instruction", ""),
            "safety_precautions": rec.get("safety_precautions", ""),
            "image_path": rel_path,
            "status": rec["status"]
        }
        rec_id = insert_detection(db_payload)
        db_payload["id"] = rec_id

        # Broadcast WebSocket alert
        alert_event = {
            "type": "PEST_DETECTION_ALERT",
            "trigger": trigger_type,
            "record": db_payload,
            "summary": f"{rec['detected_pest']} ({pest_count} detected) in {crop_name} - {rec['infestation_level']} Infestation"
        }
        self._broadcast_alert(alert_event)

        return db_payload

    def analyze_now(
        self,
        crop_type: Optional[str] = None,
        farm_area: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes immediate on-demand manual inspection and recommendation."""
        if crop_type:
            self.set_active_crop(crop_type)
        if farm_area:
            self.set_farm_area(farm_area)

        # Grab current raw frame
        frame = None
        if self.cap and self.cap.isOpened():
            with self._camera_lock:
                ret, raw_frame = self.cap.read()
                if ret and raw_frame is not None:
                    frame = raw_frame

        if frame is None:
            frame = self._generate_synthetic_frame()

        # Run inference
        detections = self.detector.detect(frame, self.active_crop)
        result = self._process_and_save_detection(frame, detections, trigger_type="MANUAL")
        return result

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns consolidated live telemetry payload."""
        crop_data = knowledge_base.get_crop(self.active_crop)
        return {
            "probe_id": self.probe_id,
            "active_crop": self.active_crop,
            "crop_name": crop_data.get("name", self.active_crop.capitalize()) if crop_data else self.active_crop,
            "farm_area": self.farm_area,
            "camera_active": True,
            "is_paused": self.is_paused,
            "latest_pest": self.latest_detections[0].label if self.latest_detections else "Pest-Free",
            "latest_pest_count": len(self.latest_detections),
            "infestation_level": self.latest_infestation,
            "plant_health_status": self.latest_health,
            "model_loaded": getattr(self.detector, "is_model_loaded", False),
            "model_path": getattr(self.detector, "model_path", ""),
            "model_error": getattr(self.detector, "model_error", None),
            "model_runtime": getattr(self.detector, "runtime_name", "None"),
            "class_filter_mode": getattr(self.detector, "class_filter_mode", "full_102"),
            "conf_threshold": getattr(self.detector, "conf_threshold", 0.25),
            "iou_threshold": getattr(self.detector, "iou_threshold", 0.45),
            "timestamp": time.time(),
        }

    def get_jpeg_frame(self) -> bytes:
        """Encodes latest annotated frame into JPEG byte stream."""
        with self._camera_lock:
            if self.latest_annotated_frame is not None:
                frame = self.latest_annotated_frame
            else:
                frame = self._generate_synthetic_frame()

        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ret:
            return buffer.tobytes()
        return b""

    def shutdown(self):
        """Cleans up threads and hardware connections."""
        self._running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()
        logger.info("[ProbeController] Probe shut down cleanly.")


# Global singleton instance
probe = ProbeController()

