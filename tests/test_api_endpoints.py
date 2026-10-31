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
    assert len(data_get["available_profiles"]) == 5
    profile_ids = [p["id"] for p in data_get["available_profiles"]]
    assert "tropical_27_pests" in profile_ids

    # Update model profile to tropical_27_pests
    res_post_trop = client.post("/api/dev/vision_settings", json={
        "model_profile": "tropical_27_pests",
        "conf_threshold": 0.25,
        "class_filter_mode": "full_102"
    })
    assert res_post_trop.status_code == 200
    assert res_post_trop.json()["settings"]["active_model_profile"] == "tropical_27_pests"

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


# --- FEELWORLD 4K10X PTZ API Endpoint Tests ---

def test_api_ptz_status():
    """Verify /api/ptz/status returns FEELWORLD 4K10X telemetry and limits."""
    res = client.get("/api/ptz/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "ptz" in data
    ptz = data["ptz"]
    assert ptz["model_name"] == "FEELWORLD 4K10X 4K PTZ"
    assert "pan" in ptz
    assert "tilt" in ptz
    assert "zoom" in ptz
    assert "presets" in ptz
    assert "limits" in ptz
    assert ptz["limits"]["min_pan"] == -125.0
    assert ptz["limits"]["max_pan"] == 125.0


def test_api_ptz_move_step_and_set():
    """Verify /api/ptz/move supports both relative direction steps and absolute coordinates."""
    # Move step pan_right
    res_step = client.post("/api/ptz/move", json={"action": "pan_right", "step": 10.0})
    assert res_step.status_code == 200
    assert res_step.json()["status"] == "success"

    # Home
    res_home = client.post("/api/ptz/move", json={"action": "home"})
    assert res_home.status_code == 200
    assert res_home.json()["ptz"]["pan"] == 0.0
    assert res_home.json()["ptz"]["tilt"] == 0.0
    assert res_home.json()["ptz"]["zoom"] == 1.0

    # Set absolute coordinates
    res_set = client.post("/api/ptz/move", json={"action": "set", "pan": 35.0, "tilt": -10.0, "zoom": 3.0})
    assert res_set.status_code == 200
    assert res_set.json()["ptz"]["pan"] == 35.0
    assert res_set.json()["ptz"]["tilt"] == -10.0
    assert res_set.json()["ptz"]["zoom"] == 3.0

    # Clean up back to home
    client.post("/api/ptz/move", json={"action": "home"})


def test_api_ptz_preset_recall_and_save():
    """Verify /api/ptz/preset recalls preset slots and saves new positions."""
    # Recall Preset 1 (Center Canopy)
    res_recall = client.post("/api/ptz/preset", json={"action": "recall", "preset_id": 1})
    assert res_recall.status_code == 200
    assert res_recall.json()["ptz"]["active_preset_id"] == 1

    # Save to Preset 6
    client.post("/api/ptz/move", json={"action": "set", "pan": -20.0, "tilt": 8.0, "zoom": 2.0})
    res_save = client.post("/api/ptz/preset", json={"action": "save", "preset_id": 6, "name": "East Gate"})
    assert res_save.status_code == 200
    assert "6" in res_save.json()["ptz"]["presets"] or 6 in res_save.json()["ptz"]["presets"]

    client.post("/api/ptz/move", json={"action": "home"})


def test_api_ptz_patrol_config():
    """Verify /api/ptz/patrol configures sweep mode and auto zoom."""
    res = client.post("/api/ptz/patrol", json={
        "patrol_mode": "preset_sweep",
        "interval_sec": 12.0,
        "auto_zoom_on_detect": True
    })
    assert res.status_code == 200
    ptz = res.json()["ptz"]
    assert ptz["patrol_mode"] == "preset_sweep"
    assert ptz["patrol_interval_sec"] == 12.0
    assert ptz["auto_zoom_on_detect"] is True

    # Turn off patrol
    client.post("/api/ptz/patrol", json={"patrol_mode": "off"})


def test_api_dev_camera_config():
    """Verify /api/dev/camera/config updates transport mode and resolution profile."""
    res = client.post("/api/dev/camera/config", json={
        "resolution_profile": "720p_lightweight",
        "connection_mode": "usb_uvc"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["telemetry"]["resolution_profile"] == "720p_lightweight"
    assert data["telemetry"]["capture_resolution"] == "1280x720"

    # Reset back to recommended 1080p adaptive
    res_reset = client.post("/api/dev/camera/config", json={
        "resolution_profile": "1080p_adaptive",
        "connection_mode": "usb_uvc"
    })
    assert res_reset.status_code == 200
    assert res_reset.json()["telemetry"]["resolution_profile"] == "1080p_adaptive"


def test_api_vision_live_toggle_and_manual_analyze():
    """Verify Live AI toggle disables background inference while manual analyze continues to work."""
    # 1. Turn Live AI OFF
    res_off = client.post("/api/vision/live_toggle", json={"enabled": False})
    assert res_off.status_code == 200
    data_off = res_off.json()
    assert data_off["status"] == "success"
    assert data_off["live_ai_enabled"] is False

    # 2. Check /api/ping reflects live_ai_enabled == False
    res_ping = client.get("/api/ping")
    assert res_ping.status_code == 200
    assert res_ping.json()["live_ai_enabled"] is False

    # 3. Manual analyze MUST still execute successfully
    res_analyze = client.post("/api/analyze", json={"crop_type": "rice", "farm_area": "North Paddy"})
    assert res_analyze.status_code == 200
    data_analyze = res_analyze.json()
    assert data_analyze["status"] == "success"
    assert "record" in data_analyze
    assert data_analyze["record"]["crop_type"] == "rice"

    # 4. Turn Live AI back ON
    res_on = client.post("/api/vision/live_toggle", json={"enabled": True})
    assert res_on.status_code == 200
    data_on = res_on.json()
    assert data_on["status"] == "success"
    assert data_on["live_ai_enabled"] is True

    # 5. Check /api/ping reflects live_ai_enabled == True
    res_ping2 = client.get("/api/ping")
    assert res_ping2.status_code == 200
    assert res_ping2.json()["live_ai_enabled"] is True






