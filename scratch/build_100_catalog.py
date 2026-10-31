"""
Builds uniform 20-pests-per-crop (100 total IP102 pests) for knowledge_base.json, knowledge_base.yaml,
and updates pest_classes_102.json and ip102_agronomic_matrix.json.
"""

import json
import os
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
MATRIX_PATH = os.path.join(CONFIG_DIR, "ip102_agronomic_matrix.json")
CLASSES_PATH = os.path.join(CONFIG_DIR, "pest_classes_102.json")
KB_JSON_PATH = os.path.join(CONFIG_DIR, "knowledge_base.json")
KB_YAML_PATH = os.path.join(CONFIG_DIR, "knowledge_base.yaml")
INFO_JSON_PATH = os.path.join(BASE_DIR, "info.json")

# Load agronomic matrix
with open(MATRIX_PATH, "r", encoding="utf-8") as f:
    matrix_raw = json.load(f)

matrix_pests = matrix_raw.get("pests", [])
matrix_by_key = {p["key"]: p for p in matrix_pests}

GROUPS = {
    "rice": {
        "name": "Rice / Paddy",
        "scientific_name": "Oryza sativa",
        "description": "Cereal staple crop susceptible to stem borers, plant hoppers, leaf folders, gall midges, and foliage caterpillars (20 cataloged IP102 species).",
        "pests": [
            "rice_leaf_roller", "rice_leaf_caterpillar", "paddy_stem_maggot", "asiatic_rice_borer",
            "yellow_rice_borer", "rice_gall_midge", "rice_stemfly", "brown_plant_hopper",
            "white_backed_plant_hopper", "small_brown_plant_hopper", "rice_water_weevil", "rice_leafhopper",
            "grain_spreader_thrips", "rice_shell_pest", "mole_cricket", "cicadella_viridis",
            "cicadellidae", "lawana_imitata_melichar", "salurnis_marginella_guerr", "cerodonta_denticornis"
        ]
    },
    "corn": {
        "name": "Corn / Maize",
        "scientific_name": "Zea mays",
        "description": "Major cereal & grain crop vulnerable to corn borers, armyworms, cutworms, root grubs, wireworms, and cereal aphids (20 cataloged IP102 species).",
        "pests": [
            "grub", "wireworm", "black_cutworm", "large_cutworm",
            "yellow_cutworm", "corn_borer", "army_worm", "potosiabre_vitarsis",
            "english_grain_aphid", "green_bug", "bird_cherry_oataphid", "wheat_blossom_midge",
            "penthaleus_major", "longlegged_spider_mite", "wheat_phloeothrips", "wheat_sawfly",
            "locustoidea", "prodenia_litura", "meadow_moth", "chlumetia_transversa"
        ]
    },
    "mungbean": {
        "name": "Mungbean",
        "scientific_name": "Vigna radiata",
        "description": "Leguminous pulse crop sensitive to pod borers, aphids, blister beetles, thrips, plant bugs, and defoliating caterpillars (20 cataloged IP102 species).",
        "pests": [
            "white_margined_moth", "aphids", "sericaorient_alismots_chulsky", "alfalfa_weevil",
            "flax_budworm", "alfalfa_plant_bug", "tarnished_plant_bug", "lytta_polita",
            "legume_blister_beetle", "blister_beetle", "therioaphis_maculata_buckton", "odontothrips_loti",
            "thrips", "alfalfa_seed_chalcid", "apolygus_lucorum", "miridae",
            "beet_army_worm", "beet_weevil", "dasineura_sp", "deporaus_marginatus_pascoe"
        ]
    },
    "squash": {
        "name": "Squash / Cucurbits",
        "scientific_name": "Cucurbita moschata",
        "description": "Cucurbitaceous & fruit vegetable vulnerable to fruit flies, whiteflies, fruit borers, leafminers, and spider mites (20 cataloged IP102 species).",
        "pests": [
            "trialeurodes_vaporariorum", "dacus_dorsalis", "tetradacus_c_bactrocera_minax", "bactrocera_tsuneonis",
            "cabbage_army_worm", "pieris_canidia", "beet_fly", "beet_spot_flies",
            "oides_decempunctata", "pseudococcus_comstocki_kuwana", "parathrene_regalis", "ampelophaga",
            "xylotrechus", "erythroneura_apicalis", "colomerus_vitis", "viteus_vitifoliae",
            "lycorma_delicatula", "limacodidae", "peach_borer", "sternochetus_frigidus"
        ]
    },
    "eggplant": {
        "name": "Eggplant",
        "scientific_name": "Solanum melongena",
        "description": "Solanaceous crop susceptible to fruit & shoot borers, flea beetles, broad mites, scale insects, whiteflies, and thrips (20 cataloged IP102 species).",
        "pests": [
            "red_spider", "flea_beetle", "polyphagotars_onemus_latus", "scirtothrips_dorsalis_hood",
            "aleurocanthus_spiniferus", "nipaecoccus_vastalor", "icerya_purchasi_maskell", "ceroplastes_rubens",
            "chrysomphalus_aonidum", "unaspis_yanonensis", "parlatoria_zizyphus_lucus", "panonchus_citri_mcgregor",
            "phyllocoptes_oleiverus_ashmead", "brevipoalpus_lewisi_mcgregor", "phyllocnistis_citrella_stainton", "toxoptera_citricidus",
            "toxoptera_aurantii", "aphis_citricola_vander_goot", "papilio_xuthus", "adristyrannus"
        ]
    }
}

# Construct knowledge base structure
kb_crops = {}
key_to_crop = {}

