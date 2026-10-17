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
    # High confidence (>= 0.50)
    rec_high = knowledge_base.get_recommendation("corn", "fall_armyworm", confidence=0.88, pest_count=2)
    assert rec_high["status"] == "CONFIRMED"
    assert rec_high["is_uncertain"] is False
    assert "[VERIFY FIRST]" not in rec_high["recommended_pesticide"]

    # Borderline confidence (0.20 <= conf < 0.50) -> Uncertain caution
    rec_border = knowledge_base.get_recommendation("corn", "fall_armyworm", confidence=0.35, pest_count=2)
    assert rec_border["status"] == "UNCERTAIN"
    assert rec_border["is_uncertain"] is True
    assert "[VERIFY FIRST]" in rec_border["recommended_pesticide"]

    # Low confidence (< 0.20) -> Ignored / noise
    rec_low = knowledge_base.get_recommendation("corn", "fall_armyworm", confidence=0.15, pest_count=2)
    assert rec_low["status"] == "IGNORED_LOW_CONFIDENCE"
    assert rec_low["recommended_pesticide"] is None


def test_integrated_plant_health_derivation():
    """Verify plant health derivation based on pest pressure and infestation severity."""
    # 0 pests -> Healthy / Pest-Free
    h1 = knowledge_base.evaluate_plant_health(0, "None")
    assert h1 == "Healthy / Pest-Free"

    # Low infestation -> Mild Pest Stress
    h2 = knowledge_base.evaluate_plant_health(2, "Low")
    assert h2 == "Mild Pest Stress"

    # Moderate infestation -> Under Moderate Pest Pressure
    h3 = knowledge_base.evaluate_plant_health(4, "Moderate")
    assert h3 == "Under Moderate Pest Pressure"

    # Severe infestation -> Severe Infestation (Critical Damage Risk)
    h4 = knowledge_base.evaluate_plant_health(8, "Severe")
    assert "Severe Infestation" in h4

    # Backwards compatibility test: soil_status parameter still accepted without error
    h5 = knowledge_base.evaluate_plant_health(0, "None", soil_status="Optimal")
    assert h5 == "Healthy / Pest-Free"


def test_rice_crop_support_and_pests():
    """Verify that rice is fully supported with key IP102 pests."""
    crops = knowledge_base.get_supported_crops()
    crop_keys = [c["key"] for c in crops]
    assert "rice" in crop_keys

    rice_crop = knowledge_base.get_crop("rice")
    assert rice_crop is not None
    assert "asiatic_rice_borer" in rice_crop["pests"]
    assert "yellow_rice_borer" in rice_crop["pests"]
    assert "brown_plant_hopper" in rice_crop["pests"]

    # Test recommendation for Asiatic Rice Borer
    rec = knowledge_base.get_recommendation("rice", "asiatic_rice_borer", confidence=0.85, pest_count=3)
    assert rec["status"] == "CONFIRMED"
    assert "Chlorantraniliprole" in rec["recommended_pesticide"] or "Cartap" in rec["recommended_pesticide"]
    assert rec["crop_type"] == "rice"


def test_ip102_catalog_fallback_recommendations():
    """Verify all 102 pests can be queried with sound IPM recommendations even without crop-specific entry."""
    # Test a wheat pest (wheat sawfly) queried in corn or general
    rec_sawfly = knowledge_base.get_recommendation("corn", "wheat_sawfly", confidence=0.80, pest_count=2)
    assert rec_sawfly["status"] == "CONFIRMED"
    assert rec_sawfly["recommended_pesticide"] is not None
    assert rec_sawfly["detected_pest"] == "Wheat Sawfly"

    # Test a citrus scale pest (cottony cushion scale)
    rec_scale = knowledge_base.get_recommendation("eggplant", "icerya_purchasi_maskell", confidence=0.75, pest_count=1)
    assert rec_scale["status"] == "CONFIRMED"
    assert "Buprofezin" in rec_scale["recommended_pesticide"] or "Dinotefuran" in rec_scale["recommended_pesticide"]

    # Test an alfalfa weevil
    rec_weevil = knowledge_base.get_recommendation("mungbean", "alfalfa_weevil", confidence=0.72, pest_count=4)
    assert rec_weevil["status"] == "CONFIRMED"
    assert "Lambda-Cyhalothrin" in rec_weevil["recommended_pesticide"] or "Spinosad" in rec_weevil["recommended_pesticide"]


