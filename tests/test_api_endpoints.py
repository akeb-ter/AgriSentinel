"""
Integration tests for AgriSentinel REST and Web API endpoints.
"""

from fastapi.testclient import TestClient
from edge.app import app

client = TestClient(app)


def test_api_status_endpoint():
    """Verify /api/status returns probe telemetry."""
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "telemetry" in data
    assert "active_crop" in data["telemetry"]
    assert "plant_health_status" in data["telemetry"]
    assert "model_loaded" in data["telemetry"]


def test_api_crops_endpoint():
    """Verify /api/crops returns supported crops list."""
    res = client.get("/api/crops")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    crops = data["crops"]
    keys = [c["key"] for c in crops]
    assert "mungbean" in keys
    assert "squash" in keys
    assert "eggplant" in keys
    assert "corn" in keys


def test_api_select_crop():
    """Verify /api/crop/select updates the active crop."""
    res = client.post("/api/crop/select", json={"crop": "squash"})
    assert res.status_code == 200
    data = res.json()
    assert data["active_crop"] == "squash"


def test_api_stats():
    """Verify /api/stats returns calculation statistics including avg_confidence."""
    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "stats" in data
    assert "avg_confidence" in data["stats"]


def test_api_recommendation_query():
    """Verify /api/recommendations/{crop}/{pest} returns accurate agricultural advice."""
    res = client.get("/api/recommendations/corn/fall_armyworm?confidence=0.85")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    rec = data["recommendation"]
    assert rec["detected_pest"] == "Fall Armyworm"
    assert "Chlorantraniliprole" in rec["recommended_pesticide"]


def test_api_manual_analyze():
    """Verify /api/analyze creates and logs an immediate inspection snapshot."""
    res = client.post("/api/analyze", json={"crop_type": "corn", "farm_area": "Test Field 1"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    record = data["record"]
    assert record["crop_type"] == "corn"
    assert "id" in record
    assert record["id"] is not None


def test_api_detections_list():
    """Verify /api/detections returns historical inspection records."""
    res = client.get("/api/detections?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert "detections" in data
    assert isinstance(data["detections"], list)


def test_api_vision_settings():
    """Verify /api/dev/vision_settings GET and POST functionality."""
    res = client.get("/api/dev/vision_settings")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "model_loaded" in data
    assert "class_filter_mode" in data
    assert "conf_threshold" in data
    assert "iou_threshold" in data
    assert "active_classes" in data

    # Test updating parameters
    update_res = client.post("/api/dev/vision_settings", json={
        "class_filter_mode": "full_102",
        "conf_threshold": 0.65,
        "iou_threshold": 0.40
    })
    assert update_res.status_code == 200
    up_data = update_res.json()
    assert up_data["status"] == "success"
    assert up_data["settings"]["class_filter_mode"] == "full_102"
    assert up_data["settings"]["conf_threshold"] == 0.65

    # Reset back to default
    client.post("/api/dev/vision_settings", json={
        "class_filter_mode": "full_102",
        "conf_threshold": 0.25,
        "iou_threshold": 0.45
    })


