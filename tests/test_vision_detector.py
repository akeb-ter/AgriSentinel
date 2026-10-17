"""
Tests for Vision Detector, TfliteRunner, and 102-Pest Taxonomy.
"""

import numpy as np
import pytest
from edge.vision.detector import (
    load_102_labels,
    PEST_LABELS_102,
    ALLOWED_STRICT_12,
    DetectionBox,
    SimulatedDetector,
    TfliteRunner,
    PestDetector,
    get_detector,
)


def test_load_102_labels():
    """Verify that all 102 labels are loaded properly."""
    labels = load_102_labels()
    assert len(labels) == 102
    assert "rice leaf roller" in labels[0].lower()
    assert "cicadellidae" in labels[-1].lower()
    assert len(PEST_LABELS_102) == 102


def test_allowed_strict_12_catalog():
    """Verify the strict 12 target classes catalog matches plan specifications."""
    assert len(ALLOWED_STRICT_12) == 12
    assert ALLOWED_STRICT_12[0] == "Rice leaf roller"
    assert ALLOWED_STRICT_12[1] == "Rice leaf caterpillar"
    assert ALLOWED_STRICT_12[3] == "Asiatic rice borer"
    assert ALLOWED_STRICT_12[4] == "Yellow rice borer"
    assert ALLOWED_STRICT_12[7] == "Brown plant hopper"
    assert ALLOWED_STRICT_12[8] == "White backed plant hopper"
    assert ALLOWED_STRICT_12[12] == "Grain spreader thrips"
    assert ALLOWED_STRICT_12[18] == "Black cutworm"
    assert ALLOWED_STRICT_12[19] == "Large cutworm"
    assert ALLOWED_STRICT_12[45] == "Corn leaf aphid"
    assert ALLOWED_STRICT_12[56] == "Fall armyworm"
    assert ALLOWED_STRICT_12[78] == "Whitefly"


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
        assert len(boxes) >= 1
        for b in boxes:
            assert b.confidence >= 0.40
            assert b.width > 0
            assert b.height > 0
            assert b.pest_key != ""


def test_tflite_runner_missing_model_no_simulation():
    """Verify TfliteRunner does NOT simulate detections when model is missing."""
    runner = TfliteRunner(model_path="nonexistent_model.tflite")
    assert runner.is_model_loaded is False
    assert runner.model_error is not None
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    boxes = runner.detect(frame, crop_type="rice")
    # Must return empty list - no fake simulation when model missing
    assert boxes == []


def test_get_detector_loads_model():
    """Verify get_detector factory initializes and loads the best.tflite model."""
    detector = get_detector()
    assert detector is not None
    assert detector.is_model_loaded is True
    assert detector.model_error is None
    assert detector.input_shape == (416, 416)
    assert detector.class_filter_mode == "strict_12"
    assert detector.conf_threshold == 0.60
    assert detector.iou_threshold == 0.45

    # Plain blank frame should return no detections
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    boxes = detector.detect(frame, crop_type="corn")
    assert isinstance(boxes, list)
    assert len(boxes) == 0


def test_pest_detector_alias():
    """Verify PestDetector class alias works identically to TfliteRunner."""
    assert PestDetector is TfliteRunner
    detector = PestDetector(conf_threshold=0.75, iou_threshold=0.50)
    assert detector.conf_threshold == 0.75
    assert detector.iou_threshold == 0.50


def test_tflite_set_parameters():
    """Verify live parameter updates on TfliteRunner."""
    runner = get_detector()
    runner.set_parameters(conf_threshold=0.70, iou_threshold=0.50, class_filter_mode="full_102")
    assert runner.conf_threshold == 0.70
    assert runner.iou_threshold == 0.50
    assert runner.class_filter_mode == "full_102"

    # Reset back to strict_12 default
    runner.set_parameters(conf_threshold=0.60, iou_threshold=0.45, class_filter_mode="strict_12")
    assert runner.conf_threshold == 0.60
    assert runner.iou_threshold == 0.45
    assert runner.class_filter_mode == "strict_12"


def test_annotate_frame_overlay():
    """Verify annotate_frame creates a valid annotated frame with Health and Model status."""
    from edge.vision.detector import annotate_frame
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    boxes = [
        DetectionBox(label="Fall Armyworm", confidence=0.88, x=10, y=20, width=50, height=50)
    ]
    annotated = annotate_frame(
        frame,
        boxes,
        crop_name="Corn",
        health_status="Mild Pest Stress",
        model_status="Online"
    )
    assert isinstance(annotated, np.ndarray)
    assert annotated.shape == (480, 640, 3)

