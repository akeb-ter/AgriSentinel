"""
Unit and integration tests for edge.camera_test module.
"""

import cv2
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
    """Verify root HTML preview endpoint."""
    with TestClient(app) as client:
        response = client.get("/")
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
        assert "synthetic_mode" in data
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
