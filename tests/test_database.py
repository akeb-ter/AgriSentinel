"""
Tests for SQLite DBMS persistence layer and detection record management.
"""

from edge.database import (
    init_db,
    insert_detection,
    get_recent_detections,
    get_detection_by_id,
    delete_detection,
    get_detection_stats,
    query_detections,
    delete_detections_batch,
    clear_detections
)


def test_database_crud_operations():
    """Verify insert, retrieve, filter, stats, and delete operations on detections table."""
    init_db()

    # 1. Insert test detection
    payload = {
        "crop_type": "eggplant",
        "farm_area": "Test Greenhouse B",
        "detected_pest": "Fruit and Shoot Borer",
        "pest_count": 4,
        "infestation_level": "Moderate",
        "soil_moisture_percent": 48.5,
        "soil_status": "Optimal",
        "plant_health_status": "Under Moderate Pest Pressure",
        "confidence": 0.89,
        "recommended_pesticide": "Flubendiamide 39.35% SC",
        "status": "CONFIRMED"
    }
    rec_id = insert_detection(payload)
    assert isinstance(rec_id, int)
    assert rec_id > 0

    # 2. Get by ID
    rec = get_detection_by_id(rec_id)
    assert rec is not None
    assert rec["detected_pest"] == "Fruit and Shoot Borer"
    assert rec["pest_count"] == 4
    assert rec["crop_type"] == "eggplant"

    # 3. Filter by crop
    eggplant_recs = get_recent_detections(limit=10, crop_type="eggplant")
    assert len(eggplant_recs) >= 1
    assert any(r["id"] == rec_id for r in eggplant_recs)

    # 4. Check statistics
    stats = get_detection_stats()
    assert stats["total_inspections"] >= 1
    assert "top_pests" in stats

    # 5. Delete detection
    del_ok = delete_detection(rec_id)
    assert del_ok is True
    assert get_detection_by_id(rec_id) is None


def test_database_insert_without_soil_fields():
    """Verify insert_detection functions smoothly without soil moisture fields."""
    init_db()
    payload = {
        "crop_type": "rice",
        "farm_area": "Paddy 3",
        "detected_pest": "Brown Plant Hopper",
        "pest_count": 2,
        "infestation_level": "Low",
        "plant_health_status": "Mild Pest Stress",
        "confidence": 0.92,
        "recommended_pesticide": "Triflemezopyrim 10% SC",
        "status": "CONFIRMED"
    }
    rec_id = insert_detection(payload)
    assert rec_id > 0
    rec = get_detection_by_id(rec_id)
    assert rec["soil_moisture_percent"] == 0.0
    assert rec["soil_status"] == "N/A"
    delete_detection(rec_id)


def test_query_detections_filtering_and_pagination():
    """Verify query_detections supports multi-tier filtering, search, and pagination."""
    init_db()

    # Create distinct records
    ids = []
    ids.append(insert_detection({
        "crop_type": "corn",
        "farm_area": "Field Alpha [Phone Camera]",
        "detected_pest": "Fall Armyworm",
        "pest_count": 5,
        "infestation_level": "Severe",
        "confidence": 0.88,
        "plant_health_status": "Severe Damage",
        "recommended_pesticide": "Chlorantraniliprole",
        "status": "CONFIRMED"
    }))
    ids.append(insert_detection({
        "crop_type": "corn",
        "farm_area": "Field Beta",
        "detected_pest": "Corn Earworm",
        "pest_count": 2,
        "infestation_level": "Low",
        "confidence": 0.45,
        "plant_health_status": "Minor Leaf Chewing",
        "recommended_pesticide": "Spinetoram",
        "status": "UNCERTAIN"
    }))
    ids.append(insert_detection({
        "crop_type": "eggplant",
        "farm_area": "Greenhouse 1",
        "detected_pest": "Eggplant Fruit Borer",
        "pest_count": 8,
        "infestation_level": "Severe",
        "confidence": 0.95,
        "plant_health_status": "Severe Stems Bored",
        "recommended_pesticide": "Flubendiamide",
        "status": "CONFIRMED"
    }))

    try:
        # Filter by crop
        res = query_detections(crop_type="corn")
        assert all(r["crop_type"] == "corn" for r in res["records"])
        assert res["total"] >= 2

        # Filter by infestation
        res_sev = query_detections(infestation_level="Severe")
        assert all(r["infestation_level"] == "Severe" for r in res_sev["records"])

        # Filter by search
        res_search = query_detections(search="Armyworm")
        assert any("Armyworm" in r["detected_pest"] for r in res_search["records"])

        # Filter by confidence
        res_conf = query_detections(min_confidence=0.80)
        assert all(r["confidence"] >= 0.80 for r in res_conf["records"])

        # Filter by source (phone vs robot)
        res_phone = query_detections(source="phone")
        assert any(r["id"] == ids[0] for r in res_phone["records"])
        res_robot = query_detections(source="robot")
        assert all("[Phone Camera]" not in (r["farm_area"] or "") for r in res_robot["records"])

        # Pagination test
        page1 = query_detections(limit=1, offset=0)
        assert len(page1["records"]) == 1
        assert page1["total"] >= 3

    finally:
        delete_detections_batch(ids)


def test_delete_detections_batch():
    """Verify delete_detections_batch cleanly deletes multiple records in one atomic operation."""
    init_db()

    id1 = insert_detection({"crop_type": "rice", "farm_area": "Batch Plot 1", "detected_pest": "Pest A", "status": "CONFIRMED"})
    id2 = insert_detection({"crop_type": "rice", "farm_area": "Batch Plot 2", "detected_pest": "Pest B", "status": "CONFIRMED"})
    id3 = insert_detection({"crop_type": "rice", "farm_area": "Batch Plot 3", "detected_pest": "Pest C", "status": "CONFIRMED"})

    deleted_count = delete_detections_batch([id1, id2])
    assert deleted_count == 2
    assert get_detection_by_id(id1) is None
    assert get_detection_by_id(id2) is None
    assert get_detection_by_id(id3) is not None

    # Empty batch returns 0
    assert delete_detections_batch([]) == 0

    # Cleanup remaining
    delete_detection(id3)


def test_clear_detections():
    """Verify clear_detections with filter or full wipe."""
    init_db()

    id1 = insert_detection({"crop_type": "squash", "farm_area": "Plot S1", "detected_pest": "Squash Beetle", "infestation_level": "Low", "status": "CONFIRMED"})
    id2 = insert_detection({"crop_type": "squash", "farm_area": "Plot S2", "detected_pest": "Fruit Fly", "infestation_level": "Severe", "status": "CONFIRMED"})
    id3 = insert_detection({"crop_type": "mungbean", "farm_area": "Plot M1", "detected_pest": "Pod Borer", "infestation_level": "Medium", "status": "CONFIRMED"})

    # Filtered clear: delete only squash with Severe infestation
    cleared = clear_detections(filters={"crop_type": "squash", "infestation_level": "Severe"})
    assert cleared >= 1
    assert get_detection_by_id(id2) is None
    assert get_detection_by_id(id1) is not None
    assert get_detection_by_id(id3) is not None

    # Cleanup remaining
    delete_detections_batch([id1, id3])


