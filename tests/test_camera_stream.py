"""
Unit and integration tests for edge.camera_test module.
"""

import os
# Force synthetic camera for deterministic test environment
os.environ["CAMERA_BACKEND"] = "synthetic"

import io
import time
import threading
import numpy as np
from fastapi.testclient import TestClient
from edge.camera_test import app, CameraManager


def test_camera_manager_synthetic_generation():
    """Verify synthetic frame generator produces a valid BGR image."""
    manager = CameraManager()
    frame = manager._generate_synthetic_frame(width=320, height=240)
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (240, 320, 3)
    assert frame.dtype == np.uint8


def test_camera_manager_jpeg_encoding():
    """Verify get_jpeg_frame encodes valid JPEG data."""
    manager = CameraManager()
    jpeg_bytes = manager.get_jpeg_frame()
    assert isinstance(jpeg_bytes, bytes)
    assert len(jpeg_bytes) > 0
    # Check standard JPEG header magic bytes (SOI marker 0xFFD8)
    assert jpeg_bytes.startswith(b"\xff\xd8")


def test_api_index_endpoint():
    """Verify camera diagnostic HTML preview endpoint."""
    with TestClient(app) as client:
        response = client.get("/camera_diagnostic")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "AgriSentinel" in response.text
        assert "/video_feed" in response.text


