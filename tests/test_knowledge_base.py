"""
Tests for Agricultural Knowledge Base loader, recommendation matching, and uncertainty handling.
"""

from edge.knowledge_base import knowledge_base


def test_knowledge_base_supported_crops():
    """Verify that all four required crops are supported out of the box."""
    crops = knowledge_base.get_supported_crops()
    crop_keys = [c["key"] for c in crops]

    assert "mungbean" in crop_keys
    assert "squash" in crop_keys
    assert "eggplant" in crop_keys
    assert "corn" in crop_keys


def test_infestation_level_calculation():
    """Verify infestation level thresholds per pest."""
    # Corn Fall Armyworm: low: 1-2, moderate: 3-5, severe: >=6
    assert knowledge_base.calculate_infestation_level("corn", "fall_armyworm", 0) == "None"
    assert knowledge_base.calculate_infestation_level("corn", "fall_armyworm", 1) == "Low"
    assert knowledge_base.calculate_infestation_level("corn", "fall_armyworm", 2) == "Low"
    assert knowledge_base.calculate_infestation_level("corn", "fall_armyworm", 3) == "Moderate"
    assert knowledge_base.calculate_infestation_level("corn", "fall_armyworm", 5) == "Moderate"
    assert knowledge_base.calculate_infestation_level("corn", "fall_armyworm", 6) == "Severe"
    assert knowledge_base.calculate_infestation_level("corn", "fall_armyworm", 12) == "Severe"


def test_two_tier_confidence_and_uncertainty():
    """Verify two-tier confidence enforcement and amber caution flags."""
    # High confidence (>= 0.70)
    rec_high = knowledge_base.get_recommendation("corn", "fall_armyworm", confidence=0.88, pest_count=2)
    assert rec_high["status"] == "CONFIRMED"
    assert rec_high["is_uncertain"] is False
    assert "[VERIFY FIRST]" not in rec_high["recommended_pesticide"]

    # Borderline confidence (0.40 <= conf < 0.70) -> Uncertain caution
    rec_border = knowledge_base.get_recommendation("corn", "fall_armyworm", confidence=0.55, pest_count=2)
    assert rec_border["status"] == "UNCERTAIN"
    assert rec_border["is_uncertain"] is True
    assert "[VERIFY FIRST]" in rec_border["recommended_pesticide"]

    # Low confidence (< 0.40) -> Ignored / noise
    rec_low = knowledge_base.get_recommendation("corn", "fall_armyworm", confidence=0.25, pest_count=2)
    assert rec_low["status"] == "IGNORED_LOW_CONFIDENCE"
    assert rec_low["recommended_pesticide"] is None


def test_integrated_plant_health_derivation():
    """Verify plant health derivation combining pest pressure and soil moisture."""
    # 0 pests, Optimal soil -> Healthy
    h1 = knowledge_base.evaluate_plant_health(0, "None", "Optimal")
    assert "Healthy" in h1

    # 0 pests, Dry soil -> Moisture stress (drought risk)
    h2 = knowledge_base.evaluate_plant_health(0, "None", "Dry")
    assert "Drought Risk" in h2 or "Moisture Stress" in h2

    # 0 pests, Waterlogged soil -> Excess moisture (fungal risk)
    h3 = knowledge_base.evaluate_plant_health(0, "None", "Waterlogged")
    assert "Fungal" in h3 or "Excess Moisture" in h3

    # Severe pests -> Severe infestation
    h4 = knowledge_base.evaluate_plant_health(8, "Severe", "Optimal")
    assert "Severe Infestation" in h4

