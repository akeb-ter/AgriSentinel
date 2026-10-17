"""
AgriSentinel - Modular AI Vision & Pest Detection Pipeline

Provides a pluggable inference interface:
1. TfliteRunner (PestDetector): Runs TensorFlow Lite (.tflite) YOLOv8/YOLO11 models
   trained on the 102 pest taxonomy (IP102 benchmark), supporting strict 12-class target
   filtering (default) or full 102-class catalog (beta).
2. EdgeImpulseRunner: Runs compiled .eim Linux binaries on Raspberry Pi (Edge Impulse runner)
3. SimulatedDetector: High-fidelity simulation available for offline tests
"""

import os
import time
import math
import json
import random
import logging
import zipfile
import io
import threading
from typing import List, Dict, Any, Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger("AgriSentinel-Vision")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
LABELS_PATH = os.path.join(CONFIG_DIR, "labels.txt")
CLASSES_JSON = os.path.join(CONFIG_DIR, "pest_classes_102.json")
MODELS_DIR = os.path.join(BASE_DIR, "edge", "models")

# Color palette for bounding boxes and UI overlays (BGR format)
BOX_COLORS = [
    (0, 215, 255),   # Gold / Yellow
    (0, 165, 255),   # Orange
    (50, 205, 50),   # Lime Green
    (238, 104, 123), # Soft Blue
    (147, 20, 255),  # Deep Pink
]

# Target IP102 Class IDs for Rice, Corn, Eggplant, Squash, and Mungbean pests (Strict 12 Default)
ALLOWED_STRICT_12 = {
    0: "Rice leaf roller",
    1: "Rice leaf caterpillar",
    3: "Asiatic rice borer",
    4: "Yellow rice borer",
    7: "Brown plant hopper",
    8: "White backed plant hopper",
    12: "Grain spreader thrips",
    18: "Black cutworm",
    19: "Large cutworm",
    45: "Corn leaf aphid",
    56: "Fall armyworm",
    78: "Whitefly"
}

# Target taxonomic aliases to map actual YOLO11 IP102 model class indices
TARGET_PEST_ALIASES = {
    22: "Corn borer",
    23: "Army worm",
    24: "Aphids",
    27: "English grain aphid",
    28: "Green bug",
    38: "Cabbage army worm",
    39: "Beet army worm",
    54: "Thrips",
    71: "Whitefly",
    21: "Red spider",
    37: "Flea beetle",
    15: "Mole cricket"
}


def load_102_labels() -> List[str]:
    """Loads 102 pest class labels from config file, with fallback."""
    if os.path.exists(LABELS_PATH):
        try:
            with open(LABELS_PATH, "r", encoding="utf-8") as f:
                labels = [line.strip() for line in f if line.strip()]
            if len(labels) >= 100:
                return labels
        except Exception as e:
            logger.warning(f"Failed loading labels.txt: {e}")

    if os.path.exists(CLASSES_JSON):
        try:
            with open(CLASSES_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [c["name"] for c in data.get("classes", [])]
        except Exception as e:
            logger.warning(f"Failed loading pest_classes_102.json: {e}")

    # Builtin top 25 fallback
    return [
        "rice leaf roller", "rice leaf caterpillar", "paddy stem maggot",
        "asiatic rice borer", "yellow rice borer", "rice gall midge",
        "Rice Stemfly", "brown plant hopper", "white backed plant hopper",
        "small brown plant hopper", "rice water weevil", "rice leafhopper",
        "grain spreader thrips", "rice shell pest", "grub", "mole cricket",
        "wireworm", "white margined moth", "black cutworm", "large cutworm",
        "yellow cutworm", "red spider", "corn borer", "army worm", "aphids"
    ]


PEST_LABELS_102 = load_102_labels()


def extract_tflite_metadata(model_path: str) -> Optional[Dict[str, Any]]:
    """Extracts embedded zip metadata from TFLite flatbuffer if present."""
    if not model_path or not os.path.exists(model_path):
        return None
    try:
        with open(model_path, "rb") as f:
            buf = f.read()
        idx = buf.rfind(b"PK\x03\x04")
        if idx != -1:
            zf = zipfile.ZipFile(io.BytesIO(buf[idx:]))
            if "metadata.json" in zf.namelist():
                return json.loads(zf.read("metadata.json").decode("utf-8"))
    except Exception as e:
        logger.debug(f"Failed extracting tflite metadata: {e}")
    return None


class DetectionBox:
    """Represents a single detected pest instance."""

    def __init__(
        self,
        label: str,
        confidence: float,
        x: int,
        y: int,
        width: int,
        height: int,
        pest_key: Optional[str] = None
    ):
        self.label = label
        self.confidence = float(confidence)
        self.x = max(0, int(x))
        self.y = max(0, int(y))
        self.width = max(10, int(width))
        self.height = max(10, int(height))
        self.pest_key = pest_key or label.lower().strip().replace(" ", "_").replace("-", "_")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "pest_key": self.pest_key,
            "confidence": round(self.confidence, 3),
            "box": {
                "x": self.x,
                "y": self.y,
                "width": self.width,
                "height": self.height,
            }
        }


