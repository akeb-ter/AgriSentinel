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


def load_3pest_labels() -> List[str]:
    """Loads 3-pest class labels for YOLOv8n Fast Scout."""
    path = os.path.join(CONFIG_DIR, "yolov8n_aphid_fruitfly_scale_labels.txt")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                res = []
                for line in f:
                    line = line.strip()
                    if ":" in line:
                        res.append(line.split(":", 1)[1].strip())
                    elif line:
                        res.append(line)
                if len(res) >= 3:
                    return res[:3]
        except Exception as e:
            logger.warning(f"Failed loading yolov8n_aphid_fruitfly_scale_labels.txt: {e}")
    return ["aphid", "fruit fly", "scale insect"]


def load_cereal_labels() -> Dict[int, Dict[str, Any]]:
    """Loads CerealPestAID labels and filter metadata (26 classes)."""
    path_json = os.path.join(CONFIG_DIR, "cerealpestaid_croppests_filtered.json")
    labels: Dict[int, Dict[str, Any]] = {}
    if os.path.exists(path_json):
        try:
            with open(path_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.get("classes", {}).items():
                    idx = int(k)
                    labels[idx] = {
                        "name": v.get("name", f"Class {idx}"),
                        "is_crop_pest": v.get("is_crop_pest", True),
                        "type": v.get("type", "pest")
                    }
                return labels
        except Exception as e:
            logger.warning(f"Failed loading cerealpestaid_croppests_filtered.json: {e}")

    for i in range(26):
        labels[i] = {
            "name": f"Cereal Pest {i}",
            "is_crop_pest": (i not in [14, 15, 19]),
            "type": "predator" if i == 19 else ("non_pest" if i in [14, 15] else "pest")
        }
    return labels


def load_quarrying_labels() -> Dict[int, Dict[str, str]]:
    """Loads Quarrying 2,037 species bilingual labels."""
    path = os.path.join(CONFIG_DIR, "quarrying_all_2037_labels_bilingual.txt")
    labels: Dict[int, Dict[str, str]] = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 3:
                        idx = int(parts[0])
                        tax = parts[1]
                        sci = parts[2]
                        labels[idx] = {"scientific": sci, "taxonomy": tax}
            if len(labels) > 0:
                return labels
        except Exception as e:
            logger.warning(f"Failed loading quarrying labels: {e}")
    return labels


BENEFICIAL_TAXA_KEYWORDS = [
    "odonata", "mantodea", "neuroptera", "araneae", "coccinellidae",
    "ladybird", "ladybug", "lacewing", "mantis", "spider", "hoverfly",
    "predator", "predators", "chrysopidae", "syrphidae", "蜻蜓", "螳螂", "草蛉", "蜘蛛", "瓢虫"
]

MODEL_PROFILES: Dict[str, Dict[str, Any]] = {
    "comprehensive_102": {
        "id": "comprehensive_102",
        "name": "Comprehensive 102 Pests (YOLO11s)",
        "file": "ip102_yolo11s_640x640.tflite",
        "fallback_file": "best.tflite",
        "type": "yolo",
        "input_shape": (640, 640),
        "total_classes": 102,
        "description": "Full agricultural crop pest catalog (102 species across 8 crop systems)"
    },
    "fast_scout_3pests": {
        "id": "fast_scout_3pests",
        "name": "Fast Edge Scout (YOLOv8n)",
        "file": "yolov8n_aphid_fruitfly_scale.tflite",
        "fallback_file": "yolov8n_aphid_fruitfly_scale.tflite",
        "type": "yolo",
        "input_shape": (640, 640),
        "total_classes": 3,
        "description": "High-speed live streaming scout for aphids, fruit flies, and scale insects (10-12 FPS)"
    },
    "cereal_diagnostic": {
        "id": "cereal_diagnostic",
        "name": "Close-Up Cereal Diagnostic (MobileNetV3)",
        "file": "cerealpestaid_mobilenetv3.tflite",
        "fallback_file": "cerealpestaid_mobilenetv3.tflite",
        "type": "classifier",
        "input_shape": (224, 224),
        "total_classes": 26,
        "description": "Macro leaf diagnostic with beneficial ladybug/lacewing predator guard"
    },
    "species_encyclopedia": {
        "id": "species_encyclopedia",
        "name": "Species Encyclopedia (Quarrying ONNX)",
        "file": "quarrying_insect_identifier_224x224.onnx",
        "fallback_file": "quarrying_insect_identifier_224x224.onnx",
        "type": "onnx_classifier",
        "input_shape": (224, 224),
        "total_classes": 2037,
        "description": "Deep taxonomic identification across 2,037 wild insect and arthropod species"
    }
}


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
    """Represents a single detected pest or beneficial insect instance."""

    def __init__(
        self,
        label: str,
        confidence: float,
        x: int,
        y: int,
        width: int,
        height: int,
        pest_key: Optional[str] = None,
        is_beneficial: bool = False,
        taxonomy: Optional[str] = None
    ):
        self.label = label
        self.confidence = float(confidence)
        self.x = max(0, int(x))
        self.y = max(0, int(y))
        self.width = max(10, int(width))
        self.height = max(10, int(height))
        self.pest_key = pest_key or label.lower().strip().replace(" ", "_").replace("-", "_")
        self.is_beneficial = bool(is_beneficial)
        self.taxonomy = taxonomy

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "pest_key": self.pest_key,
            "confidence": round(self.confidence, 3),
            "is_beneficial": self.is_beneficial,
            "taxonomy": self.taxonomy,
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
        model_profile: str = "comprehensive_102",
        conf_threshold: float = float(os.getenv("TFLITE_CONF_THRESHOLD", "0.25")),
        iou_threshold: float = 0.45,
        class_filter_mode: str = os.getenv("TFLITE_FILTER_MODE", "full_102"),
        labels: Optional[List[str]] = None
    ):
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.class_filter_mode = class_filter_mode  # "strict_12" or "full_102"
        self.active_profile = model_profile
        self.labels = labels or list(PEST_LABELS_102)

        self.model_path = model_path
        self.interpreter = None
        self.onnx_session = None
        self._interpreters: Dict[str, Any] = {}
        self._onnx_sessions: Dict[str, Any] = {}
        self._input_details = None
        self._output_details = None
        self.input_shape = (640, 640)
        self.input_height = 640
        self.input_width = 640
        self.is_nchw = True
        self.is_quantized = False
        self.is_model_loaded = False
        self.model_error: Optional[str] = None
        self.runtime_name: str = "None"
        self._lock = threading.Lock()

        # Preload label catalogs
        self.cereal_labels = load_cereal_labels()
        self.quarrying_labels = load_quarrying_labels()

        if self.model_path:
            self._init_explicit_model(self.model_path)
        else:
            self.switch_model(self.active_profile)

    def _create_interpreter(self, path: str):
        """Attempts to create a TFLite interpreter from tflite_runtime, ai_edge_litert, or tensorflow.lite."""
        if not path or not os.path.exists(path):
            return None, f"Model file not found at '{path}'"

        # 1. Try tflite_runtime (preferred on Raspberry Pi / Linux)
        try:
            import tflite_runtime.interpreter as tflite
            interp = tflite.Interpreter(model_path=path)
            return interp, "tflite_runtime"
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[TfliteRunner] tflite_runtime error: {e}")

        # 2. Try ai_edge_litert (official Google LiteRT for Python 3.11-3.13)
        try:
            from ai_edge_litert.interpreter import Interpreter
            interp = Interpreter(model_path=path)
            return interp, "ai_edge_litert"
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[TfliteRunner] ai_edge_litert error: {e}")

        # 3. Try full tensorflow.lite
        try:
            import tensorflow as tf
            interp = tf.lite.Interpreter(model_path=path)
            return interp, "tensorflow.lite"
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[TfliteRunner] tensorflow.lite error: {e}")

        return None, "No supported TFLite runtime found (install tflite-runtime or ai-edge-litert)"

    def _init_explicit_model(self, path: str):
        """Initializes interpreter for a custom explicit model path."""
        interp, rname = self._create_interpreter(path)
        if interp:
            self.interpreter = interp
            self.runtime_name = rname
            self._setup_details()
            self.is_model_loaded = True
            self.model_error = None
            meta = extract_tflite_metadata(path)
            if meta and "names" in meta:
                try:
                    names_dict = meta["names"]
                    sorted_keys = sorted([int(k) for k in names_dict.keys()])
                    self.labels = [names_dict[str(k)] for k in sorted_keys]
                except Exception:
                    pass
            logger.info(f"[TfliteRunner] Initialized explicit model from {path} via {rname}")
        else:
            self.is_model_loaded = False
            self.model_error = rname
            logger.warning(f"[TfliteRunner] {self.model_error}")

    def switch_model(self, profile_key: str) -> bool:
        """
        Switches active vision model to one of the supported MODEL_PROFILES:
        - 'comprehensive_102': YOLO11s (102 Crop Pests)
        - 'fast_scout_3pests': YOLOv8n (Aphid, Fruit Fly, Scale Insect)
        - 'cereal_diagnostic': MobileNetV3 (Close-up leaf diagnostic with predator guard)
        - 'species_encyclopedia': Quarrying ONNX (2,037 wild insect species)
        """
        if profile_key not in MODEL_PROFILES:
            logger.warning(f"[TfliteRunner] Unknown model profile: {profile_key}")
            return False

        with self._lock:
            prof = MODEL_PROFILES[profile_key]
            prof_type = prof.get("type", "yolo")
            filename = prof.get("file", "")
            fallback_name = prof.get("fallback_file", filename)

            target_path = os.path.join(MODELS_DIR, filename)
            if not os.path.exists(target_path):
                target_path = os.path.join(MODELS_DIR, fallback_name)
            if not os.path.exists(target_path):
                # Search models directory for any fallback
                best_path = os.path.join(MODELS_DIR, "best.tflite")
                if os.path.exists(best_path):
                    target_path = best_path
                elif self.model_path and os.path.exists(self.model_path):
                    target_path = self.model_path
                else:
                    self.is_model_loaded = False
                    self.model_error = f"Model file '{filename}' not found in {MODELS_DIR}"
                    logger.warning(f"[TfliteRunner] {self.model_error}")
                    return False

            self.model_path = target_path
            self.active_profile = profile_key

            try:
                if prof_type == "onnx_classifier":
                    if profile_key not in self._onnx_sessions:
                        import onnxruntime as ort
                        sess_opts = ort.SessionOptions()
                        sess_opts.inter_op_num_threads = 2
                        sess_opts.intra_op_num_threads = 2
                        self._onnx_sessions[profile_key] = ort.InferenceSession(
                            target_path,
                            sess_opts,
                            providers=["CPUExecutionProvider"]
                        )
                    self.onnx_session = self._onnx_sessions[profile_key]
                    self.interpreter = None
                    self.runtime_name = "onnxruntime"
                    self.input_shape = prof.get("input_shape", (224, 224))
                    self.input_height, self.input_width = self.input_shape
                    self.is_nchw = True
                    self.is_quantized = False
                    self.labels = [self.quarrying_labels.get(i, {}).get("scientific", f"Species_{i}") for i in range(len(self.quarrying_labels))]
                    self.is_model_loaded = True
                    self.model_error = None
                    logger.info(f"[TfliteRunner] Switched to ONNX profile '{profile_key}' from {target_path}")
                    return True

                else:
                    # TFLite Model
                    if profile_key not in self._interpreters:
                        interp, rname = self._create_interpreter(target_path)
                        if interp is None:
                            self.is_model_loaded = False
                            self.model_error = rname
                            return False
                        self._interpreters[profile_key] = interp
                        self.runtime_name = rname

                    self.interpreter = self._interpreters[profile_key]
                    self.onnx_session = None
                    self._setup_details()

                    if profile_key == "comprehensive_102":
                        meta = extract_tflite_metadata(target_path)
                        if meta and "names" in meta:
                            try:
                                names_dict = meta["names"]
                                sorted_keys = sorted([int(k) for k in names_dict.keys()])
                                self.labels = [names_dict[str(k)] for k in sorted_keys]
                            except Exception:
                                self.labels = list(PEST_LABELS_102)
                        else:
                            self.labels = list(PEST_LABELS_102)

                    elif profile_key == "fast_scout_3pests":
                        self.labels = load_3pest_labels()

                    elif profile_key == "cereal_diagnostic":
                        self.labels = [self.cereal_labels.get(i, {}).get("name", f"Cereal_Pest_{i}") for i in range(len(self.cereal_labels))]

                    self.is_model_loaded = True
                    self.model_error = None
                    logger.info(f"[TfliteRunner] Switched to profile '{profile_key}' ({self.runtime_name}) from {target_path}")
                    return True

            except Exception as e:
                self.is_model_loaded = False
                self.model_error = f"Error switching to profile '{profile_key}': {e}"
                logger.error(f"[TfliteRunner] {self.model_error}")
                return False

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
        class_filter_mode: Optional[str] = None,
        model_profile: Optional[str] = None
    ):
        """Updates runtime inference thresholds, class filter mode, and active model profile."""
        with self._lock:
            if conf_threshold is not None:
                self.conf_threshold = max(0.05, min(0.99, float(conf_threshold)))
            if iou_threshold is not None:
                self.iou_threshold = max(0.05, min(0.99, float(iou_threshold)))
            if class_filter_mode in ["strict_12", "full_102"]:
                self.class_filter_mode = class_filter_mode

        if model_profile and model_profile != self.active_profile:
            self.switch_model(model_profile)

        logger.info(
            f"[TfliteRunner] Updated params: conf={self.conf_threshold}, "
            f"iou={self.iou_threshold}, mode={self.class_filter_mode}, profile={self.active_profile}"
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
        conf_threshold: Optional[float] = None,
        model_profile: Optional[str] = None
    ) -> List[DetectionBox]:
        """Runs inference, filters target crop pests, and applies NMS or classification decoding."""
        if model_profile and model_profile != self.active_profile and model_profile in MODEL_PROFILES:
            self.switch_model(model_profile)

        if not self.is_model_loaded:
            return []

        effective_conf = float(conf_threshold) if conf_threshold is not None else self.conf_threshold
        prof = MODEL_PROFILES.get(self.active_profile, MODEL_PROFILES["comprehensive_102"])
        prof_type = prof.get("type", "yolo")

        with self._lock:
            try:
                orig_h, orig_w = frame_bgr.shape[:2]

                # 1. Species Encyclopedia (Quarrying ONNX 2,037 classes)
                if prof_type == "onnx_classifier" and self.onnx_session:
                    resized = cv2.resize(frame_bgr, (224, 224))
                    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
                    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
                    normalized = ((rgb.astype(np.float32) / 255.0) - mean) / std
                    chw = np.transpose(normalized, (2, 0, 1))
                    input_data = np.expand_dims(chw, axis=0)

                    input_name = self.onnx_session.get_inputs()[0].name
                    raw_out = self.onnx_session.run(None, {input_name: input_data})[0]
                    logits = raw_out[0]
                    exp_l = np.exp(logits - np.max(logits))
                    probs = exp_l / np.sum(exp_l)
                    top_idx = int(np.argmax(probs))
                    top_score = float(probs[top_idx])

                    if top_score < effective_conf:
                        return []

                    entry = self.quarrying_labels.get(top_idx, {"scientific": f"Species {top_idx}", "taxonomy": ""})
                    sci = entry.get("scientific", f"Species {top_idx}")
                    tax = entry.get("taxonomy", "")
                    tax_lower = tax.lower()
                    sci_lower = sci.lower()

                    is_beneficial = any(k in tax_lower for k in BENEFICIAL_TAXA_KEYWORDS) or any(k in sci_lower for k in BENEFICIAL_TAXA_KEYWORDS)
                    label = f"{sci} [Beneficial Predator]" if is_beneficial else sci
                    pest_key = "beneficial_predator" if is_beneficial else sci.lower().replace(" ", "_")

                    return [DetectionBox(
                        label=label,
                        confidence=round(top_score, 4),
                        x=int(orig_w * 0.1),
                        y=int(orig_h * 0.1),
                        width=int(orig_w * 0.8),
                        height=int(orig_h * 0.8),
                        pest_key=pest_key,
                        is_beneficial=is_beneficial,
                        taxonomy=tax
                    )]

                # 2. Cereal Diagnostic Classifier (MobileNetV3 26 classes)
                if prof_type == "classifier" and self.interpreter:
                    resized = cv2.resize(frame_bgr, (224, 224))
                    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                    normalized = rgb.astype(np.float32) / 255.0
                    input_data = np.expand_dims(normalized, axis=0)

                    self.interpreter.set_tensor(self._input_details[0]["index"], input_data)
                    self.interpreter.invoke()
                    raw_out = np.array(self.interpreter.get_tensor(self._output_details[0]["index"]), copy=True)
                    logits = raw_out[0]
                    exp_l = np.exp(logits - np.max(logits))
                    probs = exp_l / np.sum(exp_l)
                    top_idx = int(np.argmax(probs))
                    top_score = float(probs[top_idx])

                    if top_score < effective_conf:
                        return []

                    # Beneficial Predator Guard (Class 19: predators - ladybug, lacewing, hoverfly)
                    if top_idx == 19:
                        return [DetectionBox(
                            label="Beneficial Predator (Ladybug/Lacewing)",
                            confidence=round(top_score, 4),
                            x=int(orig_w * 0.1),
                            y=int(orig_h * 0.1),
                            width=int(orig_w * 0.8),
                            height=int(orig_h * 0.8),
                            pest_key="beneficial_predator",
                            is_beneficial=True,
                            taxonomy="Predator (Coccinellidae/Chrysopidae)"
                        )]

                    # Non-pest herbivores (Class 14) or occasional pest (Class 15) -> suppressed from false alarm
                    if top_idx in [14, 15]:
                        return []

                    # Genuine crop pest
                    entry = self.cereal_labels.get(top_idx, {})
                    label_name = entry.get("name", f"Cereal Pest {top_idx}")
                    return [DetectionBox(
                        label=label_name.title(),
                        confidence=round(top_score, 4),
                        x=int(orig_w * 0.1),
                        y=int(orig_h * 0.1),
                        width=int(orig_w * 0.8),
                        height=int(orig_h * 0.8),
                        pest_key=label_name.lower().replace(" ", "_"),
                        is_beneficial=False
                    )]

                # 3. YOLO Object Detection (Comprehensive 102 or Fast Scout 3-Pests)
                if prof_type == "yolo" and self.interpreter:
                    input_data = self.preprocess(frame_bgr)
                    self.interpreter.set_tensor(self._input_details[0]["index"], input_data)
                    self.interpreter.invoke()

                    raw_output = np.array(self.interpreter.get_tensor(self._output_details[0]["index"]), copy=True)

                    if len(raw_output.shape) == 3:
                        squeezed = np.squeeze(raw_output)
                        if squeezed.shape[0] < squeezed.shape[1]:
                            predictions = squeezed.T
                        else:
                            predictions = squeezed

                        if predictions.shape[1] > 4:
                            boxes = []
                            scores = []
                            class_ids = []
                            labels_out = []

                            is_3pest = (self.active_profile == "fast_scout_3pests")

                            for pred in predictions:
                                class_scores = pred[4:]
                                max_idx = int(np.argmax(class_scores))
                                confidence = float(class_scores[max_idx])

                                if confidence < effective_conf:
                                    continue

                                if is_3pest:
                                    if 0 <= max_idx < len(self.labels):
                                        label_name = self.labels[max_idx]
                                    else:
                                        label_name = f"Pest {max_idx}"
                                else:
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
                                if cx > 1.5 or cy > 1.5 or w > 1.5 or h > 1.5:
                                    cx /= self.input_width
                                    cy /= self.input_height
                                    w /= self.input_width
                                    h /= self.input_height

                                x1 = int((cx - w / 2) * orig_w)
                                y1 = int((cy - h / 2) * orig_h)
                                box_w = int(w * orig_w)
                                box_h = int(h * orig_h)

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
                                        pest_key=labels_out[idx].lower().replace(" ", "_"),
                                        is_beneficial=False
                                    ))
                            return detected_pests

                    # SSD MobileNet format fallback
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
                                pest_key=label.lower().replace(" ", "_"),
                                is_beneficial=False
                            ))
                        return boxes_ssd

            except Exception as e:
                logger.error(f"[TfliteRunner] Inference error ({self.active_profile}): {e}")

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


