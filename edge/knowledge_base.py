"""
AgriSentinel - Agricultural Knowledge Base Loader & Decision Engine

Loads multi-crop pesticide and infestation data from config/knowledge_base.yaml (or JSON fallback).
Provides:
- Supported crops catalog & metadata
- Infestation level calculation based on pest count thresholds
- Integrated Plant Health evaluation (based on pest pressure & infestation severity)
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
CLASSES_102_PATH = os.path.join(CONFIG_DIR, "pest_classes_102.json")


class KnowledgeBase:
    """Agricultural intelligence engine managing crop pests and recommendations."""

    def __init__(self, yaml_path: str = YAML_PATH, json_path: str = JSON_PATH):
        self.yaml_path = yaml_path
        self.json_path = json_path
        self.data: Dict[str, Any] = {}
        self.catalog_102: Dict[str, Dict[str, Any]] = {}
        self._load_102_catalog()
        self.reload()

    def _load_102_catalog(self):
        """Loads the 102-pest IP102 catalog into indexing map."""
        if not os.path.exists(CLASSES_102_PATH):
            return
        try:
            with open(CLASSES_102_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
                for item in raw.get("classes", []):
                    k = item.get("key", "").lower().strip()
                    n = item.get("name", "").lower().strip()
                    if k:
                        self.catalog_102[k] = item
                    if n:
                        self.catalog_102[n] = item
                    if "id" in item:
                        self.catalog_102[str(item["id"])] = item
            logger.info(f"[KnowledgeBase] Loaded {len(raw.get('classes', []))} pest classes from {CLASSES_102_PATH}")
        except Exception as e:
            logger.warning(f"[KnowledgeBase] Could not load 102 pest catalog: {e}")

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
        if not crop_key:
            return None
        return self.crops.get(crop_key.lower().strip())

    def _generate_taxonomic_recommendations(self, common_name: str, scientific_name: str = "") -> Dict[str, Any]:
        """
        Generates sound Integrated Pest Management (IPM) chemical and biocontrol recommendations
        based on the pest's morphological and taxonomic group across the 102 IP102 catalog.
        """
        target = f"{common_name.lower()} {scientific_name.lower()}"

        if any(w in target for w in ["borer", "maggot", "stemfly"]):
            return {
                "chemical": {
                    "product_name": "Chlorantraniliprole 18.5% SC or Flubendiamide 39.35% SC",
                    "active_ingredient": "Chlorantraniliprole / Flubendiamide",
                    "dosage": "0.3 - 0.4 ml/L water",
                    "phi_days": 14,
                    "timing": "Target peak egg-hatch or initial larval instars before tunneling into stems"
                },
                "organic_biocontrol": {
                    "product_name": "Bacillus thuringiensis (Bt subsp. kurstaki) + Trichogramma parasitoids",
                    "dosage": "2.0 g/L Bt spray; release 50,000 parasitoids/ha",
                    "phi_days": 0,
                    "timing": "Release upon adult moth detection"
                },
                "safety_precautions": "Maintain personal protective equipment (gloves, respirator). Do not apply near aquatic environments."
            }

        if any(w in target for w in ["hopper", "planthopper", "leafhopper", "cicadell", "lawana", "salurnis", "erythroneura"]):
            return {
                "chemical": {
                    "product_name": "Triflemezopyrim 10% SC or Pymetrozine 50% WG",
                    "active_ingredient": "Triflemezopyrim / Pymetrozine",
                    "dosage": "0.5 ml/L water (Triflemezopyrim) or 0.6 g/L (Pymetrozine)",
                    "phi_days": 14,
                    "timing": "Direct nozzle spray at the base/lower leaves where hoppers feed"
                },
                "organic_biocontrol": {
                    "product_name": "Beauveria bassiana or Metarhizium anisopliae bio-insecticide",
                    "dosage": "5 g/L spore suspension with mild surfactant",
                    "phi_days": 0,
                    "timing": "Spray in late afternoon to maintain humidity for fungal germination"
                },
                "safety_precautions": "Avoid overuse of synthetic pyrethroids to prevent planthopper resurgence. Wear standard PPE."
            }

        if any(w in target for w in ["caterpillar", "armyworm", "army_worm", "cutworm", "moth", "budworm", "roller", "prodenia", "pieris", "papilio", "leafminer", "limacodidae"]):
            return {
                "chemical": {
                    "product_name": "Emamectin Benzoate 5% SG or Chlorantraniliprole 18.5% SC",
                    "active_ingredient": "Emamectin Benzoate / Diamides",
                    "dosage": "0.4 g/L water (Emamectin) or 0.4 ml/L (Chlorantraniliprole)",
                    "phi_days": 7,
                    "timing": "Spray during dusk or early morning when larvae emerge on foliage"
                },
                "organic_biocontrol": {
                    "product_name": "Bacillus thuringiensis (Bt) + Cold-pressed Neem Oil",
                    "dosage": "2.5 g/L Bt + 3 ml/L Neem oil (10,000 ppm)",
                    "phi_days": 0,
                    "timing": "Apply at first sign of skeletonized leaves or leaf rolling"
                },
                "safety_precautions": "Wear certified respirator and protective clothing. Toxic to silkworms."
            }

        if any(w in target for w in ["aphid", "whitefly", "vaporariorum", "green_bug", "plant_bug", "miridae", "apolygus"]):
            return {
                "chemical": {
                    "product_name": "Imidacloprid 17.8% SL or Acetamiprid 20% SP",
                    "active_ingredient": "Imidacloprid / Acetamiprid",
                    "dosage": "0.5 ml/L water",
                    "phi_days": 14,
                    "timing": "Target colonies under foliage before honeydew/sooty mold develops"
                },
                "organic_biocontrol": {
                    "product_name": "Neem Oil 10,000 ppm + Potassium Soap",
                    "dosage": "3 - 5 ml/L water",
                    "phi_days": 0,
                    "timing": "Apply early morning; ensure thorough contact with leaf undersides"
                },
                "safety_precautions": "Highly toxic to bees. Do NOT spray open flowering blossoms during active foraging hours."
            }

        if any(w in target for w in ["thrips", "odontothrips", "scirtothrips", "phloeothrips"]):
            return {
                "chemical": {
                    "product_name": "Spinetoram 11.7% SC or Fipronil 5% SC",
                    "active_ingredient": "Spinetoram / Fipronil",
                    "dosage": "0.5 ml/L water (Spinetoram) or 1.5 ml/L (Fipronil)",
                    "phi_days": 7,
                    "timing": "Early morning spray targeting terminal buds and leaf curls"
                },
                "organic_biocontrol": {
                    "product_name": "Spinosad organic suspension + Blue Sticky Monitoring Traps",
                    "dosage": "0.4 ml/L water; install 15 blue sticky traps per hectare",
                    "phi_days": 1,
                    "timing": "Deploy traps at crop canopy height"
                },
                "safety_precautions": "Rotate chemical modes of action (IRAC groups) to prevent rapid thrips resistance."
            }

        if any(w in target for w in ["mite", "spider", "colomerus", "brevipoalpus", "polyphagotars", "panonchus", "phyllocoptes", "penthaleus"]):
            return {
                "chemical": {
                    "product_name": "Spiromesifen 22.9% SC or Abamectin 1.8% EC",
                    "active_ingredient": "Spiromesifen / Abamectin",
                    "dosage": "0.8 ml/L water (Spiromesifen) or 0.6 ml/L (Abamectin)",
                    "phi_days": 7,
                    "timing": "High-pressure fine mist spray ensuring total coverage under leaves"
                },
                "organic_biocontrol": {
                    "product_name": "Wettable Sulfur 80% WP or Phytoseiid Predatory Mites",
                    "dosage": "2.0 g/L water wettable sulfur",
                    "phi_days": 0,
                    "timing": "Spray during cool evening hours (avoid temperatures > 32°C)"
                },
                "safety_precautions": "Never mix sulfur with oil-based sprays within a 30-day window to prevent phytotoxicity."
            }

        if any(w in target for w in ["scale", "mealybug", "pseudococcus", "icerya", "unaspis", "ceroplastes", "chrysomphalus", "parlatoria", "nipaecoccus", "aleurocanthus", "viteus"]):
            return {
                "chemical": {
                    "product_name": "Buprofezin 25% SC or Dinotefuran 20% SG",
                    "active_ingredient": "Buprofezin / Dinotefuran",
                    "dosage": "1.5 ml/L water (Buprofezin) or 0.5 g/L (Dinotefuran)",
                    "phi_days": 14,
                    "timing": "Spray during early crawler stage before thick waxy coating forms"
                },
                "organic_biocontrol": {
                    "product_name": "Horticultural Paraffinic Summer Oil + Insecticidal Soap",
                    "dosage": "1.5% oil-soap emulsion drench",
                    "phi_days": 0,
                    "timing": "Direct high volume wash over infested stems and branches"
                },
                "safety_precautions": "Wear eye protection and full face shield when drenching tall canopies."
            }

        if any(w in target for w in ["fly", "midge", "dacus", "bactrocera", "tetradacus", "cerodonta", "dasineura"]):
            return {
                "chemical": {
                    "product_name": "Malathion 50% EC bait spray or Spinosad fruit fly bait",
                    "active_ingredient": "Malathion / Spinosad bait",
                    "dosage": "2 ml/L water mixed with 10 g/L molasses or protein attractant",
                    "phi_days": 7,
                    "timing": "Coarse splash spots on lower canopy leaves early in the morning"
                },
                "organic_biocontrol": {
                    "product_name": "Methyl Eugenol / Cue-lure Pheromone Traps + Yellow Sticky Cards",
                    "dosage": "Install 15 - 20 traps per hectare at canopy level",
                    "phi_days": 0,
                    "timing": "Deploy before fruit initiation to suppress adult fly populations"
                },
                "safety_precautions": "Avoid direct spraying onto developing edible fruits. Wear chemical-resistant gloves."
            }

        if any(w in target for w in ["weevil", "beetle", "flea_beetle", "potosiabre", "sericaorient", "lytta", "rhytidodera", "sternochetus", "oides", "deporaus"]):
            return {
                "chemical": {
                    "product_name": "Lambda-Cyhalothrin 5% EC or Spinosad 45% SC",
                    "active_ingredient": "Lambda-Cyhalothrin / Spinosad",
                    "dosage": "1.0 ml/L water",
                    "phi_days": 7,
                    "timing": "Apply at first appearance of adult foliage chewing damage"
                },
                "organic_biocontrol": {
                    "product_name": "Diatomaceous Earth (DE) perimeter dusting + Azadirachtin spray",
                    "dosage": "Dust base of plants; spray Azadirachtin at 3 ml/L",
                    "phi_days": 0,
                    "timing": "Apply in dry weather condition"
                },
                "safety_precautions": "Keep domestic animals away from treated vegetation for at least 48 hours."
            }

        if any(w in target for w in ["cricket", "grub", "wireworm", "locusto"]):
            return {
                "chemical": {
                    "product_name": "Chlorpyrifos 20% EC or Fipronil 0.3% GR Granules",
                    "active_ingredient": "Chlorpyrifos / Fipronil",
                    "dosage": "2.5 ml/L root soil drench or 15-20 kg/ha incorporated granules",
                    "phi_days": 21,
                    "timing": "Soil application during land preparation or around root crowns"
                },
                "organic_biocontrol": {
                    "product_name": "Entomopathogenic Nematodes (Steinernema carpocapsae) or Metarhizium anisopliae",
                    "dosage": "Apply 1 billion nematodes/ha as root zone drench",
                    "phi_days": 0,
                    "timing": "Drench moist soil during cloudy days or late afternoon"
                },
                "safety_precautions": "Avoid application near natural surface water drains to prevent aquatic organism toxicity."
            }

        # General IPM fallback
        return {
            "chemical": {
                "product_name": "Broad-spectrum contact insecticide (e.g., Lambda-Cyhalothrin 5% EC)",
                "active_ingredient": "Pyrethroid / Contact insecticide",
                "dosage": "1.0 ml per Liter of water",
                "phi_days": 14,
                "timing": "Spot spray infested foliage following field inspection"
            },
            "organic_biocontrol": {
                "product_name": "Cold-pressed Neem Oil 10,000 ppm + Potassium Soap",
                "dosage": "3 - 5 ml per Liter of water",
                "phi_days": 0,
                "timing": "Spray late afternoon on undersides of leaves"
            },
            "safety_precautions": "Wear rubber gloves, protective goggles, and face mask. Confirm species with local agricultural extension officer."
        }

    def _get_fallback_ip102_pest(self, pest_key: str) -> Optional[Dict[str, Any]]:
        """Synthesizes complete pest metadata and IPM recommendations for any 102 IP102 pest."""
        norm = pest_key.lower().strip().replace(" ", "_").replace("-", "_")

        catalog_entry = self.catalog_102.get(norm)
        if not catalog_entry:
            # Search partial or ID
            for k, item in self.catalog_102.items():
                if norm == k or norm in item.get("name", "").lower():
                    catalog_entry = item
                    break

        if catalog_entry:
            common_name = catalog_entry.get("name", pest_key.replace("_", " ").title())
            sci_name = catalog_entry.get("scientific_name", "")
        else:
            common_name = pest_key.replace("_", " ").title()
            sci_name = ""

        recs = self._generate_taxonomic_recommendations(common_name, sci_name)

        return {
            "common_name": common_name,
            "scientific_name": sci_name,
            "infestation_thresholds": {
                "low": [1, 2],
                "moderate": [3, 5],
                "severe": 6
            },
            "recommendations": recs
        }

    def get_pest(self, crop_key: str, pest_key: str) -> Optional[Dict[str, Any]]:
        """
        Returns pest details for a given crop, searching:
        1. Specific crop dictionary
        2. Other crops in the multi-crop catalog
        3. The 102 IP102 pest catalog with intelligent taxonomic IPM recommendations
        """
        norm = pest_key.lower().strip().replace(" ", "_").replace("-", "_")

        # 1. Search specified crop
        crop = self.get_crop(crop_key) if crop_key else None
        if crop:
            pests = crop.get("pests", {})
            if norm in pests:
                return pests[norm]
            for k, v in pests.items():
                if norm in k or k in norm or norm in v.get("common_name", "").lower():
                    return v

        # 2. Search other crops in knowledge base
        for c_key, c_data in self.crops.items():
            if crop_key and c_key == crop_key.lower().strip():
                continue
            pests = c_data.get("pests", {})
            if norm in pests:
                return pests[norm]
            for k, v in pests.items():
                if norm in k or k in norm or norm in v.get("common_name", "").lower():
                    return v

        # 3. Fallback to 102 IP102 catalog
        return self._get_fallback_ip102_pest(norm)

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
        soil_status: Optional[str] = None
    ) -> str:
        """
        Derives plant health condition based on pest pressure and infestation severity.
        (soil_status parameter preserved as optional for backwards compatibility).
        """
        if pest_count == 0 or infestation_level in ("None", "none"):
            return "Healthy / Pest-Free"

        if infestation_level == "Low":
            return "Mild Pest Stress"

        if infestation_level == "Moderate":
            return "Under Moderate Pest Pressure"

        # Severe
        return "Severe Infestation (Critical Damage Risk)"

    def get_recommendation(
        self,
        crop_key: str,
        pest_name: str,
        confidence: float,
        pest_count: int = 1,
        soil_status: Optional[str] = None
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

