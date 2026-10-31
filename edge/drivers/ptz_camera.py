"""
AgriSentinel Edge Driver - FEELWORLD 4K10X 4K PTZ Camera Controller

Governs pan, tilt, optical zoom, preset sweeps, automated canopy patrols,
and resolution negotiation for the FEELWORLD 4K10X 4K PTZ Camera.

Hardware Specifications:
- Sensor: 1/2.8-inch CMOS (8.29 MP)
- Resolution: 4K @ 30fps, 1080p @ 60fps, 720p @ 60fps
- Optical Zoom: 10X Optical Zoom (1.0x to 10.0x)
- Mechanical Pan: ±125°
- Mechanical Tilt: ±30°
- Transports Supported:
  1. USB 3.0 UVC (plug-and-play V4L2 on Linux, DirectShow on Windows)
  2. LAN IP / PoE (RTSP low-latency video stream)
  3. VISCA-over-IP (UDP port 52381 / 1259)
  4. Virtual Viewport Fallback (smooth digital PTZ simulation for offline tests)
"""

import os
import sys
import time
import math
import socket
import logging
import threading
from typing import Dict, Any, Optional, Tuple, List
import cv2
import numpy as np

logger = logging.getLogger("AgriSentinel-PTZCamera")

# Hardware Limits
MODEL_NAME = "FEELWORLD 4K10X 4K PTZ"
MIN_PAN = -125.0
MAX_PAN = 125.0
MIN_TILT = -30.0
MAX_TILT = 30.0
MIN_ZOOM = 1.0
MAX_ZOOM = 10.0

# Resolution Profiles
RESOLUTION_PROFILES = {
    "1080p_adaptive": {
        "id": "1080p_adaptive",
        "name": "Adaptive 1080p Full HD (Recommended)",
        "capture_size": (1920, 1080),
        "preview_size": (640, 360),
        "aspect_ratio": "16:9",
        "description": "Crisp 1080p still captures & verification with low-bandwidth 360p live preview."
    },
    "720p_lightweight": {
        "id": "720p_lightweight",
        "name": "Lightweight 720p HD",
        "capture_size": (1280, 720),
        "preview_size": (640, 360),
        "aspect_ratio": "16:9",
        "description": "Optimized for minimal CPU and memory usage on Raspberry Pi."
    },
    "4k_uhd": {
        "id": "4k_uhd",
        "name": "Ultra HD 4K",
        "capture_size": (3840, 2160),
        "preview_size": (640, 360),
        "aspect_ratio": "16:9",
        "description": "Full 8.29MP sensor capture for extreme macro leaf inspection."
    },
    "480p_legacy": {
        "id": "480p_legacy",
        "name": "Legacy 480p SD",
        "capture_size": (640, 480),
        "preview_size": (640, 480),
        "aspect_ratio": "4:3",
        "description": "Standard 4:3 legacy capture mode."
    }
}

DEFAULT_PRESETS: Dict[int, Dict[str, Any]] = {
    1: {"name": "Center Canopy", "pan": 0.0, "tilt": 0.0, "zoom": 1.0},
    2: {"name": "Left Row", "pan": -45.0, "tilt": -5.0, "zoom": 1.5},
    3: {"name": "Right Row", "pan": 45.0, "tilt": -5.0, "zoom": 1.5},
    4: {"name": "Upper Foliage", "pan": 0.0, "tilt": 15.0, "zoom": 2.5},
}


