"""
AgriSentinel - Smart Crop Probe Controller

Coordinates the smart probe stick hardware and software subsystems:
1. Camera video streaming and frame capture (FEELWORLD 4K10X PTZ + Adaptive HD)
2. AI Pest Detection & Bounding Box Annotation
3. Agricultural Knowledge Base & Pesticide Recommendations
4. Auto-Pause, Smart Auto-Zoom & Confirmation Capture Loop
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
from edge.drivers.ptz_camera import ptz_driver, PTZCameraDriver, RESOLUTION_PROFILES

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
        self.crop_mode = "auto"
        self.active_crop = "auto"
        self.farm_area = "Plot 1 - North Field"

        # Subsystems
        self.detector = get_detector()
        self.ptz: PTZCameraDriver = ptz_driver

        # Operational state
        self.is_paused = False
        self._pause_lock = threading.Lock()
        self._last_auto_detection_time = 0.0
        self._last_bg_detection_time = 0.0
        self._bg_detection_interval = float(os.getenv("BG_DETECTION_INTERVAL", "0.6"))
        self.alert_callbacks: List[Callable[[Dict[str, Any]], None]] = []

        # Latest readings cache
        self.latest_detections: List[DetectionBox] = []
        self.latest_health = "Healthy / Pest-Free"
        self.latest_infestation = "None"
        self.latest_annotated_frame: Optional[np.ndarray] = None
        self.latest_raw_frame: Optional[np.ndarray] = None

        # Camera Management
        self.cap: Optional[cv2.VideoCapture] = None
        self._camera_lock = threading.Lock()
        self._running = True
        self._camera_thread = threading.Thread(target=self._camera_loop, daemon=True)
        self._camera_thread.start()

        logger.info(
            f"[ProbeController] Initialized probe {self.probe_id} for crop '{self.active_crop}' "
            f"(mode: {self.crop_mode}, camera: {self.ptz.model_name})."
        )

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
        """Sets the host crop being inspected or enables auto-detection."""
        crop_clean = crop_key.lower().strip()
        if crop_clean in ("auto", "auto_detect", "autodetect"):
            self.crop_mode = "auto"
            self.active_crop = "auto"
            logger.info("[ProbeController] Crop mode set to: Auto-Detect (auto)")
            return
        supported = [c["key"] for c in knowledge_base.get_supported_crops()]
        if crop_clean in supported:
            self.crop_mode = "manual"
            self.active_crop = crop_clean
            logger.info(f"[ProbeController] Active crop changed to: {self.active_crop}")
        else:
            logger.warning(f"[ProbeController] Unsupported crop '{crop_key}', keeping '{self.active_crop}'")

    def set_farm_area(self, area: str):
        """Updates the farm plot or zone designation."""
        self.farm_area = area.strip()
        logger.info(f"[ProbeController] Farm area updated to: {self.farm_area}")

    def _init_camera(self):
        """Initializes OpenCV video capture (USB UVC, RTSP stream, or synthetic fallback)."""
        with self._camera_lock:
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None

            cap_w, cap_h = self.ptz.profile["capture_size"]
            mode = self.ptz.connection_mode

            try:
                # 1. IP / RTSP Stream Mode (Ethernet / PoE)
                if mode == "ip_rtsp":
                    logger.info(f"[ProbeController] Connecting to RTSP stream: {self.ptz.rtsp_url}")
                    self.cap = cv2.VideoCapture(self.ptz.rtsp_url, cv2.CAP_FFMPEG)
                    if self.cap and self.cap.isOpened():
                        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        logger.info(f"[ProbeController] RTSP stream connected successfully.")
                        return

                # 2. USB 3.0 UVC Mode (Direct USB connection)
                backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_V4L2
                idx = self.ptz.camera_index
                self.cap = cv2.VideoCapture(idx, backend)
                if not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(idx)

                if self.cap.isOpened():
                    # Request MJPEG FOURCC for high-speed hardware-compressed 1080p/4K transmission
                    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                    self.cap.set(cv2.CAP_PROP_FOURCC, fourcc)
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cap_w)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cap_h)
                    self.cap.set(cv2.CAP_PROP_FPS, 30)

                    actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    logger.info(
                        f"[ProbeController] {self.ptz.model_name} opened on USB index {idx} "
                        f"(requested {cap_w}x{cap_h}, negotiated {actual_w}x{actual_h})."
                    )
                    self.ptz.connection_mode = "usb_uvc"
                else:
                    logger.info(f"[ProbeController] Physical camera not opened on index {idx}. Using synthetic simulation pattern.")
                    self.ptz.connection_mode = "synthetic"
                    self.cap = None

            except Exception as e:
                logger.warning(f"[ProbeController] Camera init error: {e}. Falling back to simulation pattern.")
                self.ptz.connection_mode = "synthetic"
                self.cap = None

    def restart_camera(
        self,
        connection_mode: Optional[str] = None,
        camera_index: Optional[int] = None,
        rtsp_url: Optional[str] = None,
        visca_ip: Optional[str] = None,
        visca_port: Optional[int] = None,
        resolution_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dynamically reconfigures and restarts the camera backend without dropping the server."""
        self.ptz.set_connection_config(
            connection_mode=connection_mode,
            camera_index=camera_index,
            rtsp_url=rtsp_url,
            visca_ip=visca_ip,
            visca_port=visca_port,
            resolution_profile=resolution_profile
        )
        self._init_camera()
        return self.get_telemetry()

    def _generate_synthetic_frame(self) -> np.ndarray:
        """Generates a realistic animated plant canopy background frame matching profile resolution."""
        w, h = self.ptz.profile["capture_size"]
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Foliage green gradient background
        for y in range(0, h, 2):
            shade = int(35 + (y / h) * 45)
            frame[y:y+2, :] = [20, shade, 15]

        # Draw animated leaf veins and crop canopy elements
        t = time.time()
        center_x = int(w // 2 + math.sin(t * 0.5) * (w * 0.05))
        center_y = int(h // 2)

        scale = w / 640.0
        cv2.ellipse(frame, (center_x - int(80*scale), center_y), (int(140*scale), int(70*scale)), 35, 0, 360, (25, 120, 35), -1)
        cv2.ellipse(frame, (center_x + int(90*scale), center_y + int(40*scale)), (int(160*scale), int(80*scale)), -25, 0, 360, (20, 105, 30), -1)
        cv2.ellipse(frame, (center_x, center_y - int(60*scale)), (int(120*scale), int(60*scale)), 10, 0, 360, (30, 140, 40), -1)

        # Natural noise texture
        noise = np.random.randint(-8, 8, (h // 2, w // 2, 3), dtype=np.int16)
        noise_full = cv2.resize(noise, (w, h), interpolation=cv2.INTER_NEAREST)
        frame_noisy = np.clip(frame.astype(np.int16) + noise_full, 0, 255).astype(np.uint8)
        return frame_noisy

    def _camera_loop(self):
        """Continuous camera frame acquisition, PTZ patrol, and detection stream loop."""
        self._init_camera()

        while self._running:
            if self.is_paused:
                time.sleep(0.05)
                continue

            # Execute automated canopy patrol step if scheduled
            try:
                self.ptz.step_patrol()
            except Exception as e:
                logger.debug(f"[ProbeController] Patrol step error: {e}")

            raw_frame = None
            if self.cap and self.cap.isOpened():
                with self._camera_lock:
                    ret, frame_cap = self.cap.read()
                    if ret and frame_cap is not None:
                        raw_frame = frame_cap

            if raw_frame is None:
                raw_frame = self._generate_synthetic_frame()

            # Apply PTZ Virtual Viewport transform (simulates pan/tilt/zoom on synthetic or fixed frames)
            frame = self.ptz.apply_virtual_viewport(raw_frame)
            self.latest_raw_frame = frame

            # Run detection inference periodically (keeps AI responsive while avoiding CPU throttling)
            now = time.time()
            if (now - self._last_bg_detection_time) >= self._bg_detection_interval:
                self._last_bg_detection_time = now
                detections = self.detector.detect(frame, self.active_crop)
                self.latest_detections = detections
            else:
                detections = self.latest_detections

            primary_pest = detections[0] if detections else None
            primary_pest_name = primary_pest.pest_key if primary_pest else ""

            # Auto-infer crop if pest detected and in auto mode or crop mismatch
            display_crop = self.active_crop
            if primary_pest_name and (getattr(self, "crop_mode", "auto") == "auto" or self.active_crop in ("auto", "auto_detect")):
                inferred = knowledge_base.infer_crop_from_pest(primary_pest_name, fallback_crop=self.active_crop)
                if inferred:
                    self.active_crop = inferred
                    display_crop = inferred
            elif display_crop in ("auto", "auto_detect"):
                display_crop = "rice"

            crop_info = knowledge_base.get_crop(display_crop)
            crop_name = crop_info.get("name", display_crop.capitalize()) if crop_info else display_crop.capitalize()

            # Derive metrics
            pest_count = len(detections)
            infestation = knowledge_base.calculate_infestation_level(
                display_crop,
                primary_pest_name,
                pest_count
            )
            self.latest_infestation = infestation
            self.latest_health = knowledge_base.evaluate_plant_health(
                pest_count,
                infestation,
                pest_name=primary_pest_name
            )

            # Annotate frame
            model_status = "Online" if getattr(self.detector, "is_model_loaded", False) else "Offline (Missing)"
            annotated_full = annotate_frame(
                frame,
                detections,
                crop_name=crop_name,
                health_status=self.latest_health,
                model_status=model_status
            )

            # Downscale preview frame for low-latency, bandwidth-efficient web streaming
            preview_w, preview_h = self.ptz.profile["preview_size"]
            if annotated_full.shape[1] != preview_w or annotated_full.shape[0] != preview_h:
                annotated_preview = cv2.resize(annotated_full, (preview_w, preview_h), interpolation=cv2.INTER_LINEAR)
            else:
                annotated_preview = annotated_full

            with self._camera_lock:
                self.latest_annotated_frame = annotated_preview

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
        Executes the 2-step Auto-Pause, Smart Auto-Zoom, & Re-verification workflow:
        1. Halt patrol and preview acquisition to eliminate motion blur.
        2. Optionally perform Smart Auto-Zoom on detected pest target.
        3. Capture a fresh high-resolution still frame.
        4. Re-run inference on still frame.
        5. If verified, save crisp snapshot, insert DBMS record, and broadcast alert.
        6. Restore zoom & resume patrol.
        """
        self._last_auto_detection_time = time.time()
        logger.info("[ProbeController] Pest candidate detected. Executing 2-Step Auto-Pause & Smart Zoom Verification...")

        self.is_paused = True
        self.ptz.pause_patrol()

        zoomed = False
        try:
            # 1. Smart Auto-Zoom to target bounding box for high-detail optical inspection
            if self.ptz.auto_zoom_on_detect and detections:
                zoomed = self.ptz.trigger_smart_zoom(detections[0], zoom_target=3.5)

            # 2. Stabilization pause to allow camera optics / zoom motor to settle
            time.sleep(0.6)

            # 3. Capture clean still frame from camera
            still_frame = None
            if self.cap and self.cap.isOpened():
                with self._camera_lock:
                    ret, frame_cap = self.cap.read()
                    if ret and frame_cap is not None:
                        still_frame = frame_cap

            if still_frame is None:
                still_frame = self._generate_synthetic_frame()

            # Apply PTZ viewport to still frame if needed
            still_frame_transformed = self.ptz.apply_virtual_viewport(still_frame)

            # 4. Re-verify detection on clean high-detail still frame
            verified_pests = self.detector.detect(still_frame_transformed, self.active_crop)

            # 5. Save and broadcast if verified
            if verified_pests and len(verified_pests) > 0:
                logger.info(
                    f"[ProbeController] Detections verified on still frame ({len(verified_pests)} found). Logging alert..."
                )
                self._process_and_save_detection(still_frame_transformed, verified_pests, trigger_type="AUTO")
            else:
                logger.info(
                    "[ProbeController] Pest not verified on clean still frame (unconfirmed motion blur/candidate). Resuming stream."
                )
        finally:
            if zoomed:
                time.sleep(0.2)
                self.ptz.restore_zoom()
            self.ptz.resume_patrol()
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
        is_beneficial = primary_pest.is_beneficial if primary_pest else False
        taxonomy = primary_pest.taxonomy if primary_pest else None

        # Query recommendation & plant health
        rec = knowledge_base.get_recommendation(
            crop_key=crop_clean,
            pest_name=pest_name,
            confidence=confidence,
            pest_count=pest_count,
            is_beneficial=is_beneficial,
            taxonomy=taxonomy
        )

        resolved_crop = rec.get("crop_type", crop_clean)
        if resolved_crop in ("auto", "auto_detect"):
            resolved_crop = "rice"
        crop_data = knowledge_base.get_crop(resolved_crop)
        crop_name = rec.get("crop_name") or (crop_data.get("name", resolved_crop.capitalize()) if crop_data else resolved_crop.capitalize())

        if getattr(self, "crop_mode", "auto") == "auto" or crop_clean in ("auto", "auto_detect"):
            self.active_crop = resolved_crop

        # Annotate full resolution snapshot
        annotated_snapshot = annotate_frame(
            frame,
            detections,
            crop_name=crop_name,
            health_status=rec["plant_health_status"]
        )

        # Save snapshot file
        filename = f"det_{ts_str}_{resolved_crop}_{uuid.uuid4().hex[:6]}.jpg"
        full_path = os.path.join(DETECTIONS_DIR, filename)
        cv2.imwrite(full_path, annotated_snapshot, [cv2.IMWRITE_JPEG_QUALITY, 85])
        rel_path = f"/static/detections/{filename}"

        # Insert to SQLite
        db_payload = {
            "timestamp": datetime.datetime.now().isoformat(),
            "crop_type": resolved_crop,
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
        raw_frame = None
        if self.cap and self.cap.isOpened():
            with self._camera_lock:
                ret, frame_cap = self.cap.read()
                if ret and frame_cap is not None:
                    raw_frame = frame_cap

        if raw_frame is None:
            raw_frame = self._generate_synthetic_frame()

        frame = self.ptz.apply_virtual_viewport(raw_frame)

        # Run inference
        detections = self.detector.detect(frame, self.active_crop)
        result = self._process_and_save_detection(frame, detections, trigger_type="MANUAL")
        return result

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns consolidated live telemetry payload including PTZ status."""
        crop_data = knowledge_base.get_crop(self.active_crop)
        cap_w, cap_h = self.ptz.profile["capture_size"]
        return {
            "probe_id": self.probe_id,
            "crop_mode": getattr(self, "crop_mode", "auto"),
            "active_crop": self.active_crop,
            "crop_name": crop_data.get("name", self.active_crop.capitalize()) if crop_data else self.active_crop,
            "farm_area": self.farm_area,
            "camera_active": True,
            "camera_model": self.ptz.model_name,
            "camera_connection_mode": self.ptz.connection_mode,
            "resolution_profile": self.ptz.profile_key,
            "capture_resolution": f"{cap_w}x{cap_h}",
            "aspect_ratio": self.ptz.profile["aspect_ratio"],
            "ptz": self.ptz.get_status(),
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
