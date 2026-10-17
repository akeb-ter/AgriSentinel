"""
Unit and integration tests for AgriSentinel Mobile PWA client and API endpoints.
"""

import io
import os
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from edge.app import app
from edge.database import get_db_connection, delete_detection

client = TestClient(app)


def test_manifest_json():
    """Verify /static/manifest.json is accessible and properly configured for PWA."""
    res = client.get("/static/manifest.json")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "AgriSentinel Monitor"
    assert data["short_name"] == "AgriSentinel"
    assert data["start_url"] == "/mobile"
    assert data["display"] == "standalone"
    assert len(data["icons"]) >= 2


def test_service_worker_endpoint():
    """Verify /sw.js is served at root scope with Service-Worker-Allowed header."""
    res = client.get("/sw.js")
    assert res.status_code == 200
    assert "application/javascript" in res.headers.get("content-type", "")
    assert res.headers.get("service-worker-allowed") == "/"
    assert b"agrisentinel-v1" in res.content


def test_ping_endpoint():
    """Verify /api/ping returns active device heartbeat."""
    res = client.get("/api/ping")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["device"] == "agrisentinel_probe"
    assert "active_crop" in data
    assert "timestamp" in data


def test_mobile_page_requires_auth():
    """Verify /mobile redirects unauthenticated users to login with next parameter."""
    res = client.get("/mobile", follow_redirects=False)
    assert res.status_code == 302
    assert "/?next=/mobile" in res.headers["location"]


def test_mobile_page_authenticated():
    """Verify /mobile renders PWA client for authenticated session."""
    res = client.get("/mobile", cookies={"user_id": "1"})
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "AgriSentinel" in res.text
    assert "manifest.json" in res.text
    assert "cameraToggle" in res.text
    assert "capturePestBtn" in res.text
    assert "analyzePhotoBtn" in res.text
    assert "aiScanOverlay" in res.text


def test_phone_detect_upload():
    """Verify /api/detect/upload processes smartphone frame and logs to DBMS with [Phone Camera] tag."""
    # Create test JPEG frame
    dummy_frame = np.zeros((300, 300, 3), dtype=np.uint8)
    # Draw green circle
    cv2.circle(dummy_frame, (150, 150), 60, (20, 140, 30), -1)
    ret, buf = cv2.imencode(".jpg", dummy_frame)
    assert ret is True
    jpeg_bytes = buf.tobytes()

    res = client.post(
        "/api/detect/upload",
        files={"file": ("phone_shot.jpg", jpeg_bytes, "image/jpeg")},
        data={"crop_type": "corn"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["source"] == "PHONE_CAMERA"
    assert data["crop_type"] == "corn"
    assert "findings" in data
    assert "recommendation" in data
    assert "record" in data

    record = data["record"]
    rec_id = record["id"]
    assert "[Phone Camera]" in record["farm_area"]

    # Verify saved in SQLite database
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM detections WHERE id = ?", (rec_id,)).fetchone()
    conn.close()
    assert row is not None
    assert "[Phone Camera]" in row["farm_area"]

    # Clean up test detection & image
    delete_detection(rec_id)

