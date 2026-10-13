"""
AgriSentinel - Agricultural Knowledge Base Loader & Decision Engine

Loads multi-crop pesticide and infestation data from config/knowledge_base.yaml (or JSON fallback).
Provides:
- Supported crops catalog & metadata
- Infestation level calculation based on pest count thresholds
- Integrated Plant Health evaluation (combining pest pressure & soil moisture status)
- Two-Tier Confidence & Uncertainty filter:
    * High Confidence (>= 70%): Full chemical & organic recommendations, dosage, and safety precautions
    * Borderline / Uncertain (40% - 69%): Amber caution flag with recommended visual verification before spraying
    * Low (< 40%): Filtered out as unreliable false positive
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("AgriSentinel-KnowledgeBase")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
YAML_PATH = os.path.join(CONFIG_DIR, "knowledge_base.yaml")
JSON_PATH = os.path.join(CONFIG_DIR, "knowledge_base.json")


class KnowledgeBase:
    """Agricultural intelligence engine managing crop pests and recommendations."""

    def __init__(self, yaml_path: str = YAML_PATH, json_path: str = JSON_PATH):
        self.yaml_path = yaml_path
        self.json_path = json_path
        self.data: Dict[str, Any] = {}
        self.reload()

    def reload(self):
        """Loads knowledge base from YAML, falling back to JSON if PyYAML is unavailable."""
        loaded = False

        if os.path.exists(self.yaml_path):
            try:
                import yaml
                with open(self.yaml_path, "r", encoding="utf-8") as f:
                    self.data = yaml.safe_load(f) or {}
                loaded = True
                logger.info(f"[KnowledgeBase] Successfully loaded knowledge base from {self.yaml_path}")
            except ImportError:
                logger.debug("[KnowledgeBase] PyYAML not installed, checking for JSON fallback.")
            except Exception as e:
                logger.error(f"[KnowledgeBase] Failed loading YAML: {e}")

        if not loaded and os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                loaded = True
                logger.info(f"[KnowledgeBase] Successfully loaded knowledge base from {self.json_path}")
            except Exception as e:
                logger.error(f"[KnowledgeBase] Failed loading JSON: {e}")

        if not loaded:
            logger.warning("[KnowledgeBase] No knowledge base file found. Initializing built-in minimal fallback.")
            self.data = self._get_builtin_fallback()

        # Cache crops
        self.crops = self.data.get("crops", {})
        self.conf_high = float(self.data.get("system", {}).get("confidence_threshold_high", 0.70))
        self.conf_uncertain = float(self.data.get("system", {}).get("confidence_threshold_uncertain", 0.40))

    def get_supported_crops(self) -> List[Dict[str, Any]]:
        """Returns list of supported crops with key, display name, and pest keys."""
        results = []
        for key, details in self.crops.items():
            results.append({
                "key": key,
                "name": details.get("name", key.capitalize()),
                "scientific_name": details.get("scientific_name", ""),
                "description": details.get("description", ""),
                "pests": [
                    {
                        "key": p_key,
                        "common_name": p_data.get("common_name", p_key),
                        "scientific_name": p_data.get("scientific_name", "")
                    }
                    for p_key, p_data in details.get("pests", {}).items()
                ]
            })
        return results

    def get_crop(self, crop_key: str) -> Optional[Dict[str, Any]]:
        """Returns crop details by key."""
        return self.crops.get(crop_key.lower().strip())

    def get_pest(self, crop_key: str, pest_key: str) -> Optional[Dict[str, Any]]:
        """Returns pest details for a given crop."""
        crop = self.get_crop(crop_key)
        if not crop:
            return None
        pests = crop.get("pests", {})
        # Exact match or normalized slug match
        norm = pest_key.lower().strip().replace(" ", "_").replace("-", "_")
        if norm in pests:
            return pests[norm]
        for k, v in pests.items():
            if norm in k or k in norm or norm in v.get("common_name", "").lower():
                return v
        return None

    def calculate_infestation_level(self, crop_key: str, pest_key: str, count: int) -> str:
        """
        Calculates infestation rating ('None', 'Low', 'Moderate', 'Severe')
        based on defined thresholds in the knowledge base.
        """
        if count <= 0:
            return "None"

        pest = self.get_pest(crop_key, pest_key)
        if not pest:
            # General default
            if count <= 2:
                return "Low"
            elif count <= 5:
                return "Moderate"
            return "Severe"

        thresholds = pest.get("infestation_thresholds", {})
        low_max = thresholds.get("low", [1, 2])[-1]
        mod_max = thresholds.get("moderate", [3, 5])[-1]
        severe_min = thresholds.get("severe", 6)

        if count <= low_max:
            return "Low"
        elif count <= mod_max:
            return "Moderate"
        else:
            return "Severe"

    def evaluate_plant_health(
        self,
        pest_count: int,
        infestation_level: str,
        soil_status: str
    ) -> str:
        """
        Derives integrated plant health condition combining pest pressure and soil hydration.
        """
        soil_status_clean = soil_status.capitalize()

        if pest_count == 0 or infestation_level == "None":
            if soil_status_clean == "Dry":
                return "Moisture Stress (Drought Risk)"
            elif soil_status_clean == "Waterlogged":
                return "Excess Moisture (Fungal / Root Rot Risk)"
            return "Healthy / Pest-Free"

        if infestation_level == "Low":
            if soil_status_clean in ("Dry", "Waterlogged"):
                return f"Dual Stress (Low Infestation + {soil_status_clean} Soil)"
            return "Mild Pest Stress (Early Stage)"

        if infestation_level == "Moderate":
            if soil_status_clean in ("Dry", "Waterlogged"):
                return f"Elevated Stress (Moderate Pests + {soil_status_clean} Soil)"
            return "Under Moderate Pest Pressure"

        # Severe
        return "Severe Infestation (Critical Damage Risk)"

    def get_recommendation(
        self,
        crop_key: str,
        pest_name: str,
        confidence: float,
        pest_count: int = 1,
        soil_status: str = "Optimal"
    ) -> Dict[str, Any]:
        """
        Queries recommendation with Two-Tier Confidence & Uncertainty enforcement:
        - confidence >= 0.70: Full Confirmed Recommendation
        - 0.40 <= confidence < 0.70: Uncertain Borderline Recommendation with Amber Warning
        - confidence < 0.40: Low Confidence Ignored / Rejected
        """
        crop_data = self.get_crop(crop_key)
        crop_display = crop_data.get("name", crop_key.capitalize()) if crop_data else crop_key.capitalize()

        if confidence < self.conf_uncertain:
            return {
                "status": "IGNORED_LOW_CONFIDENCE",
                "is_uncertain": True,
                "confidence": confidence,
                "crop_type": crop_key,
                "detected_pest": "Uncertain / Noise",
                "pest_count": 0,
                "infestation_level": "None",
                "plant_health_status": "Indeterminate (Low Confidence)",
                "recommended_pesticide": None,
                "organic_alternative": None,
                "dosage_instruction": None,
                "safety_precautions": "Detection confidence too low (< 40%). Chemical application strictly not recommended.",
            }

        is_uncertain = confidence < self.conf_high
        status = "UNCERTAIN" if is_uncertain else "CONFIRMED"

        pest_data = self.get_pest(crop_key, pest_name)
        if not pest_data:
            common_name = pest_name.replace("_", " ").capitalize()
            sci_name = ""
            recs = {}
            safety = "Consult local agricultural extension officer for uncataloged species."
        else:
            common_name = pest_data.get("common_name", pest_name)
            sci_name = pest_data.get("scientific_name", "")
            recs = pest_data.get("recommendations", {})
            safety = recs.get("safety_precautions", "Wear protective gloves, mask, and clothing.")

        chem = recs.get("chemical", {})
        org = recs.get("organic_biocontrol", {})

        infestation = self.calculate_infestation_level(crop_key, pest_name, pest_count)
        health = self.evaluate_plant_health(pest_count, infestation, soil_status)

        chem_str = chem.get("product_name", "Appropriate target insecticide pending field verification")
        org_str = org.get("product_name", "Neem-based organic repellent spray")
        dosage = chem.get("dosage", "")
        if chem.get("timing"):
            dosage += f" | Timing: {chem.get('timing')}"
        if chem.get("phi_days"):
            dosage += f" | PHI: {chem.get('phi_days')} days"

        if is_uncertain:
            chem_str = f"[VERIFY FIRST] Candidate match: {chem_str}"
            safety = (
                f"UNCERTAIN DETECTION ({confidence * 100:.1f}% confidence). "
                f"Verify pest presence visually before chemical application. {safety}"
            )

        return {
            "status": status,
            "is_uncertain": is_uncertain,
            "confidence": round(confidence, 3),
            "crop_type": crop_key,
            "crop_name": crop_display,
            "detected_pest": common_name,
            "scientific_name": sci_name,
            "pest_count": pest_count,
            "infestation_level": infestation,
            "plant_health_status": health,
            "recommended_pesticide": chem_str,
            "organic_alternative": org_str,
            "dosage_instruction": dosage,
            "safety_precautions": safety,
        }

    def _get_builtin_fallback(self) -> Dict[str, Any]:
        """Provides hardcoded fallback catalog if config files are missing."""
        return {
            "system": {"confidence_threshold_high": 0.70, "confidence_threshold_uncertain": 0.40},
            "crops": {
                "corn": {
                    "name": "Corn / Maize",
                    "pests": {
                        "fall_armyworm": {
                            "common_name": "Fall Armyworm",
                            "infestation_thresholds": {"low": [1, 2], "moderate": [3, 5], "severe": 6},
                            "recommendations": {
                                "chemical": {"product_name": "Chlorantraniliprole 18.5% SC", "dosage": "0.4 ml/L water", "phi_days": 14},
                                "organic_biocontrol": {"product_name": "Bacillus thuringiensis (Bt)", "dosage": "2 g/L water"},
                                "safety_precautions": "Wear certified respirator and gloves."
                            }
                        }
                    }
                }
            }
        }


# Global singleton instance
knowledge_base = KnowledgeBase()