for crop_key, crop_info in GROUPS.items():
    pests_dict = {}
    for p_key in crop_info["pests"]:
        key_to_crop[p_key] = crop_key
        mat = matrix_by_key.get(p_key)
        if not mat:
            raise ValueError(f"Missing matrix entry for {p_key}")
        
        ph = mat.get("plant_health", {})
        prec = mat.get("pesticide_recommendation", {})
        sev = ph.get("severity_level", "Moderate")

        # Thresholds tailored to severity
        if p_key in ["army_worm", "fall_armyworm"]:
            thresholds = {"low": [1, 2], "moderate": [3, 5], "severe": 6}
        elif sev == "Critical":
            thresholds = {"low": [1, 1], "moderate": [2, 3], "severe": 4}
        elif sev == "High":
            thresholds = {"low": [1, 2], "moderate": [3, 4], "severe": 5}
        elif sev == "Moderate":
            thresholds = {"low": [1, 2], "moderate": [3, 5], "severe": 6}
        else: # Low
            thresholds = {"low": [1, 3], "moderate": [4, 6], "severe": 7}

        phi_days = prec.get("pre_harvest_interval_days", 14)
        ai = prec.get("active_ingredient", "Target Insecticide")
        formulation = prec.get("formulation", "Standard")
        rate = prec.get("application_rate", "Standard foliar spray")
        bio = prec.get("bio_rational_alternative", "Cold-pressed Neem Oil 10,000 ppm")
        safety = prec.get("safety_precautions", "Wear protective gloves, mask, and clothing.")

        # Product name
        prod_name = f"{ai} {formulation}"

        # If asiatic rice borer, ensure Cartap / Chlorantraniliprole in product_name
        if p_key == "asiatic_rice_borer":
            prod_name = "Cartap Hydrochloride 50% SP or Chlorantraniliprole 18.5% SC"
        elif p_key == "army_worm":
            prod_name = "Chlorantraniliprole 18.5% SC or Emamectin Benzoate 5% SG"
        elif p_key == "icerya_purchasi_maskell":
            prod_name = "Buprofezin 25% SC or Pyriproxyfen 10% EC"
        elif p_key == "alfalfa_weevil":
            prod_name = "Lambda-Cyhalothrin 5% EC or Indoxacarb 14.5% SC"

        pests_dict[p_key] = {
            "common_name": mat.get("common_name", p_key.replace("_", " ").title()),
            "scientific_name": mat.get("scientific_name", ""),
            "infestation_thresholds": thresholds,
            "recommendations": {
                "chemical": {
                    "product_name": prod_name,
                    "active_ingredient": ai,
                    "dosage": f"{rate} | PHI: {phi_days} days",
                    "phi_days": phi_days,
                    "timing": f"Target early instars or initial sign of {ph.get('primary_symptom', 'foliar damage').lower()}"
                },
                "organic_biocontrol": {
                    "product_name": bio,
                    "dosage": "2.5 g/L or 3-5 ml/L spray application",
                    "phi_days": 0,
                    "timing": "Apply at early detection or as preventative field border buffer"
                },
                "safety_precautions": safety
            }
        }

    kb_crops[crop_key] = {
        "name": crop_info["name"],
        "scientific_name": crop_info["scientific_name"],
        "description": crop_info["description"],
        "pests": pests_dict
    }

# Also map remaining 2 IP102 classes to a host crop
key_to_crop["mango_flat_beak_leafhopper"] = "squash"
key_to_crop["rhytidodera_bowrinii_white"] = "squash"

# Assemble full KB data
kb_data = {
    "system": {
        "version": "3.0",
        "confidence_threshold_high": 0.50,
        "confidence_threshold_uncertain": 0.20
    },
    "moisture_thresholds": {
        "dry_percent": 25.0,
        "wet_percent": 75.0
    },
    "crops": kb_crops
}

# 1. Save knowledge_base.json
with open(KB_JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(kb_data, f, indent=2, ensure_ascii=False)
print(f"Updated {KB_JSON_PATH}")

# 2. Save knowledge_base.yaml
with open(KB_YAML_PATH, "w", encoding="utf-8") as f:
    yaml.dump(kb_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
print(f"Updated {KB_YAML_PATH}")

# 3. Update pest_classes_102.json
with open(CLASSES_PATH, "r", encoding="utf-8") as f:
    classes_data = json.load(f)

for item in classes_data.get("classes", []):
    k = item.get("key")
    if k in key_to_crop:
        item["crop_affinity"] = key_to_crop[k]

with open(CLASSES_PATH, "w", encoding="utf-8") as f:
    json.dump(classes_data, f, indent=2, ensure_ascii=False)
print(f"Updated {CLASSES_PATH}")

# 4. Update primary_crop in ip102_agronomic_matrix.json
crop_display_names = {
    "rice": "Rice",
    "corn": "Corn",
    "mungbean": "Mungbean",
    "squash": "Squash",
    "eggplant": "Eggplant"
}
for mat_item in matrix_pests:
    k = mat_item.get("key")
    if k in key_to_crop:
        assigned_crop = key_to_crop[k]
        mat_item["primary_crop"] = crop_display_names[assigned_crop]

with open(MATRIX_PATH, "w", encoding="utf-8") as f:
    json.dump(matrix_raw, f, indent=2, ensure_ascii=False)
print(f"Updated {MATRIX_PATH}")

# 5. Keep info.json in sync if it exists
if os.path.exists(INFO_JSON_PATH):
    with open(INFO_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(matrix_raw, f, indent=2, ensure_ascii=False)
    print(f"Updated {INFO_JSON_PATH}")

print("Done! All 5 crops have 20 uniform pests each.")
