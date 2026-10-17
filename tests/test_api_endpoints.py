"""
Integration tests for AgriSentinel REST and Web API endpoints.
"""

from fastapi.testclient import TestClient
from edge.app import app
from edge.database import init_db, insert_detection, delete_detections_batch

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


def test_api_detections_pagination_and_filters():
    """Verify /api/detections supports pagination metadata and query filters."""
    init_db()
    ids = []
    ids.append(insert_detection({
        "crop_type": "rice",
        "farm_area": "Test Paddy A",
        "detected_pest": "Stem Borer",
        "infestation_level": "Medium",
        "confidence": 0.82,
        "status": "CONFIRMED"
    }))
    ids.append(insert_detection({
        "crop_type": "rice",
        "farm_area": "Test Paddy B [Phone Camera]",
        "detected_pest": "Rice Bug",
        "infestation_level": "Severe",
        "confidence": 0.91,
        "status": "CONFIRMED"
    }))

    try:
        # Test pagination query params
        res = client.get("/api/detections?page=1&page_size=1&crop_type=rice")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert len(data["detections"]) == 1
        assert "pagination" in data
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 1
        assert data["pagination"]["total"] >= 2
        assert data["pagination"]["total_pages"] >= 2

        # Test source filter
        res_source = client.get("/api/detections?source=phone")
        assert res_source.status_code == 200
        data_src = res_source.json()
        assert any("[Phone Camera]" in d.get("farm_area", "") for d in data_src["detections"])

        # Test min confidence filter
        res_conf = client.get("/api/detections?min_confidence=0.90")
        assert res_conf.status_code == 200
        for d in res_conf.json()["detections"]:
            assert d["confidence"] >= 0.90

    finally:
        delete_detections_batch(ids)


def test_api_detections_batch_delete():
    """Verify /api/detections/batch-delete removes records and returns count."""
    init_db()
    id1 = insert_detection({"crop_type": "corn", "detected_pest": "Batch Pest 1", "status": "CONFIRMED"})
    id2 = insert_detection({"crop_type": "corn", "detected_pest": "Batch Pest 2", "status": "CONFIRMED"})

    res = client.post("/api/detections/batch-delete", json={"ids": [id1, id2]})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["deleted_count"] == 2

    # Verify they no longer exist
    res_get = client.get(f"/api/detections/{id1}")
    assert res_get.status_code == 404


def test_api_detections_clear():
    """Verify /api/detections/clear removes filtered records."""
    init_db()
    id1 = insert_detection({"crop_type": "test_clear_crop", "detected_pest": "Clear Pest 1", "infestation_level": "Severe", "status": "CONFIRMED"})
    id2 = insert_detection({"crop_type": "test_clear_crop", "detected_pest": "Clear Pest 2", "infestation_level": "Low", "status": "CONFIRMED"})

    # Clear only the Severe one
    res = client.post("/api/detections/clear", json={
        "clear_all": False,
        "filters": {
            "crop_type": "test_clear_crop",
            "infestation_level": "Severe"
        }
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["deleted_count"] >= 1

    # Clean up the Low one
    delete_detections_batch([id2])


def test_api_dev_vision_settings_get_and_post():
    """Verify /api/dev/vision_settings returns profiles and accepts model_profile update."""
    res_get = client.get("/api/dev/vision_settings")
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["status"] == "success"
    assert "active_model_profile" in data_get
    assert "available_profiles" in data_get
    assert len(data_get["available_profiles"]) == 4

    # Update model profile to fast_scout_3pests
    res_post = client.post("/api/dev/vision_settings", json={
        "model_profile": "fast_scout_3pests",
        "conf_threshold": 0.30,
        "class_filter_mode": "full_102"
    })
    assert res_post.status_code == 200
    data_post = res_post.json()
    assert data_post["status"] == "success"
    assert data_post["settings"]["active_model_profile"] == "fast_scout_3pests"
    assert data_post["settings"]["conf_threshold"] == 0.30

    # Reset back to comprehensive_102
    res_reset = client.post("/api/dev/vision_settings", json={
        "model_profile": "comprehensive_102",
        "conf_threshold": 0.25,
        "class_filter_mode": "full_102"
    })
    assert res_reset.status_code == 200
    assert res_reset.json()["settings"]["active_model_profile"] == "comprehensive_102"


def test_api_detect_upload_with_model_profile():
    """Verify /api/detect/upload accepts custom model_profile form field."""
    import cv2
    import numpy as np
    dummy_img = np.zeros((224, 224, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", dummy_img)

    res = client.post(
        "/api/detect/upload",
        files={"file": ("test.jpg", encoded.tobytes(), "image/jpeg")},
        data={"crop_type": "corn", "conf_threshold": "0.99", "model_profile": "species_encyclopedia"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["source"] == "PHONE_CAMERA"
    assert "recommendation" in data




