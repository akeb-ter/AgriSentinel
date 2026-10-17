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
    """Verify get_detector factory initializes and loads the active model."""
    detector = get_detector()
    assert detector is not None
    assert detector.is_model_loaded is True
    assert detector.model_error is None
    assert detector.input_shape in [(416, 416), (640, 640)]
    assert detector.class_filter_mode == "full_102"
    assert detector.conf_threshold == 0.25
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
    runner.set_parameters(conf_threshold=0.70, iou_threshold=0.50, class_filter_mode="strict_12")
    assert runner.conf_threshold == 0.70
    assert runner.iou_threshold == 0.50
    assert runner.class_filter_mode == "strict_12"

    # Reset back to full_102 default
    runner.set_parameters(conf_threshold=0.25, iou_threshold=0.45, class_filter_mode="full_102")
    assert runner.conf_threshold == 0.25
    assert runner.iou_threshold == 0.45
    assert runner.class_filter_mode == "full_102"


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


def test_concurrent_detection_thread_safety():
    """Verify that concurrent calls to detect() across multiple threads are thread-safe and do not crash or corrupt state."""
    import threading
    detector = get_detector()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    errors = []

    def worker():
        for _ in range(5):
            try:
                res = detector.detect(frame, crop_type="corn")
                assert isinstance(res, list)
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0


def test_multi_model_profile_switching():
    """Verify switching across all 4 MODEL_PROFILES."""
    from edge.vision.detector import MODEL_PROFILES
    detector = get_detector()

    assert "comprehensive_102" in MODEL_PROFILES
    assert "fast_scout_3pests" in MODEL_PROFILES
    assert "cereal_diagnostic" in MODEL_PROFILES
    assert "species_encyclopedia" in MODEL_PROFILES

    # 1. Switch to Fast Scout 3-Pests
    ok_scout = detector.switch_model("fast_scout_3pests")
    assert ok_scout is True
    assert detector.active_profile == "fast_scout_3pests"
    assert detector.is_model_loaded is True
    assert len(detector.labels) == 3

    # 2. Switch to Cereal Diagnostic
    ok_cereal = detector.switch_model("cereal_diagnostic")
    assert ok_cereal is True
    assert detector.active_profile == "cereal_diagnostic"
    assert detector.is_model_loaded is True
    assert len(detector.labels) == 26

    # 3. Switch to Species Encyclopedia (Quarrying ONNX)
    ok_onnx = detector.switch_model("species_encyclopedia")
    assert ok_onnx is True
    assert detector.active_profile == "species_encyclopedia"
    assert detector.is_model_loaded is True
    assert detector.runtime_name == "onnxruntime"
    assert len(detector.labels) == 2037

    # 4. Switch back to Comprehensive 102
    ok_comp = detector.switch_model("comprehensive_102")
    assert ok_comp is True
    assert detector.active_profile == "comprehensive_102"
    assert detector.is_model_loaded is True
    assert len(detector.labels) == 102


def test_detection_box_beneficial_flag():
    """Verify DetectionBox beneficial flag and serialization."""
    b_pest = DetectionBox("Fall Armyworm", 0.85, 10, 20, 50, 50, is_beneficial=False)
    assert b_pest.is_beneficial is False
    assert b_pest.to_dict()["is_beneficial"] is False

    b_pred = DetectionBox("Ladybug", 0.94, 30, 40, 60, 60, is_beneficial=True, taxonomy="Coleoptera: Coccinellidae")
    assert b_pred.is_beneficial is True
    assert b_pred.taxonomy == "Coleoptera: Coccinellidae"
    assert b_pred.to_dict()["is_beneficial"] is True
    assert b_pred.to_dict()["taxonomy"] == "Coleoptera: Coccinellidae"


def test_annotate_frame_beneficial_badge():
    """Verify annotate_frame renders beneficial predator alert without errors."""
    from edge.vision.detector import annotate_frame
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    boxes = [
        DetectionBox(label="Ladybug", confidence=0.92, x=20, y=30, width=60, height=60, is_beneficial=True)
    ]
    annotated = annotate_frame(frame, boxes, crop_name="Corn", health_status="Healthy / Pest-Free")
    assert annotated.shape == (480, 640, 3)


def test_cereal_and_quarrying_inference_execution():
    """Verify that cereal and quarrying models run inference on sample frames without crashing."""
    detector = get_detector()
    blank = np.zeros((480, 640, 3), dtype=np.uint8)

    # Test cereal inference
    detector.switch_model("cereal_diagnostic")
    res_cereal = detector.detect(blank, conf_threshold=0.99)
    assert isinstance(res_cereal, list)

    # Test quarrying inference
    detector.switch_model("species_encyclopedia")
    res_quarry = detector.detect(blank, conf_threshold=0.99)
    assert isinstance(res_quarry, list)

    # Reset back to comprehensive
    detector.switch_model("comprehensive_102")


