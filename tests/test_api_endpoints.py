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
    assert "soil_moisture_percent" in data["telemetry"]


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


def test_api_soil_moisture():
    """Verify /api/soil-moisture returns sensor data."""
    res = client.get("/api/soil-moisture")
    assert res.status_code == 200
    data = res.json()
    assert "soil_moisture" in data
    assert "moisture_percent" in data["soil_moisture"]


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