def test_api_camera_status():
    """Verify diagnostic status JSON endpoint."""
    with TestClient(app) as client:
        response = client.get("/api/camera/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_running" in data
        assert "backend" in data
        assert "resolution" in data
        assert "fps" in data
        assert "frames_served" in data


def test_api_camera_snapshot():
    """Verify snapshot endpoint returns valid JPEG image."""
    with TestClient(app) as client:
        response = client.get("/api/camera/snapshot")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content.startswith(b"\xff\xd8")


# --- FEELWORLD 4K10X PTZ Driver Unit Tests ---

def test_ptz_driver_initialization_and_limits():
    """Verify PTZCameraDriver initializes with correct limits and model specifications."""
    from edge.drivers.ptz_camera import PTZCameraDriver, MIN_PAN, MAX_PAN, MIN_TILT, MAX_TILT, MIN_ZOOM, MAX_ZOOM
    driver = PTZCameraDriver(connection_mode="usb_uvc", resolution_profile="1080p_adaptive")
    assert driver.model_name == "FEELWORLD 4K10X 4K PTZ"
    assert driver.pan == 0.0
    assert driver.tilt == 0.0
    assert driver.zoom == 1.0

    # Test clamping limits
    driver.set_position(pan=200.0, tilt=80.0, zoom=25.0)
    assert driver.pan == MAX_PAN  # 125.0
    assert driver.tilt == MAX_TILT  # 30.0
    assert driver.zoom == MAX_ZOOM  # 10.0

    driver.set_position(pan=-200.0, tilt=-80.0, zoom=0.1)
    assert driver.pan == MIN_PAN  # -125.0
    assert driver.tilt == MIN_TILT  # -30.0
    assert driver.zoom == MIN_ZOOM  # 1.0


def test_ptz_driver_step_motion_and_home():
    """Verify relative step motions (pan left/right, tilt up/down, zoom in/out, home)."""
    from edge.drivers.ptz_camera import PTZCameraDriver
    driver = PTZCameraDriver()

    driver.move_step("pan_right", step=15.0)
    assert driver.pan == 15.0

    driver.move_step("pan_left", step=20.0)
    assert driver.pan == -5.0

    driver.move_step("tilt_up", step=10.0)
    assert driver.tilt == 10.0

    driver.move_step("tilt_down", step=15.0)
    assert driver.tilt == -5.0

    driver.move_step("zoom_in", zoom_step=1.5)
    assert driver.zoom == 2.5

    driver.move_step("zoom_out", zoom_step=0.5)
    assert driver.zoom == 2.0

    driver.home()
    assert driver.pan == 0.0
    assert driver.tilt == 0.0
    assert driver.zoom == 1.0


def test_ptz_driver_presets_recall_and_save():
    """Verify canopy presets saving and recall logic."""
    from edge.drivers.ptz_camera import PTZCameraDriver
    driver = PTZCameraDriver()

    # Preset 2 is Left Row (-45°, -5°, 1.5x)
    st2 = driver.recall_preset(2)
    assert driver.pan == -45.0
    assert driver.tilt == -5.0
    assert driver.zoom == 1.5
    assert driver.active_preset_id == 2

    # Save a custom preset to slot 5
    driver.set_position(pan=33.0, tilt=12.0, zoom=4.0)
    driver.save_preset(preset_id=5, name="Zone 5 Nursery")
    assert 5 in driver.presets
    assert driver.presets[5]["name"] == "Zone 5 Nursery"
    assert driver.presets[5]["pan"] == 33.0

    # Recall another, then recall 5
    driver.home()
    assert driver.pan == 0.0
    driver.recall_preset(5)
    assert driver.pan == 33.0
    assert driver.tilt == 12.0
    assert driver.zoom == 4.0


def test_ptz_driver_patrol_modes():
    """Verify preset sweep and continuous sweep patrol mechanics."""
    from edge.drivers.ptz_camera import PTZCameraDriver
    driver = PTZCameraDriver()
    driver.set_patrol_mode("preset_sweep", interval_sec=0.01)

    # Force last patrol time backwards to trigger step
    driver._last_patrol_step_time = 0.0
    stepped = driver.step_patrol()
    assert stepped is True
    # Should have stepped to Preset 2
    assert driver.active_preset_id == 2

    # Continuous sweep mode
    driver.set_patrol_mode("continuous_sweep", interval_sec=0.01)
    driver.set_position(pan=0.0, tilt=0.0, zoom=1.0)
    driver._last_patrol_step_time = 0.0
    stepped_sweep = driver.step_patrol()
    assert stepped_sweep is True
    assert driver.pan != 0.0


def test_ptz_driver_smart_auto_zoom():
    """Verify auto-zoom behavior on pest detection and zoom restoration."""
    from edge.drivers.ptz_camera import PTZCameraDriver
    driver = PTZCameraDriver()
    driver.set_position(pan=-15.0, tilt=5.0, zoom=1.0)

    # Trigger smart zoom
    zoomed = driver.trigger_smart_zoom(zoom_target=3.5)
    assert zoomed is True
    assert driver.zoom >= 3.5

    # Restore pre-zoom position
    driver.restore_zoom()
    assert driver.pan == -15.0
    assert driver.tilt == 5.0
    assert driver.zoom == 1.0


def test_ptz_driver_virtual_viewport():
    """Verify virtual viewport pan/tilt/zoom transformation on test frame."""
    from edge.drivers.ptz_camera import PTZCameraDriver
    driver = PTZCameraDriver()
    frame = np.ones((720, 1280, 3), dtype=np.uint8) * 128

    driver.set_position(pan=20.0, tilt=-10.0, zoom=2.0)
    transformed = driver.apply_virtual_viewport(frame)
    assert transformed.shape == frame.shape
    assert isinstance(transformed, np.ndarray)


def test_ptz_resolution_profiles():
    """Verify switching resolution profiles updates capture and preview dimensions."""
    from edge.drivers.ptz_camera import PTZCameraDriver
    driver = PTZCameraDriver()

    # Switch to 720p lightweight
    driver.set_resolution_profile("720p_lightweight")
    assert driver.profile["capture_size"] == (1280, 720)
    assert driver.profile["preview_size"] == (640, 360)

    # Switch to 4k uhd
    driver.set_resolution_profile("4k_uhd")
    assert driver.profile["capture_size"] == (3840, 2160)
    assert driver.profile["preview_size"] == (640, 360)

