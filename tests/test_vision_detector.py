"""
Tests for Vision Detector, TfliteRunner, and 102-Pest Taxonomy.
"""

import numpy as np
import pytest
from edge.vision.detector import (
    load_102_labels,
    PEST_LABELS_102,
    DetectionBox,
    SimulatedDetector,
    TfliteRunner,
    get_detector,
)


def test_load_102_labels():
    """Verify that all 102 labels are loaded properly."""
    labels = load_102_labels()
    assert len(labels) == 102
    assert "rice leaf roller" in labels[0].lower()
    assert "cicadellidae" in labels[-1].lower()
    assert len(PEST_LABELS_102) == 102


def test_detection_box_structure():
    """Verify DetectionBox creation and serialization."""
    box = DetectionBox(
        label="Asiatic Rice Borer",
        confidence=0.892,
        x=50,
        y=60,
        width=120,
        height=140,
        pest_key="asiatic_rice_borer"
    )
    d = box.to_dict()
    assert d["label"] == "Asiatic Rice Borer"
    assert d["pest_key"] == "asiatic_rice_borer"
    assert d["confidence"] == 0.892
    assert d["box"]["x"] == 50
    assert d["box"]["y"] == 60
    assert d["box"]["width"] == 120
    assert d["box"]["height"] == 140


def test_simulated_detector_multi_crop():
    """Verify simulated detector produces pest candidates for all 5 crops."""
    detector = SimulatedDetector()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    for crop in ["rice", "corn", "mungbean", "squash", "eggplant"]:
        boxes = detector.detect(frame, crop_type=crop)
        # Should return between 1 and 3 simulated boxes
        assert len(boxes) >= 1
        for b in boxes:
            assert b.confidence >= 0.40
            assert b.width > 0
            assert b.height > 0
            assert b.pest_key != ""


def test_simulated_detector_force_pest():
    """Verify simulated detector force override."""
    detector = SimulatedDetector()
    detector.set_simulation_state(enabled=True, pest="yellow_rice_borer", count=2)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    boxes = detector.detect(frame, crop_type="rice")
    assert len(boxes) == 2
    for b in boxes:
        assert b.pest_key == "yellow_rice_borer"


def test_tflite_runner_simulated_fallback():
    """Verify TfliteRunner gracefully falls back when no physical .tflite weights are present."""
    runner = TfliteRunner(model_path="nonexistent_model.tflite")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    boxes = runner.detect(frame, crop_type="rice")
    assert len(boxes) >= 1


def test_get_detector_factory():
    """Verify get_detector factory initializes successfully."""
    detector = get_detector()
    assert detector is not None
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    boxes = detector.detect(frame, crop_type="corn")
    assert len(boxes) >= 1