class PTZCameraDriver:
    """Controller for FEELWORLD 4K10X 4K PTZ Camera."""

    def __init__(
        self,
        connection_mode: str = "usb_uvc",
        resolution_profile: str = "1080p_adaptive",
        camera_index: int = 0,
        rtsp_url: str = "rtsp://192.168.1.88:554/live/av0",
        visca_ip: str = "192.168.1.88",
        visca_port: int = 52381,
    ):
        self._lock = threading.Lock()
        self.model_name = MODEL_NAME
        self.connection_mode = connection_mode.lower()  # "usb_uvc", "ip_rtsp", or "synthetic"
        self.camera_index = camera_index
        self.rtsp_url = rtsp_url
        self.visca_ip = visca_ip
        self.visca_port = visca_port

        # Resolution Profile
        self.profile_key = resolution_profile if resolution_profile in RESOLUTION_PROFILES else "1080p_adaptive"
        self.profile = RESOLUTION_PROFILES[self.profile_key]

        # PTZ State
        self.pan: float = 0.0
        self.tilt: float = 0.0
        self.zoom: float = 1.0
        self.focus_mode: str = "auto"
        self.active_preset_id: Optional[int] = 1

        # Presets (up to 8 slots)
        self.presets: Dict[int, Dict[str, Any]] = dict(DEFAULT_PRESETS)

        # Automation & Patrol
        self.patrol_mode: str = "off"  # "off", "preset_sweep", "continuous_sweep"
        self.patrol_interval_sec: float = 10.0
        self._last_patrol_step_time: float = time.time()
        self._patrol_preset_cycle: List[int] = [1, 2, 3, 4]
        self._patrol_cycle_idx: int = 0
        self._sweep_direction: float = 1.0  # +1 for right, -1 for left
        self.is_patrol_paused: bool = False

        # Smart Auto-Zoom
        self.auto_zoom_on_detect: bool = True
        self._pre_auto_zoom_state: Optional[Dict[str, float]] = None

        # Hardware capabilities detected
        self.is_hardware_ptz_available: bool = False
        self._init_network_socket()

        logger.info(
            f"[PTZCameraDriver] Initialized {self.model_name} in mode '{self.connection_mode}' "
            f"with profile '{self.profile_key}' ({self.profile['capture_size'][0]}x{self.profile['capture_size'][1]})."
        )

    def _init_network_socket(self):
        """Initializes non-blocking UDP socket for VISCA-over-IP communication."""
        self._visca_sock: Optional[socket.socket] = None
        try:
            self._visca_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._visca_sock.settimeout(0.2)
        except Exception as e:
            logger.debug(f"[PTZCameraDriver] UDP socket init error: {e}")

    # ── State Accessors ──────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive status dictionary for REST API and telemetry."""
        with self._lock:
            return {
                "model_name": self.model_name,
                "connection_mode": self.connection_mode,
                "camera_index": self.camera_index,
                "rtsp_url": self.rtsp_url,
                "visca_ip": self.visca_ip,
                "visca_port": self.visca_port,
                "pan": round(self.pan, 1),
                "tilt": round(self.tilt, 1),
                "zoom": round(self.zoom, 1),
                "zoom_display": f"{round(self.zoom, 1)}x",
                "focus_mode": self.focus_mode,
                "active_preset_id": self.active_preset_id,
                "presets": self.presets,
                "patrol_mode": self.patrol_mode,
                "patrol_interval_sec": self.patrol_interval_sec,
                "is_patrol_paused": self.is_patrol_paused,
                "auto_zoom_on_detect": self.auto_zoom_on_detect,
                "resolution_profile": self.profile_key,
                "capture_size": list(self.profile["capture_size"]),
                "preview_size": list(self.profile["preview_size"]),
                "aspect_ratio": self.profile["aspect_ratio"],
                "available_profiles": list(RESOLUTION_PROFILES.values()),
                "limits": {
                    "min_pan": MIN_PAN,
                    "max_pan": MAX_PAN,
                    "min_tilt": MIN_TILT,
                    "max_tilt": MAX_TILT,
                    "min_zoom": MIN_ZOOM,
                    "max_zoom": MAX_ZOOM,
                }
            }

    # ── PTZ Motion Commands ──────────────────────────────────────

    def set_position(
        self,
        pan: Optional[float] = None,
        tilt: Optional[float] = None,
        zoom: Optional[float] = None,
        preset_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Sets absolute Pan, Tilt, and Zoom values within camera physical limits."""
        with self._lock:
            if pan is not None:
                self.pan = float(np.clip(pan, MIN_PAN, MAX_PAN))
            if tilt is not None:
                self.tilt = float(np.clip(tilt, MIN_TILT, MAX_TILT))
            if zoom is not None:
                self.zoom = float(np.clip(zoom, MIN_ZOOM, MAX_ZOOM))
            self.active_preset_id = preset_id

        # Dispatch commands to hardware if applicable
        self._dispatch_hardware_ptz()
        return self.get_status()

    def move_step(
        self,
        action: str,
        step: float = 5.0,
        zoom_step: float = 0.5
    ) -> Dict[str, Any]:
        """
        Executes a relative PTZ adjustment:
        action in {"pan_left", "pan_right", "tilt_up", "tilt_down", "zoom_in", "zoom_out", "home"}
        """
        action = action.lower().strip()
        with self._lock:
            if action == "pan_left":
                self.pan = float(np.clip(self.pan - step, MIN_PAN, MAX_PAN))
                self.active_preset_id = None
            elif action == "pan_right":
                self.pan = float(np.clip(self.pan + step, MIN_PAN, MAX_PAN))
                self.active_preset_id = None
            elif action == "tilt_up":
                self.tilt = float(np.clip(self.tilt + step, MIN_TILT, MAX_TILT))
                self.active_preset_id = None
            elif action == "tilt_down":
                self.tilt = float(np.clip(self.tilt - step, MIN_TILT, MAX_TILT))
                self.active_preset_id = None
            elif action == "zoom_in":
                self.zoom = float(np.clip(self.zoom + zoom_step, MIN_ZOOM, MAX_ZOOM))
                self.active_preset_id = None
            elif action == "zoom_out":
                self.zoom = float(np.clip(self.zoom - zoom_step, MIN_ZOOM, MAX_ZOOM))
                self.active_preset_id = None
            elif action in ("home", "center"):
                self.pan = 0.0
                self.tilt = 0.0
                self.zoom = 1.0
                self.active_preset_id = 1
            else:
                logger.warning(f"[PTZCameraDriver] Unknown move action: {action}")

        self._dispatch_hardware_ptz()
        return self.get_status()

    def home(self) -> Dict[str, Any]:
        """Returns camera to 0° pan, 0° tilt, 1.0x optical zoom."""
        return self.move_step("home")

    # ── Canopy Presets ───────────────────────────────────────────

    def recall_preset(self, preset_id: int) -> Dict[str, Any]:
        """Recalls a saved canopy preset slot."""
        with self._lock:
            preset = self.presets.get(preset_id)
            if not preset:
                logger.warning(f"[PTZCameraDriver] Preset slot {preset_id} not found.")
                return self.get_status()

            target_pan = preset.get("pan", 0.0)
            target_tilt = preset.get("tilt", 0.0)
            target_zoom = preset.get("zoom", 1.0)

        # Apply position
        self.set_position(pan=target_pan, tilt=target_tilt, zoom=target_zoom, preset_id=preset_id)
        # Dispatch VISCA preset recall if network enabled
        self._send_visca_preset_recall(preset_id)
        return self.get_status()

    def save_preset(self, preset_id: int, name: Optional[str] = None) -> Dict[str, Any]:
        """Saves current PTZ coordinates into specified preset slot."""
        if not (1 <= preset_id <= 8):
            raise ValueError("Preset ID must be between 1 and 8.")

        with self._lock:
            preset_name = name or self.presets.get(preset_id, {}).get("name", f"Preset {preset_id}")
            self.presets[preset_id] = {
                "name": preset_name,
                "pan": round(self.pan, 1),
                "tilt": round(self.tilt, 1),
                "zoom": round(self.zoom, 1),
            }
            self.active_preset_id = preset_id

        self._send_visca_preset_save(preset_id)
        logger.info(f"[PTZCameraDriver] Saved Preset {preset_id} ({preset_name}): pan={self.pan}, tilt={self.tilt}, zoom={self.zoom}x")
        return self.get_status()

    # ── Automated Patrol & Smart Auto-Zoom ───────────────────────

    def set_patrol_mode(
        self,
        mode: str,
        interval_sec: Optional[float] = None,
        auto_zoom: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Configures automated canopy scanning patrol and auto-zoom toggle."""
        valid_modes = ("off", "preset_sweep", "continuous_sweep")
        clean_mode = mode.lower().strip()
        if clean_mode not in valid_modes:
            clean_mode = "off"

        with self._lock:
            self.patrol_mode = clean_mode
            if interval_sec is not None and interval_sec >= 2.0:
                self.patrol_interval_sec = float(interval_sec)
            if auto_zoom is not None:
                self.auto_zoom_on_detect = bool(auto_zoom)
            self._last_patrol_step_time = time.time()
            self.is_patrol_paused = False

        logger.info(f"[PTZCameraDriver] Patrol mode set to '{self.patrol_mode}' (interval={self.patrol_interval_sec}s, auto_zoom={self.auto_zoom_on_detect})")
        return self.get_status()

    def pause_patrol(self):
        """Temporarily halts patrol during 2-step pest confirmation."""
        with self._lock:
            self.is_patrol_paused = True

    def resume_patrol(self):
        """Resumes patrol after verification."""
        with self._lock:
            self.is_patrol_paused = False
            self._last_patrol_step_time = time.time()

    def step_patrol(self) -> bool:
        """
        Executes one patrol step if interval has elapsed and patrol is active.
        Called periodically by probe controller camera thread.
        """
        with self._lock:
            if self.patrol_mode == "off" or self.is_patrol_paused:
                return False

            now = time.time()
            if (now - self._last_patrol_step_time) < self.patrol_interval_sec:
                return False

            self._last_patrol_step_time = now
            mode = self.patrol_mode

        if mode == "preset_sweep":
            with self._lock:
                available_ids = sorted(list(self.presets.keys()))
                if not available_ids:
                    return False
                self._patrol_cycle_idx = (self._patrol_cycle_idx + 1) % len(available_ids)
                next_preset_id = available_ids[self._patrol_cycle_idx]
            self.recall_preset(next_preset_id)
            return True

        elif mode == "continuous_sweep":
            with self._lock:
                step_deg = 20.0 * self._sweep_direction
                new_pan = self.pan + step_deg
                if new_pan >= 90.0:
                    new_pan = 90.0
                    self._sweep_direction = -1.0
                elif new_pan <= -90.0:
                    new_pan = -90.0
                    self._sweep_direction = 1.0

            self.set_position(pan=new_pan, tilt=0.0, zoom=1.0)
            return True

        return False

    def trigger_smart_zoom(
        self,
        box: Optional[Any] = None,
        zoom_target: float = 3.5
    ) -> bool:
        """
        Executes Smart Auto-Zoom during 2-Step Pest Verification:
        1. Stores current pre-zoom coordinates.
        2. Adjusts pan/tilt towards detected pest box center if available.
        3. Sets optical zoom to zoom_target for macro inspection.
        """
        with self._lock:
            if not self.auto_zoom_on_detect:
                return False

            self._pre_auto_zoom_state = {
                "pan": self.pan,
                "tilt": self.tilt,
                "zoom": self.zoom,
                "preset_id": self.active_preset_id
            }

            target_pan = self.pan
            target_tilt = self.tilt

            # If bounding box is provided (normalized x1, y1, x2, y2), center camera on it
            if box is not None:
                try:
                    # Bounding box centers in 0.0 - 1.0 range
                    bx = getattr(box, "x1", 0.0) + (getattr(box, "x2", 1.0) - getattr(box, "x1", 0.0)) / 2.0
                    by = getattr(box, "y1", 0.0) + (getattr(box, "y2", 1.0) - getattr(box, "y1", 0.0)) / 2.0
                    # Shift pan/tilt proportionally (FOV is ~67.5° wide)
                    pan_offset = (bx - 0.5) * 45.0
                    tilt_offset = -(by - 0.5) * 20.0
                    target_pan = float(np.clip(self.pan + pan_offset, MIN_PAN, MAX_PAN))
                    target_tilt = float(np.clip(self.tilt + tilt_offset, MIN_TILT, MAX_TILT))
                except Exception as e:
                    logger.debug(f"[PTZCameraDriver] Bounding box offset error: {e}")

            target_zoom = float(np.clip(max(self.zoom, zoom_target), MIN_ZOOM, MAX_ZOOM))

        logger.info(f"[PTZCameraDriver] Smart Auto-Zoom triggered: {self.zoom}x -> {target_zoom}x (pan={target_pan:.1f}, tilt={target_tilt:.1f})")
        self.set_position(pan=target_pan, tilt=target_tilt, zoom=target_zoom)
        return True

    def restore_zoom(self):
        """Restores PTZ state that was saved prior to Smart Auto-Zoom."""
        with self._lock:
            prev = self._pre_auto_zoom_state
            self._pre_auto_zoom_state = None

        if prev:
            logger.info(f"[PTZCameraDriver] Restoring pre-zoom position: pan={prev['pan']}, tilt={prev['tilt']}, zoom={prev['zoom']}x")
            self.set_position(
                pan=prev["pan"],
                tilt=prev["tilt"],
                zoom=prev["zoom"],
                preset_id=prev.get("preset_id")
            )

    # ── Resolution Configuration ────────────────────────────────

    def set_resolution_profile(self, profile_key: str) -> Dict[str, Any]:
        """Switches active resolution profile."""
        if profile_key not in RESOLUTION_PROFILES:
            logger.warning(f"[PTZCameraDriver] Unknown profile '{profile_key}'. Available: {list(RESOLUTION_PROFILES.keys())}")
            return self.get_status()

        with self._lock:
            self.profile_key = profile_key
            self.profile = RESOLUTION_PROFILES[profile_key]

        logger.info(f"[PTZCameraDriver] Switched resolution profile to '{profile_key}' ({self.profile['name']}).")
        return self.get_status()

    def set_connection_config(
        self,
        connection_mode: Optional[str] = None,
        camera_index: Optional[int] = None,
        rtsp_url: Optional[str] = None,
        visca_ip: Optional[str] = None,
        visca_port: Optional[int] = None,
        resolution_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates hardware transport configurations."""
        with self._lock:
            if connection_mode is not None:
                self.connection_mode = connection_mode.lower().strip()
            if camera_index is not None:
                self.camera_index = int(camera_index)
            if rtsp_url is not None:
                self.rtsp_url = rtsp_url.strip()
            if visca_ip is not None:
                self.visca_ip = visca_ip.strip()
            if visca_port is not None:
                self.visca_port = int(visca_port)
            if resolution_profile is not None and resolution_profile in RESOLUTION_PROFILES:
                self.profile_key = resolution_profile
                self.profile = RESOLUTION_PROFILES[resolution_profile]

        logger.info(f"[PTZCameraDriver] Updated connection config: mode={self.connection_mode}, profile={self.profile_key}")
        return self.get_status()

    # ── Virtual Viewport Transform (Synthetic & Digital Fallback) ──

    def apply_virtual_viewport(self, frame: np.ndarray) -> np.ndarray:
        """
        Applies smooth digital pan/tilt/zoom viewport crop and transform.
        Ensures that testing on synthetic feeds or fixed webcams provides full
        visual feedback for PTZ movement, zoom changes, and auto-zoom verifications.
        """
        if frame is None:
            return frame

        h, w = frame.shape[:2]
        with self._lock:
            z = self.zoom
            p = self.pan
            t = self.tilt

        # If neutral at 1.0x with 0 pan and 0 tilt, return original frame
        if abs(z - 1.0) < 0.05 and abs(p) < 0.5 and abs(t) < 0.5:
            return frame

        # Crop width and height based on zoom factor
        crop_w = int(w / z)
        crop_h = int(h / z)

        # Center offsets based on pan (-125° to +125°) and tilt (-30° to +30°)
        # Pan shifts center horizontally, tilt shifts center vertically
        max_x_shift = (w - crop_w) / 2.0
        max_y_shift = (h - crop_h) / 2.0

        shift_x = (p / MAX_PAN) * max_x_shift if MAX_PAN > 0 else 0.0
        shift_y = -(t / MAX_TILT) * max_y_shift if MAX_TILT > 0 else 0.0

        center_x = (w / 2.0) + shift_x
        center_y = (h / 2.0) + shift_y

        x1 = int(np.clip(center_x - crop_w / 2.0, 0, w - crop_w))
        y1 = int(np.clip(center_y - crop_h / 2.0, 0, h - crop_h))
        x2 = x1 + crop_w
        y2 = y1 + crop_h

        cropped = frame[y1:y2, x1:x2]
        # Resize cropped viewport back to standard resolution
        transformed = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
        return transformed

    # ── Hardware VISCA & UVC Protocols ───────────────────────────

    def _dispatch_hardware_ptz(self):
        """Sends commands over VISCA-over-IP or Linux V4L2 UVC controls."""
        if self.connection_mode == "ip_rtsp" or self.visca_ip:
            self._send_visca_absolute_position()
        if self.connection_mode == "usb_uvc" and sys.platform.startswith("linux"):
            self._apply_v4l2_uvc_controls()

    def _send_visca_packet(self, packet: bytes):
        """Sends a binary VISCA command packet via UDP to the camera."""
        if not self._visca_sock or not self.visca_ip:
            return
        try:
            self._visca_sock.sendto(packet, (self.visca_ip, self.visca_port))
        except Exception as e:
            logger.debug(f"[PTZCameraDriver] VISCA send error: {e}")

    def _send_visca_absolute_position(self):
        """Constructs VISCA pan/tilt & zoom command packets."""
        # Pan range conversion: -125..+125 mapped to VISCA coordinates
        pan_raw = int((self.pan / MAX_PAN) * 0x0800) & 0xFFFF
        tilt_raw = int((self.tilt / MAX_TILT) * 0x0400) & 0xFFFF
        zoom_raw = int(((self.zoom - MIN_ZOOM) / (MAX_ZOOM - MIN_ZOOM)) * 0x4000) & 0xFFFF

        # VISCA Absolute Pan/Tilt command: 81 01 06 02 VV WW 0Y 0Y 0Y 0Y 0Z 0Z 0Z 0Z FF
        p_bytes = [
            (pan_raw >> 12) & 0x0F,
            (pan_raw >> 8) & 0x0F,
            (pan_raw >> 4) & 0x0F,
            pan_raw & 0x0F,
        ]
        t_bytes = [
            (tilt_raw >> 12) & 0x0F,
            (tilt_raw >> 8) & 0x0F,
            (tilt_raw >> 4) & 0x0F,
            tilt_raw & 0x0F,
        ]
        packet_pt = bytes([
            0x81, 0x01, 0x06, 0x02,
            0x10, 0x10,  # Speed
            p_bytes[0], p_bytes[1], p_bytes[2], p_bytes[3],
            t_bytes[0], t_bytes[1], t_bytes[2], t_bytes[3],
            0xFF
        ])
        self._send_visca_packet(packet_pt)

        # VISCA Direct Zoom command: 81 01 04 47 0p 0q 0r 0s FF
        z_bytes = [
            (zoom_raw >> 12) & 0x0F,
            (zoom_raw >> 8) & 0x0F,
            (zoom_raw >> 4) & 0x0F,
            zoom_raw & 0x0F,
        ]
        packet_z = bytes([
            0x81, 0x01, 0x04, 0x47,
            z_bytes[0], z_bytes[1], z_bytes[2], z_bytes[3],
            0xFF
        ])
        self._send_visca_packet(packet_z)

    def _send_visca_preset_recall(self, preset_id: int):
        """VISCA Preset Recall: 81 01 04 3F 02 pp FF"""
        preset_byte = (preset_id - 1) & 0xFF
        packet = bytes([0x81, 0x01, 0x04, 0x3F, 0x02, preset_byte, 0xFF])
        self._send_visca_packet(packet)

    def _send_visca_preset_save(self, preset_id: int):
        """VISCA Preset Set: 81 01 04 3F 01 pp FF"""
        preset_byte = (preset_id - 1) & 0xFF
        packet = bytes([0x81, 0x01, 0x04, 0x3F, 0x01, preset_byte, 0xFF])
        self._send_visca_packet(packet)

    def _apply_v4l2_uvc_controls(self):
        """Attempts to set pan/tilt/zoom via v4l2-ctl for USB UVC cameras on Linux."""
        try:
            import subprocess
            dev = f"/dev/video{self.camera_index}"
            # Pan/tilt absolute (if supported by UVC driver)
            pan_int = int(self.pan * 3600)
            tilt_int = int(self.tilt * 3600)
            zoom_int = int(self.zoom)
            subprocess.run(
                ["v4l2-ctl", "-d", dev, "--set-ctrl", f"pan_absolute={pan_int},tilt_absolute={tilt_int},zoom_absolute={zoom_int}"],
                capture_output=True,
                check=False
            )
        except Exception:
            pass


# Global singleton instance for application wide access
ptz_driver = PTZCameraDriver()

