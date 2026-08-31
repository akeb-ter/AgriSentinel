"""
Unit and integration tests for edge.camera_test module.
"""

import io
import time
import threading
import numpy as np
from fastapi.testclient import TestClient
from edge.camera_test import app, CameraManager, RpiCamReader


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


def test_rpicam_mjpeg_stream_parsing():
    """Verify RpiCamReader correctly reconstructs JPEG frames across arbitrary chunk boundaries."""
    reader = RpiCamReader(640, 480, 30)

    # Simulated MJPEG stream containing two JPEG frames split across chunks
    frame1 = b"\xff\xd8\xff\xe0" + b"FRAME1DATA" * 50 + b"\xff\xd9"
    frame2 = b"\xff\xd8\xff\xe0" + b"FRAME2DATA" * 50 + b"\xff\xd9"
    raw_stream = frame1 + frame2

    class DummyStdout:
        def __init__(self, data: bytes, chunk_size: int = 17):
            self.stream = io.BytesIO(data)
            self.chunk_size = chunk_size

        def read(self, _size=4096):
            return self.stream.read(self.chunk_size)

    class DummyProc:
        def __init__(self, stdout):
            self.stdout = stdout

        def poll(self):
            return 0

    reader.process = DummyProc(DummyStdout(raw_stream, chunk_size=15))
    reader.running = True

    # Run loop
    reader._read_stdout_loop()

    latest = reader.get_latest_frame()
    assert latest is not None
    assert latest == frame2
    assert latest.startswith(b"\xff\xd8")
    assert latest.endswith(b"\xff\xd9")
    assert reader.frame_count == 2


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
