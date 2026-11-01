"""
AgriSentinel - Smart Crop Probe Controller

Coordinates the smart probe stick hardware and software subsystems:
1. High-Speed 30-FPS Camera Stream (FEELWORLD 4K10X PTZ + Adaptive HD)
2. Decoupled Asynchronous AI Pest Detection Loop with Live Toggle
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
DEFAULT_LIVE_AI = os.getenv("LIVE_AI_ENABLED", "0").lower() in ("1", "true", "yes", "on")


def generate_cropped_pest_snapshot(raw_frame: np.ndarray, detections: List[DetectionBox]) -> np.ndarray:
    """
    Generates a macro close-up inspection image from the frame.
    - 1 pest: tightly cropped region with 20% padding and bottom label badge.
    - 2-4 pests: multi-panel macro comparison grid of detected pests.
    - Pest-free: center 50% foliage macro inspection.
    """
    h, w = raw_frame.shape[:2]
    target_size = (480, 480)

    if not detections:
        # Center foliage macro crop
        cx, cy = w // 2, h // 2
        half_w, half_h = max(20, w // 4), max(20, h // 4)
        x1, y1 = max(0, cx - half_w), max(0, cy - half_h)
        x2, y2 = min(w, cx + half_w), min(h, cy + half_h)
        crop = raw_frame[y1:y2, x1:x2]
        crop_resized = cv2.resize(crop, target_size, interpolation=cv2.INTER_LINEAR)

        # Bottom caption bar
        bar_h = 38
        cv2.rectangle(crop_resized, (0, target_size[1] - bar_h), (target_size[0], target_size[1]), (20, 20, 20), -1)
        cv2.putText(
            crop_resized,
            "[FOLIAGE CLOSE-UP] Healthy / Pest-Free",
            (12, target_size[1] - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (50, 205, 50),
            1,
            cv2.LINE_AA
        )
        return crop_resized

    def _crop_and_badge(det: DetectionBox, out_w: int, out_h: int) -> np.ndarray:
        pad_x = max(10, int(det.width * 0.20))
        pad_y = max(10, int(det.height * 0.20))
        x1 = max(0, det.x - pad_x)
        y1 = max(0, det.y - pad_y)
        x2 = min(w, det.x + det.width + pad_x)
        y2 = min(h, det.y + det.height + pad_y)

        if x2 <= x1 or y2 <= y1:
            sub = raw_frame[0:min(100, h), 0:min(100, w)]
        else:
            sub = raw_frame[y1:y2, x1:x2]

        resized = cv2.resize(sub, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        bar_h = 32 if out_h >= 240 else 24
        cv2.rectangle(resized, (0, out_h - bar_h), (out_w, out_h), (20, 20, 20), -1)

        tag_color = (50, 205, 50) if det.is_beneficial else (0, 165, 255)
        tag_text = f"{det.label} ({int(det.confidence * 100)}%)"
        cv2.putText(
            resized,
            tag_text,
            (6, out_h - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42 if out_w <= 240 else 0.50,
            tag_color,
            1,
            cv2.LINE_AA
        )
        return resized

    if len(detections) == 1:
        return _crop_and_badge(detections[0], 480, 480)
    elif len(detections) == 2:
        p1 = _crop_and_badge(detections[0], 240, 480)
        p2 = _crop_and_badge(detections[1], 240, 480)
        return np.hstack([p1, p2])
    else:
        top_dets = detections[:4]
        panels = [_crop_and_badge(d, 240, 240) for d in top_dets]
        while len(panels) < 4:
            panels.append(np.zeros((240, 240, 3), dtype=np.uint8))
        row1 = np.hstack([panels[0], panels[1]])
        row2 = np.hstack([panels[2], panels[3]])
        return np.vstack([row1, row2])


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
        self._bg_detection_interval = float(os.getenv("BG_DETECTION_INTERVAL", "0.5"))
        self.alert_callbacks: List[Callable[[Dict[str, Any]], None]] = []

        # Live AI Inference Toggle (Default OFF for buttery smooth 30 FPS stream on Raspberry Pi)
        self.live_ai_enabled: bool = DEFAULT_LIVE_AI

        # Latest readings cache
        self.latest_detections: List[DetectionBox] = []
        self.latest_recommendations: List[Dict[str, Any]] = []
        self.latest_health = "Healthy / Pest-Free"
        self.latest_infestation = "None"
        self.latest_annotated_frame: Optional[np.ndarray] = None
        self.latest_raw_frame: Optional[np.ndarray] = None
        self.latest_jpeg_bytes: bytes = b""

        # Camera Management
        self.cap: Optional[cv2.VideoCapture] = None
        self._camera_lock = threading.Lock()
        self._running = True

        # Thread 1: High-Speed Camera Acquisition & Web Stream Thread
        self._camera_thread = threading.Thread(target=self._camera_loop, daemon=True)
        self._camera_thread.start()

        # Thread 2: Decoupled Background AI Inference Worker Thread
        self._inference_thread = threading.Thread(target=self._inference_loop, daemon=True)
        self._inference_thread.start()

        logger.info(
            f"[ProbeController] Initialized probe {self.probe_id} for crop '{self.active_crop}' "
            f"(mode: {self.crop_mode}, camera: {self.ptz.model_name}, live_ai: {self.live_ai_enabled})."
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

    def set_live_ai_enabled(self, enabled: bool):
        """Toggles continuous background AI pest detection on or off."""
        self.live_ai_enabled = bool(enabled)
        if not self.live_ai_enabled:
            with self._camera_lock:
                self.latest_detections = []
            self.latest_infestation = "None"
            self.latest_health = "Monitoring (Live AI Paused - Manual Ready)"
            logger.info("[ProbeController] Live AI Detection: DISABLED (0% CPU background load, smooth 30 FPS streaming).")
        else:
            logger.info("[ProbeController] Live AI Detection: ENABLED.")

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
                        self.ptz.bind_capture(self.cap, camera_lock=self._camera_lock)
                        return

                # 2. USB 3.0 UVC Mode (Direct USB connection to Raspberry Pi)
                backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_V4L2
                preferred_idx = self.ptz.camera_index

                # Search candidate camera indices on Linux if requested index fails
                candidates = [preferred_idx] if os.name == "nt" else [preferred_idx, 0, 1, 2]
                opened_cap = None
                opened_idx = preferred_idx

                for idx in dict.fromkeys(candidates):
                    cap_test = cv2.VideoCapture(idx, backend)
                    if not cap_test.isOpened():
                        cap_test = cv2.VideoCapture(idx)
                    if cap_test and cap_test.isOpened():
                        opened_cap = cap_test
                        opened_idx = idx
                        break

                if opened_cap and opened_cap.isOpened():
                    self.cap = opened_cap
                    self.ptz.camera_index = opened_idx

                    # Critical V4L2 configuration on Linux:
                    # Set buffer size = 1 to prevent queue lag
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                    # Request compressed MJPEG FOURCC before and after setting dimensions
                    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                    self.cap.set(cv2.CAP_PROP_FOURCC, fourcc)
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cap_w)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cap_h)
                    self.cap.set(cv2.CAP_PROP_FOURCC, fourcc)
                    self.cap.set(cv2.CAP_PROP_FPS, 30)

                    actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    logger.info(
                        f"[ProbeController] {self.ptz.model_name} opened on USB index {opened_idx} "
                        f"(requested {cap_w}x{cap_h}, negotiated {actual_w}x{actual_h})."
                    )
                    self.ptz.connection_mode = "usb_uvc"
                    self.ptz.bind_capture(self.cap, opened_idx, camera_lock=self._camera_lock)
                else:
                    logger.info(f"[ProbeController] Physical camera not opened on index {preferred_idx}. Using synthetic simulation pattern.")
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

    # ── Thread 1: High-Speed Acquisition & Streaming Loop ──────────

    def _camera_loop(self):
        """Continuous camera frame acquisition and streaming loop (runs at 25-30 FPS without AI blocking)."""
        self._init_camera()

        while self._running:
            if self.is_paused:
                time.sleep(0.04)
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

            # Apply PTZ Viewport transform (responsive pan/tilt/zoom)
            frame = self.ptz.apply_virtual_viewport(raw_frame)
            self.latest_raw_frame = frame

            # Active crop metadata
            display_crop = self.active_crop if self.active_crop not in ("auto", "auto_detect") else "rice"
            crop_info = knowledge_base.get_crop(display_crop)
            crop_name = crop_info.get("name", display_crop.capitalize()) if crop_info else display_crop.capitalize()

            # Bounding box overlays: only show if Live AI is active
            detections_to_draw = self.latest_detections if self.live_ai_enabled else []
            model_status = "Live AI" if self.live_ai_enabled else "Manual Capture Ready"

            annotated_full = annotate_frame(
                frame,
                detections_to_draw,
                crop_name=crop_name,
                health_status=self.latest_health,
                model_status=model_status
            )

            # Downscale preview frame for low-latency web streaming
            preview_w, preview_h = self.ptz.profile["preview_size"]
            if annotated_full.shape[1] != preview_w or annotated_full.shape[0] != preview_h:
                annotated_preview = cv2.resize(annotated_full, (preview_w, preview_h), interpolation=cv2.INTER_LINEAR)
            else:
                annotated_preview = annotated_full

            # Pre-encode JPEG once per frame so HTTP streaming clients do not choke CPU
            ret, buffer = cv2.imencode(".jpg", annotated_preview, [cv2.IMWRITE_JPEG_QUALITY, 75])
            with self._camera_lock:
                self.latest_annotated_frame = annotated_preview
                if ret:
                    self.latest_jpeg_bytes = buffer.tobytes()

            time.sleep(0.02)

    # ── Thread 2: Decoupled Background AI Inference Worker ─────────

    def _inference_loop(self):
        """Dedicated background thread for AI inference (prevents freezing the video stream)."""
        while self._running:
            if self.is_paused or not self.live_ai_enabled:
                time.sleep(0.15)
                continue

            frame_copy = None
            if self.latest_raw_frame is not None:
                with self._camera_lock:
                    frame_copy = self.latest_raw_frame.copy()

            if frame_copy is None:
                time.sleep(0.05)
                continue

            try:
                # Run AI detection on the copied frame
                detections = self.detector.detect(frame_copy, self.active_crop)
                self.latest_detections = detections

                primary_pest = detections[0] if detections else None
                primary_pest_name = primary_pest.pest_key if primary_pest else ""

                # Auto-infer crop if pest detected and in auto mode
                display_crop = self.active_crop
                if primary_pest_name and (self.crop_mode == "auto" or self.active_crop in ("auto", "auto_detect")):
                    inferred = knowledge_base.infer_crop_from_pest(primary_pest_name, fallback_crop=self.active_crop)
                    if inferred:
                        self.active_crop = inferred
                        display_crop = inferred
                elif display_crop in ("auto", "auto_detect"):
                    display_crop = "rice"

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
                self.latest_recommendations = self._build_multi_pest_recommendations(detections, display_crop)

                # Check Auto-Pause & Confirmation Trigger
                now = time.time()
                min_conf = getattr(self.detector, "conf_threshold", 0.25)
                is_loaded = getattr(self.detector, "is_model_loaded", False)
                if (
                    is_loaded
                    and pest_count > 0
                    and detections[0].confidence >= min_conf
                    and (now - self._last_auto_detection_time) > AUTO_TRIGGER_COOLDOWN_SEC
                ):
                    self._trigger_auto_confirmation(frame_copy, detections)

            except Exception as e:
                logger.error(f"[ProbeController] Background inference error: {e}")

            time.sleep(self._bg_detection_interval)

    def _trigger_auto_confirmation(self, raw_frame: np.ndarray, detections: List[DetectionBox]):
        """Executes the 2-step Auto-Pause, Smart Auto-Zoom, & Re-verification workflow."""
        self._last_auto_detection_time = time.time()
        logger.info("[ProbeController] Pest candidate detected. Executing 2-Step Auto-Pause & Smart Zoom Verification...")

        self.is_paused = True
        self.ptz.pause_patrol()

        zoomed = False
        try:
            if self.ptz.auto_zoom_on_detect and detections:
                zoomed = self.ptz.trigger_smart_zoom(detections[0], zoom_target=3.5)

            time.sleep(0.5)

            still_frame = None
            if self.cap and self.cap.isOpened():
                with self._camera_lock:
                    ret, frame_cap = self.cap.read()
                    if ret and frame_cap is not None:
                        still_frame = frame_cap

            if still_frame is None:
                still_frame = self._generate_synthetic_frame()

            still_frame_transformed = self.ptz.apply_virtual_viewport(still_frame)
            verified_pests = self.detector.detect(still_frame_transformed, self.active_crop)

            if verified_pests and len(verified_pests) > 0:
                logger.info(
                    f"[ProbeController] Detections verified on still frame ({len(verified_pests)} found). Logging alert..."
                )
                self._process_and_save_detection(still_frame_transformed, verified_pests, trigger_type="AUTO")
            else:
                logger.info("[ProbeController] Pest not verified on still frame. Resuming preview.")
        finally:
            if zoomed:
                time.sleep(0.15)
                self.ptz.restore_zoom()
            self.ptz.resume_patrol()
            self.is_paused = False

    def _build_multi_pest_recommendations(
        self,
        detections: List[DetectionBox],
        crop_key: str
    ) -> List[Dict[str, Any]]:
        """
        Groups detections by unique pest species and retrieves tailored agronomic recommendations
        for each detected species.
        """
        clean_crop = crop_key if crop_key not in ("auto", "auto_detect") else "rice"
        if not detections:
            rec = knowledge_base.get_recommendation(
                crop_key=clean_crop,
                pest_name="none",
                confidence=1.0,
                pest_count=0
            )
            rec["pest_count_for_species"] = 0
            rec["max_confidence"] = 1.0
            return [rec]

        groups: Dict[str, Dict[str, Any]] = {}
        for det in detections:
            pkey = det.pest_key or det.label.lower().replace(" ", "_")
            if pkey not in groups:
                groups[pkey] = {
                    "count": 0,
                    "max_conf": 0.0,
                    "sample": det
                }
            groups[pkey]["count"] += 1
            if det.confidence > groups[pkey]["max_conf"]:
                groups[pkey]["max_conf"] = det.confidence

        recs = []
        for pkey, grp in groups.items():
            sample_det = grp["sample"]
            r = knowledge_base.get_recommendation(
                crop_key=clean_crop,
                pest_name=pkey,
                confidence=grp["max_conf"],
                pest_count=grp["count"],
                is_beneficial=sample_det.is_beneficial,
                taxonomy=sample_det.taxonomy
            )
            r["pest_count_for_species"] = grp["count"]
            r["max_confidence"] = round(float(grp["max_conf"]), 4)
            r["detected_label"] = sample_det.label
            recs.append(r)

        return recs

    def _process_and_save_detection(
        self,
        frame: np.ndarray,
        detections: List[DetectionBox],
        trigger_type: str = "AUTO"
    ) -> Dict[str, Any]:
        """Saves annotated snapshot (uncropped) and close-up (cropped) to disk, inserts into DBMS, and broadcasts alerts."""
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

        if self.crop_mode == "auto" or crop_clean in ("auto", "auto_detect"):
            self.active_crop = resolved_crop

        # Build multi-pest recommendations
        multi_recs = self._build_multi_pest_recommendations(detections, resolved_crop)
        self.latest_recommendations = multi_recs

        # Format composite detected_pest name
        if not detections:
            detected_pest_str = "Pest-Free"
        elif len(multi_recs) == 1:
            detected_pest_str = multi_recs[0].get("detected_pest", primary_pest.label)
        else:
            detected_pest_str = ", ".join([
                f"{r.get('detected_pest', 'Pest')} ({r.get('pest_count_for_species', 1)})"
                for r in multi_recs
            ])

        # 1. Uncropped annotated full scene
        annotated_snapshot = annotate_frame(
            frame,
            detections,
            crop_name=crop_name,
            health_status=rec["plant_health_status"]
        )

        uid = uuid.uuid4().hex[:6]
        full_filename = f"det_{ts_str}_{resolved_crop}_{uid}_full.jpg"
        crop_filename = f"det_{ts_str}_{resolved_crop}_{uid}_crop.jpg"

        full_disk_path = os.path.join(DETECTIONS_DIR, full_filename)
        crop_disk_path = os.path.join(DETECTIONS_DIR, crop_filename)

        cv2.imwrite(full_disk_path, annotated_snapshot, [cv2.IMWRITE_JPEG_QUALITY, 85])
        rel_full_path = f"/static/detections/{full_filename}"

        # 2. Cropped pest close-up macro
        cropped_macro = generate_cropped_pest_snapshot(frame, detections)
        cv2.imwrite(crop_disk_path, cropped_macro, [cv2.IMWRITE_JPEG_QUALITY, 90])
        rel_crop_path = f"/static/detections/{crop_filename}"

        db_payload = {
            "timestamp": datetime.datetime.now().isoformat(),
            "crop_type": resolved_crop,
            "farm_area": self.farm_area,
            "detected_pest": detected_pest_str,
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
            "image_path": rel_full_path,
            "crop_image_path": rel_crop_path,
            "status": rec["status"],
            "recommendations": multi_recs
        }
        rec_id = insert_detection(db_payload)
        db_payload["id"] = rec_id

        alert_event = {
            "type": "PEST_DETECTION_ALERT",
            "trigger": trigger_type,
            "record": db_payload,
            "summary": f"{detected_pest_str} in {crop_name} - {rec['infestation_level']} Infestation",
            "recommendations": multi_recs
        }
        self._broadcast_alert(alert_event)

        return db_payload

    def analyze_now(
        self,
        crop_type: Optional[str] = None,
        farm_area: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes immediate on-demand manual inspection and recommendation (always active)."""
        if crop_type:
            self.set_active_crop(crop_type)
        if farm_area:
            self.set_farm_area(farm_area)

        raw_frame = None
        if self.cap and self.cap.isOpened():
            with self._camera_lock:
                ret, frame_cap = self.cap.read()
                if ret and frame_cap is not None:
                    raw_frame = frame_cap

        if raw_frame is None:
            raw_frame = self._generate_synthetic_frame()

        frame = self.ptz.apply_virtual_viewport(raw_frame)

        # Always runs full inference on on-demand request
        detections = self.detector.detect(frame, self.active_crop)
        result = self._process_and_save_detection(frame, detections, trigger_type="MANUAL")
        return result

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns consolidated live telemetry payload including PTZ and Live AI state."""
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
            "live_ai_enabled": self.live_ai_enabled,
            "ptz": self.ptz.get_status(),
            "is_paused": self.is_paused,
            "latest_pest": self.latest_detections[0].label if self.latest_detections else ("Pest-Free" if self.live_ai_enabled else "Ready (Manual)"),
            "latest_pest_count": len(self.latest_detections),
            "infestation_level": self.latest_infestation,
            "plant_health_status": self.latest_health,
            "recommendations": getattr(self, "latest_recommendations", []),
            "box_thickness": getattr(self.detector, "box_thickness", 2),
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
        """Returns the pre-encoded latest JPEG byte stream (instant O(1) response)."""
        with self._camera_lock:
            if self.latest_jpeg_bytes:
                return self.latest_jpeg_bytes

        # Fallback if first frame not yet encoded
        frame = self._generate_synthetic_frame()
        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return buffer.tobytes() if ret else b""

    def shutdown(self):
        """Cleans up threads and hardware connections."""
        self._running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()
        logger.info("[ProbeController] Probe shut down cleanly.")


# Global singleton instance
probe = ProbeController()