class BasePestDetector:
    """Abstract base detector interface."""

    def detect(self, frame_bgr: np.ndarray, crop_type: str = "corn") -> List[DetectionBox]:
        raise NotImplementedError


class TfliteRunner(BasePestDetector):
    """
    Dedicated TensorFlow Lite inference engine supporting YOLOv8 / YOLO11
    and SSD MobileNet models trained on the IP102 pest taxonomy.
    """

    ALLOWED_CLASSES = ALLOWED_STRICT_12  # Compatibility with plan.md.txt

    def __init__(
        self,
        model_path: Optional[str] = None,
        conf_threshold: float = float(os.getenv("TFLITE_CONF_THRESHOLD", "0.25")),
        iou_threshold: float = 0.45,
        class_filter_mode: str = os.getenv("TFLITE_FILTER_MODE", "full_102"),
        labels: Optional[List[str]] = None
    ):
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.class_filter_mode = class_filter_mode  # "strict_12" or "full_102"
        self.labels = labels or list(PEST_LABELS_102)

        self.model_path = model_path
        self.interpreter = None
        self._input_details = None
        self._output_details = None
        self.input_shape = (416, 416)
        self.input_height = 416
        self.input_width = 416
        self.is_quantized = False
        self.is_model_loaded = False
        self.model_error: Optional[str] = None
        self.runtime_name: str = "None"
        self._lock = threading.Lock()

        # Resolve model path if not given
        if not self.model_path:
            self.model_path = self._discover_model_path()

        self._init_interpreter()

    def _discover_model_path(self) -> str:
        """Finds default model location in edge/models directory."""
        env_path = os.getenv("TFLITE_MODEL_PATH")
        if env_path and os.path.exists(env_path):
            return env_path
        best_path = os.path.join(MODELS_DIR, "best.tflite")
        if os.path.exists(best_path):
            return best_path
        pest_path = os.path.join(MODELS_DIR, "pest_detector.tflite")
        if os.path.exists(pest_path):
            return pest_path
        if os.path.exists(MODELS_DIR):
            for f in os.listdir(MODELS_DIR):
                if f.endswith(".tflite"):
                    return os.path.join(MODELS_DIR, f)
        return best_path

    def _init_interpreter(self):
        """Attempts to load tflite_runtime, ai_edge_litert, or tensorflow.lite."""
        if not self.model_path or not os.path.exists(self.model_path):
            self.is_model_loaded = False
            self.model_error = f"Model file not found at '{self.model_path}'"
            logger.warning(f"[TfliteRunner] {self.model_error}")
            return

        # Try to load class names from model metadata if present
        meta = extract_tflite_metadata(self.model_path)
        if meta and "names" in meta:
            try:
                names_dict = meta["names"]
                sorted_keys = sorted([int(k) for k in names_dict.keys()])
                self.labels = [names_dict[str(k)] for k in sorted_keys]
                logger.info(f"[TfliteRunner] Loaded {len(self.labels)} class labels from model metadata.")
            except Exception as e:
                logger.debug(f"[TfliteRunner] Could not parse labels from metadata: {e}")

        last_err = None

        # 1. Try tflite_runtime (preferred on Raspberry Pi / Linux)
        try:
            import tflite_runtime.interpreter as tflite
            self.interpreter = tflite.Interpreter(model_path=self.model_path)
            self.runtime_name = "tflite_runtime"
            self._setup_details()
            self.is_model_loaded = True
            self.model_error = None
            logger.info(f"[TfliteRunner] Initialized via tflite_runtime from {self.model_path}")
            return
        except ImportError:
            pass
        except Exception as e:
            last_err = f"tflite_runtime error: {e}"
            logger.warning(f"[TfliteRunner] {last_err}")

        # 2. Try ai_edge_litert (official Google LiteRT for Python 3.11-3.13 on Windows/Linux)
        try:
            from ai_edge_litert.interpreter import Interpreter
            self.interpreter = Interpreter(model_path=self.model_path)
            self.runtime_name = "ai_edge_litert"
            self._setup_details()
            self.is_model_loaded = True
            self.model_error = None
            logger.info(f"[TfliteRunner] Initialized via ai_edge_litert from {self.model_path}")
            return
        except ImportError:
            pass
        except Exception as e:
            last_err = f"ai_edge_litert error: {e}"
            logger.warning(f"[TfliteRunner] {last_err}")

        # 3. Try full tensorflow.lite
        try:
            import tensorflow as tf
            self.interpreter = tf.lite.Interpreter(model_path=self.model_path)
            self.runtime_name = "tensorflow.lite"
            self._setup_details()
            self.is_model_loaded = True
            self.model_error = None
            logger.info(f"[TfliteRunner] Initialized via tensorflow.lite from {self.model_path}")
            return
        except ImportError:
            pass
        except Exception as e:
            last_err = f"tensorflow.lite error: {e}"
            logger.warning(f"[TfliteRunner] {last_err}")

        self.is_model_loaded = False
        self.model_error = last_err or "No supported TFLite runtime found (install tflite-runtime or ai-edge-litert)"
        logger.warning(f"[TfliteRunner] {self.model_error}")

    def _setup_details(self):
        """Extracts input and output tensor dimensions from interpreter."""
        if not self.interpreter:
            return
        self.interpreter.allocate_tensors()
        self._input_details = self.interpreter.get_input_details()
        self._output_details = self.interpreter.get_output_details()
        in_shape = self._input_details[0]["shape"]
        # Determine tensor layout (NCHW vs NHWC)
        if len(in_shape) == 4 and in_shape[1] == 3:
            self.is_nchw = True
            self.input_height = int(in_shape[2])
            self.input_width = int(in_shape[3])
        elif len(in_shape) == 4:
            self.is_nchw = False
            self.input_height = int(in_shape[1])
            self.input_width = int(in_shape[2])
        else:
            self.is_nchw = False
            self.input_height = 416
            self.input_width = 416
        self.input_shape = (self.input_height, self.input_width)
        self.is_quantized = (self._input_details[0]["dtype"] == np.uint8)
        logger.info(
            f"[TfliteRunner] Input shape: {self.input_shape}, NCHW: {self.is_nchw}, Quantized: {self.is_quantized}"
        )

    def set_parameters(
        self,
        conf_threshold: Optional[float] = None,
        iou_threshold: Optional[float] = None,
        class_filter_mode: Optional[str] = None
    ):
        """Updates runtime inference thresholds and class filter mode."""
        with self._lock:
            if conf_threshold is not None:
                self.conf_threshold = max(0.05, min(0.99, float(conf_threshold)))
            if iou_threshold is not None:
                self.iou_threshold = max(0.05, min(0.99, float(iou_threshold)))
            if class_filter_mode in ["strict_12", "full_102"]:
                self.class_filter_mode = class_filter_mode
            logger.info(
                f"[TfliteRunner] Updated params: conf={self.conf_threshold}, "
                f"iou={self.iou_threshold}, mode={self.class_filter_mode}"
            )

    def preprocess(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Resizes, normalizes, and expands dimensions for model inference (supporting NCHW and NHWC)."""
        resized = cv2.resize(frame_bgr, (self.input_width, self.input_height))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        if not self.is_quantized:
            normalized = rgb.astype(np.float32) / 255.0
        else:
            normalized = rgb

        if self.is_nchw:
            chw = np.transpose(normalized, (2, 0, 1))
            return np.expand_dims(chw, axis=0)
        else:
            return np.expand_dims(normalized, axis=0)

    def detect(
        self,
        frame_bgr: np.ndarray,
        crop_type: str = "corn",
        conf_threshold: Optional[float] = None
    ) -> List[DetectionBox]:
        """Runs inference, filters target crop pests, and applies NMS."""
        if not self.is_model_loaded or not self.interpreter:
            return []

        effective_conf = float(conf_threshold) if conf_threshold is not None else self.conf_threshold

        with self._lock:
            try:
                orig_h, orig_w = frame_bgr.shape[:2]
                input_data = self.preprocess(frame_bgr)

                self.interpreter.set_tensor(self._input_details[0]["index"], input_data)
                self.interpreter.invoke()

                raw_output = np.array(self.interpreter.get_tensor(self._output_details[0]["index"]), copy=True)

                # 1. Check for YOLO output shape: [1, 4 + classes, anchors] or [1, anchors, 4 + classes]
                if len(raw_output.shape) == 3:
                    squeezed = np.squeeze(raw_output)
                    # If shape is [channels, anchors] where channels < anchors, transpose to [anchors, channels]
                    if squeezed.shape[0] < squeezed.shape[1]:
                        predictions = squeezed.T
                    else:
                        predictions = squeezed

                    if predictions.shape[1] > 4:
                        boxes = []
                        scores = []
                        class_ids = []
                        labels_out = []

                        for pred in predictions:
                            class_scores = pred[4:]
                            max_idx = int(np.argmax(class_scores))
                            confidence = float(class_scores[max_idx])

                            if confidence < effective_conf:
                                continue

                            # Class filtering mode
                            if self.class_filter_mode == "strict_12":
                                if max_idx in ALLOWED_STRICT_12:
                                    label_name = ALLOWED_STRICT_12[max_idx]
                                elif max_idx in TARGET_PEST_ALIASES:
                                    label_name = TARGET_PEST_ALIASES[max_idx]
                                else:
                                    continue
                            else:
                                # Full 102 mode (default)
                                if 0 <= max_idx < len(self.labels):
                                    label_name = self.labels[max_idx]
                                elif max_idx in ALLOWED_STRICT_12:
                                    label_name = ALLOWED_STRICT_12[max_idx]
                                else:
                                    label_name = f"Pest {max_idx}"

                            cx, cy, w, h = pred[0:4]
                            # Handle normalized (0..1) vs pixel-space (0..imgsz) coordinates
                            if cx > 1.5 or cy > 1.5 or w > 1.5 or h > 1.5:
                                cx /= self.input_width
                                cy /= self.input_height
                                w /= self.input_width
                                h /= self.input_height

                            x1 = int((cx - w / 2) * orig_w)
                            y1 = int((cy - h / 2) * orig_h)
                            box_w = int(w * orig_w)
                            box_h = int(h * orig_h)

                            # Clamp coordinates within frame boundaries
                            x1 = max(0, min(orig_w - 5, x1))
                            y1 = max(0, min(orig_h - 5, y1))
                            box_w = max(5, min(orig_w - x1, box_w))
                            box_h = max(5, min(orig_h - y1, box_h))

                            boxes.append([x1, y1, box_w, box_h])
                            scores.append(confidence)
                            class_ids.append(max_idx)
                            labels_out.append(label_name)

                        if len(boxes) == 0:
                            return []

                        # Non-Maximum Suppression to remove redundant boxes
                        indices = cv2.dnn.NMSBoxes(boxes, scores, effective_conf, self.iou_threshold)

                        detected_pests: List[DetectionBox] = []
                        if len(indices) > 0:
                            for idx in np.array(indices).flatten():
                                detected_pests.append(DetectionBox(
                                    label=labels_out[idx].title(),
                                    confidence=round(scores[idx], 4),
                                    x=boxes[idx][0],
                                    y=boxes[idx][1],
                                    width=boxes[idx][2],
                                    height=boxes[idx][3],
                                    pest_key=labels_out[idx].lower().replace(" ", "_")
                                ))
                        return detected_pests

                # 2. Check for SSD MobileNet format (boxes, classes, scores)
                if len(self._output_details) >= 3:
                    raw_boxes = np.array(self.interpreter.get_tensor(self._output_details[0]["index"])[0], copy=True)
                    raw_classes = np.array(self.interpreter.get_tensor(self._output_details[1]["index"])[0], copy=True)
                    raw_scores = np.array(self.interpreter.get_tensor(self._output_details[2]["index"])[0], copy=True)

                    boxes_ssd = []
                    for i in range(len(raw_scores)):
                        score = float(raw_scores[i])
                        if score < effective_conf:
                            continue
                        class_idx = int(raw_classes[i])

                        if self.class_filter_mode == "strict_12":
                            if class_idx in ALLOWED_STRICT_12:
                                label = ALLOWED_STRICT_12[class_idx]
                            elif class_idx in TARGET_PEST_ALIASES:
                                label = TARGET_PEST_ALIASES[class_idx]
                            else:
                                continue
                        else:
                            label = self.labels[class_idx] if 0 <= class_idx < len(self.labels) else f"Pest {class_idx}"

                        ymin, xmin, ymax, xmax = raw_boxes[i]
                        bx = int(xmin * orig_w)
                        by = int(ymin * orig_h)
                        bw = int((xmax - xmin) * orig_w)
                        bh = int((ymax - ymin) * orig_h)

                        boxes_ssd.append(DetectionBox(
                            label=label.title(),
                            confidence=score,
                            x=bx,
                            y=by,
                            width=bw,
                            height=bh,
                            pest_key=label.lower().replace(" ", "_")
                        ))
                    return boxes_ssd

            except Exception as e:
                logger.error(f"[TfliteRunner] Inference error: {e}")

            return []


# Direct alias for plan.md.txt naming compatibility
PestDetector = TfliteRunner


class SimulatedDetector(BasePestDetector):
    """
    High-fidelity simulated AI detector supporting the 102-pest taxonomy.
    Maps realistic pests based on selected host crop.
    Used for unit testing and offline development.
    """

    def __init__(self):
        self._enabled = True
        self._force_pest: Optional[str] = None
        self._force_count: int = 1

        self.crop_pest_map = {
            "rice": [
                "asiatic_rice_borer",
                "yellow_rice_borer",
                "brown_plant_hopper",
                "rice_leaf_roller",
                "rice_gall_midge",
                "rice_leafhopper"
            ],
            "corn": [
                "corn_borer",
                "army_worm",
                "aphids",
                "black_cutworm",
                "wireworm"
            ],
            "mungbean": [
                "legume_blister_beetle",
                "aphids",
                "thrips",
                "white_margined_moth"
            ],
            "squash": [
                "dacus_dorsalis",
                "trialeurodes_vaporariorum",
                "red_spider",
                "thrips"
            ],
            "eggplant": [
                "flea_beetle",
                "red_spider",
                "polyphagotars_onemus_latus",
                "scirtothrips_dorsalis_hood"
            ]
        }
        logger.info("[VisionDetector] Initialized SimulatedDetector.")

    def set_simulation_state(self, enabled: bool = True, pest: Optional[str] = None, count: int = 1):
        self._enabled = enabled
        self._force_pest = pest
        self._force_count = count

    def detect(self, frame_bgr: np.ndarray, crop_type: str = "corn") -> List[DetectionBox]:
        if not self._enabled:
            return []

        h, w = frame_bgr.shape[:2]
        crop_clean = crop_type.lower().strip()
        available_pests = self.crop_pest_map.get(crop_clean, ["corn_borer", "asiatic_rice_borer"])

        if self._force_pest:
            target_key = self._force_pest
        else:
            idx = int(time.time() / 15.0) % len(available_pests)
            target_key = available_pests[idx]

        count = self._force_count
        label = target_key.replace("_", " ").title()

        results: List[DetectionBox] = []
        seed = int(time.time() / 4.0)
        rng = random.Random(seed)

        for i in range(count):
            conf = round(rng.uniform(0.74, 0.95), 2)
            bw = int(w * rng.uniform(0.12, 0.22))
            bh = int(h * rng.uniform(0.12, 0.22))
            bx = int(w * 0.2 + (i * bw * 1.2) + rng.uniform(-15, 15))
            by = int(h * 0.3 + rng.uniform(-20, 20))

            bx = max(10, min(w - bw - 10, bx))
            by = max(10, min(h - bh - 10, by))

            results.append(DetectionBox(
                label=label,
                confidence=conf,
                x=bx,
                y=by,
                width=bw,
                height=bh,
                pest_key=target_key
            ))

        return results


class EdgeImpulseRunner(BasePestDetector):
    """Runs compiled Edge Impulse Linux .eim binaries."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._runner = None
        self._init_runner()

    def _init_runner(self):
        try:
            from edge_impulse_linux.image import ImageImpulseRunner
            self._runner = ImageImpulseRunner(self.model_path)
            model_info = self._runner.init()
            logger.info(f"[VisionDetector] Edge Impulse model loaded: {model_info['project']['name']}")
        except Exception as e:
            logger.warning(f"[VisionDetector] Could not load Edge Impulse runner: {e}")
            self._runner = None

    def detect(self, frame_bgr: np.ndarray, crop_type: str = "corn") -> List[DetectionBox]:
        if self._runner is None:
            return []

        try:
            features, cropped = self._runner.get_features_from_image(frame_bgr)
            res = self._runner.classify(features)

            boxes = []
            if "bounding_boxes" in res.get("result", {}):
                for bb in res["result"]["bounding_boxes"]:
                    boxes.append(DetectionBox(
                        label=bb["label"],
                        confidence=bb["value"],
                        x=bb["x"],
                        y=bb["y"],
                        width=bb["width"],
                        height=bb["height"]
                    ))
            return boxes
        except Exception as e:
            logger.error(f"[VisionDetector] Edge Impulse classification error: {e}")
            return []


def get_detector(model_path: Optional[str] = None) -> TfliteRunner:
    """
    Factory creating optimal TFLite YOLO detector.
    Does NOT fall back to simulation if model is missing or fails.
    """
    # 1. Explicit model path or environment variable
    tflite_env = os.getenv("TFLITE_MODEL_PATH")
    if tflite_env and os.path.exists(tflite_env):
        return TfliteRunner(model_path=tflite_env)

    if model_path:
        return TfliteRunner(model_path=model_path)

    # 2. Check for best.tflite or pest_detector.tflite
    best_path = os.path.join(MODELS_DIR, "best.tflite")
    if os.path.exists(best_path):
        return TfliteRunner(model_path=best_path)

    pest_path = os.path.join(MODELS_DIR, "pest_detector.tflite")
    if os.path.exists(pest_path):
        return TfliteRunner(model_path=pest_path)

    if os.path.exists(MODELS_DIR):
        for f in os.listdir(MODELS_DIR):
            if f.endswith(".tflite"):
                return TfliteRunner(model_path=os.path.join(MODELS_DIR, f))

    # Return TfliteRunner with default path (marks is_model_loaded=False)
    return TfliteRunner(model_path=best_path)


def annotate_frame(
    frame_bgr: np.ndarray,
    detections: List[DetectionBox],
    crop_name: str = "Corn",
    health_status: str = "Healthy / Pest-Free",
    model_status: str = "Online",
    soil_status: Optional[str] = None
) -> np.ndarray:
    """
    Renders high-contrast bounding boxes, pest badges, and telemetry overlays on frame.
    """
    annotated = frame_bgr.copy()
    h, w = annotated.shape[:2]

    # Draw detection bounding boxes
    for idx, det in enumerate(detections):
        color = BOX_COLORS[idx % len(BOX_COLORS)]
        x, y, bw, bh = det.x, det.y, det.width, det.height

        # Bounding Box rectangle
        cv2.rectangle(annotated, (x, y), (x + bw, y + bh), color, 2)

        # Label tag with background pill
        label_text = f"{det.label} ({int(det.confidence * 100)}%)"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.55
        thickness = 1
        (txt_w, txt_h), baseline = cv2.getTextSize(label_text, font, font_scale, thickness)

        pill_y1 = max(0, y - txt_h - 10)
        pill_y2 = y
        cv2.rectangle(annotated, (x, pill_y1), (x + txt_w + 12, pill_y2), color, -1)
        cv2.putText(
            annotated,
            label_text,
            (x + 6, pill_y2 - 6),
            font,
            font_scale,
            (0, 0, 0),
            thickness,
            cv2.LINE_AA
        )

    # Top overlay bar for status
    bar_height = 36
    overlay = annotated.copy()
    cv2.rectangle(overlay, (0, 0), (w, bar_height), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, annotated, 0.25, 0, annotated)

    status_str = f"Crop: {crop_name} | Pests: {len(detections)} | Health: {health_status} | Model: {model_status}"
    cv2.putText(
        annotated,
        status_str,
        (12, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1,
        cv2.LINE_AA
    )

    return annotated