def get_detector(model_path: Optional[str] = None, model_profile: str = "comprehensive_102") -> TfliteRunner:
    """
    Factory creating optimal AI detector supporting multi-model switching.
    Defaults to 'comprehensive_102'. Does NOT fall back to simulation if model is missing.
    """
    tflite_env = os.getenv("TFLITE_MODEL_PATH")
    if tflite_env and os.path.exists(tflite_env):
        return TfliteRunner(model_path=tflite_env, model_profile=model_profile)

    if model_path:
        return TfliteRunner(model_path=model_path, model_profile=model_profile)

    return TfliteRunner(model_profile=model_profile)


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
    Beneficial natural predators are highlighted with Lime Green badges and [BENEFICIAL] shields.
    """
    annotated = frame_bgr.copy()
    h, w = annotated.shape[:2]

    has_beneficial = any(d.is_beneficial for d in detections)
    has_pests = any(not d.is_beneficial for d in detections)
    if has_beneficial and not has_pests:
        health_status = "Beneficial Predator Active"

    # Draw detection bounding boxes
    for idx, det in enumerate(detections):
        if det.is_beneficial:
            color = (50, 205, 50)  # Lime Green for beneficial predators
            label_text = f"[BENEFICIAL] {det.label} ({int(det.confidence * 100)}%)"
        else:
            color = BOX_COLORS[idx % len(BOX_COLORS)]
            label_text = f"{det.label} ({int(det.confidence * 100)}%)"

        x, y, bw, bh = det.x, det.y, det.width, det.height

        # Bounding Box rectangle
        cv2.rectangle(annotated, (x, y), (x + bw, y + bh), color, 2)

        # Label tag with background pill
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

    status_str = f"Crop: {crop_name} | Detections: {len(detections)} | Health: {health_status} | Model: {model_status}"
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
