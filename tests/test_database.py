"""
Tests for SQLite DBMS persistence layer and detection record management.
"""

from edge.database import (
    init_db,
    insert_detection,
    get_recent_detections,
    get_detection_by_id,
    delete_detection,
    get_detection_stats
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

