# AgriSentinel - 102-Class TFLite Pest Detection & Agricultural Intelligence Integration

## 1. Overview
This document describes the architectural enhancement integrating the **102-Class Agricultural Pest Taxonomy (IP102)** into the AgriSentinel crop monitoring probe on branch `dev2`.

The system now provides:
1. Native support for TensorFlow Lite (`.tflite`) object detection and classification models.
2. A comprehensive 102-class agricultural taxonomy index (`config/pest_classes_102.json` and `config/labels.txt`).
3. Addition of **Rice (*Oryza sativa*)** as a primary crop with specialized knowledge base entries for Asiatic Rice Borer, Yellow Rice Borer, Brown Planthopper, Rice Leaf Roller, Rice Gall Midge, and Rice Leafhopper.
4. An intelligent **Taxonomic IPM Decision Fallback Engine** in `edge/knowledge_base.py` ensuring that every single pest out of the 102 classes receives scientifically grounded chemical and organic pesticide recommendations, application dosages, pre-harvest intervals (PHI), and safety precautions.
5. High-fidelity multi-crop simulation supporting all 102 pests for PC/Windows development without requiring physical Raspberry Pi hardware.

---

## 2. 102 Agricultural Pest Taxonomy

The 102 pest classes (aligned with the agricultural IP102 benchmark) are indexed below:

| ID | Class Label / Common Name | Scientific Name | Primary Crop Affinity |
|---|---|---|---|
| 1 | Rice Leaf Roller | *Cnaphalocrocis medinalis* | Rice |
| 2 | Rice Leaf Caterpillar | *Parnara guttata* | Rice |
| 3 | Paddy Stem Maggot | *Hydrellia sasakii* | Rice |
| 4 | Asiatic Rice Borer | *Chilo suppressalis* | Rice |
| 5 | Yellow Rice Borer | *Scirpophaga incertulas* | Rice |
| 6 | Rice Gall Midge | *Orseolia oryzae* | Rice |
| 7 | Rice Stemfly | *Chlorops oryzae* | Rice |
| 8 | Brown Plant Hopper | *Nilaparvata lugens* | Rice |
| 9 | White Backed Plant Hopper | *Sogatella furcifera* | Rice |
| 10 | Small Brown Plant Hopper | *Laodelphax striatellus* | Rice |
| 11 | Rice Water Weevil | *Lissorhoptrus oryzophilus* | Rice |
| 12 | Rice Leafhopper | *Nephotettix cincticeps* | Rice |
| 13 | Grain Spreader Thrips | *Haplothrips aculeatus* | Rice |
| 14 | Rice Shell Pest | *Echinocnemus squameus* | Rice |
| 15 | Grub (White Grub) | *Scarabaeidae larvae* | Corn / Cereals |
| 16 | Mole Cricket | *Gryllotalpa orientalis* | Rice / Turf |
| 17 | Wireworm | *Elateridae larvae* | Corn / Tubers |
| 18 | White Margined Moth | *Spilosoma virginica* | Legumes / Mungbean |
| 19 | Black Cutworm | *Agrotis ipsilon* | Corn / Vegetables |
| 20 | Large Cutworm | *Agrotis tokionis* | Vegetables |
| 21 | Yellow Cutworm | *Agrotis segetum* | Corn / Cereals |
| 22 | Red Spider Mite | *Tetranychus urticae* | Eggplant / Vegetables |
| 23 | Corn Borer | *Ostrinia furnacalis* | Corn |
| 24 | Armyworm | *Mythimna separata* | Corn / Cereals |
| 25 | Aphids | *Aphidoidea* | Mungbean / General |
| 26 | Potosiabre vitarsis | *Protaetia brevitarsis* | Corn / Fruit |
| 27 | Peach Borer | *Synanthedon exitiosa* | Fruit / Stone Fruit |
| 28 | English Grain Aphid | *Sitobion avenae* | Wheat / Grains |
| 29 | Green Bug | *Schizaphis graminum* | Wheat / Sorghum |
| 30 | Bird Cherry-Oat Aphid | *Rhopalosiphum padi* | Wheat / Cereals |
| 31 | Wheat Blossom Midge | *Sitodiplosis mosellana* | Wheat |
| 32 | Penthaleus major | *Penthaleus major* | Wheat / Legumes |
| 33 | Longlegged Spider Mite | *Petrobia latens* | Wheat / Grasses |
| 34 | Wheat Phloeothrips | *Haplothrips tritici* | Wheat |
| 35 | Wheat Sawfly | *Cephus cinctus* | Wheat |
| 36 | Cerodonta denticornis | *Cerodontha denticornis* | Wheat / Cereals |
| 37 | Beet Fly | *Pegomya hyoscyami* | Beet / Chard |
| 38 | Flea Beetle | *Phyllotreta striolata* | Eggplant / Crucifers |
| 39 | Cabbage Armyworm | *Mamestra brassicae* | Brassica / Vegetables |
| 40 | Beet Armyworm | *Spodoptera exigua* | Vegetables / Legumes |
| 41 | Beet Spot Flies | *Psilopa leucostoma* | Beet |
| 42 | Meadow Moth | *Loxostege sticticalis* | Beet / Legumes |
| 43 | Beet Weevil | *Bothynoderes punctiventris* | Beet |
| 44 | Sericaorient alismots chulsky | *Maladera orientalis* | Legumes / Nursery |
| 45 | Alfalfa Weevil | *Hypera postica* | Legumes / Forage |
| 46 | Flax Budworm | *Heliothis ononis* | Flax / Field Crops |
| 47 | Alfalfa Plant Bug | *Adelphocoris lineolatus* | Legumes |
| 48 | Tarnished Plant Bug | *Lygus lineolaris* | Vegetables / Berries |
| 49 | Locustoidea (Locust) | *Locustoidea* | Corn / Grasses |
| 50 | Lytta polita | *Lytta polita* | Legumes / Flowers |
| 51 | Legume Blister Beetle | *Epicauta subglabra* | Mungbean / Legumes |
| 52 | Blister Beetle | *Epicauta spp.* | Legumes |
| 53 | Spotted Alfalfa Aphid | *Therioaphis maculata* | Legumes |
| 54 | Odontothrips loti | *Odontothrips loti* | Legumes |
| 55 | Thrips | *Thysanoptera* | Mungbean / Eggplant |
| 56 | Alfalfa Seed Chalcid | *Bruchophagus roddi* | Legumes / Seeds |
| 57 | Indian Cabbage White | *Pieris canidia* | Crucifers |
| 58 | Apolygus lucorum | *Apolygus lucorum* | Cotton / Vegetables |
| 59 | Limacodidae (Slug Caterpillar) | *Limacodidae* | Fruit / Trees |
| 60 | Grape Phylloxera | *Viteus vitifoliae* | Grape / Fruit |
| 61 | Grape Leaf Blister Mite | *Colomerus vitis* | Grape / Fruit |
| 62 | Citrus Flat Mite | *Brevipalpus lewisi* | Citrus |
| 63 | Oides decempunctata | *Oides decempunctata* | Grape / Fruit |
| 64 | Broad Mite | *Polyphagotarsonemus latus* | Eggplant / Peppers |
| 65 | Comstock Mealybug | *Pseudococcus comstocki* | Fruit / Ornamental |
| 66 | Parathrene regalis | *Parathrene regalis* | Fruit / Vines |
| 67 | Grape Sphinx | *Ampelophaga rubiginosa* | Grape / Fruit |
| 68 | Spotted Lanternfly | *Lycorma delicatula* | Fruit / Trees |
| 69 | Grape Borer | *Xylotrechus pyrrhoderus* | Grape / Fruit |
| 70 | Green Leafhopper | *Cicadella viridis* | Rice / Grasses |
| 71 | Miridae (Plant Bug) | *Miridae* | Vegetables |
| 72 | Greenhouse Whitefly | *Trialeurodes vaporariorum* | Squash / Tomato |
| 73 | Erythroneura apicalis | *Erythroneura apicalis* | Fruit / Vines |
| 74 | Asian Swallowtail | *Papilio xuthus* | Citrus |
| 75 | Citrus Red Mite | *Panonychus citri* | Citrus |
| 76 | Citrus Rust Mite | *Phyllocoptruta oleivora* | Citrus |
| 77 | Cottony Cushion Scale | *Icerya purchasi* | Citrus / Ornamentals |
| 78 | Arrowhead Scale | *Unaspis yanonensis* | Citrus |
| 79 | Red Wax Scale | *Ceroplastes rubens* | Citrus / Tea |
| 80 | Florida Red Scale | *Chrysomphalus aonidum* | Citrus |
| 81 | Black Parlatoria Scale | *Parlatoria ziziphi* | Citrus |
| 82 | Spherical Mealybug | *Nipaecoccus vastator* | Citrus |
| 83 | Orange Spiny Whitefly | *Aleurocanthus spiniferus* | Citrus |
| 84 | Chinese Citrus Fly | *Bactrocera minax* | Citrus |
| 85 | Oriental Fruit Fly | *Bactrocera dorsalis* | Squash / Fruit |
| 86 | Japanese Orange Fly | *Bactrocera tsuneonis* | Citrus |
| 87 | Tobacco Cutworm | *Spodoptera litura* | Corn / Vegetables |
| 88 | Adristyrannus | *Adristyrannus* | Citrus |
| 89 | Citrus Leafminer | *Phyllocnistis citrella* | Citrus |
| 90 | Brown Citrus Aphid | *Toxoptera citricida* | Citrus |
| 91 | Black Citrus Aphid | *Toxoptera aurantii* | Citrus |
| 92 | Spirea Aphid | *Aphis spiraecola* | Citrus / Apple |
| 93 | Chilli Thrips | *Scirtothrips dorsalis* | Eggplant / Pepper |
| 94 | Dasineura Gall Midge | *Dasineura sp.* | Fruit / Legumes |
| 95 | Flatid Planthopper | *Lawana imitata* | Fruit / Tea |
| 96 | Salurnis marginella Planthopper | *Salurnis marginella* | Fruit |
| 97 | Mango Leaf-Cutting Weevil | *Deporaus marginatus* | Mango / Fruit |
| 98 | Mango Shoot Borer | *Chlumetia transversa* | Mango / Fruit |
| 99 | Mango Flat Beak Leafhopper | *Idioscopus niveosparsus* | Mango / Fruit |
| 100 | Mango Branch Borer | *Rhytidodera bowringii* | Mango / Fruit |
| 101 | Mango Pulp Weevil | *Sternochetus frigidus* | Mango / Fruit |
| 102 | Cicadellidae (Leafhopper Family) | *Cicadellidae* | Rice / Grasses |

---

## 3. TFLite Vision Pipeline Architecture

### Runner Implementation (`edge/vision/detector.py`)
The `TfliteRunner` class provides:
* **Interpreter Resolution:** Automatically loads lightweight `tflite_runtime.interpreter.Interpreter` (recommended for Raspberry Pi) or falls back to `tensorflow.lite.Interpreter`.
* **Quantization Handling:** Supports both quantized INT8/UINT8 models (`dtype == np.uint8`) and floating-point models (`float32`), normalizing inputs $[0, 255] \to [0.0, 1.0]$ when necessary.
* **Dual Output Parser:**
  1. *Object Detection Models (SSD MobileNet / YOLO TFLite):* Parses standard detection tensors `[boxes, classes, scores, count]` and rescales normalized bounding boxes $[ymin, xmin, ymax, xmax]$ to original frame resolution.
  2. *Classification Models:* Parses 102-element probability logits vector with automated Softmax calculation and center-crop region highlighting.
* **Simulated Inference Fallback:** When physical `.tflite` model files are not yet deployed in `edge/models/`, `TfliteRunner` automatically delegates to `SimulatedDetector` without throwing runtime errors.

---

## 4. Agricultural Knowledge Base & Rice Support

### Primary Multi-Crop Catalog (`config/knowledge_base.yaml` & `config/knowledge_base.json`)
The primary catalog now supports 5 key crops:
* **Rice (*Oryza sativa*):** Asiatic Rice Borer, Yellow Rice Borer, Brown Planthopper, Rice Leaf Roller, Rice Gall Midge, Rice Leafhopper.
* **Corn (*Zea mays*):** Fall Armyworm, Asian Corn Borer, Black Cutworm, Wireworm, Corn Leaf Aphid.
* **Mungbean (*Vigna radiata*):** Legume Blister Beetle, Bean Pod Borer, Bean Aphid, Thrips.
* **Squash (*Cucurbita*):** Oriental Fruit Fly (*Dacus dorsalis*), Greenhouse Whitefly, Red Spider Mite, Squash Bug.
* **Eggplant (*Solanum melongena*):** Flea Beetle, Broad Mite, Red Spider, Chilli Thrips (*Scirtothrips dorsalis*).

### Full 102-Pest Taxonomic Fallback Engine
In `edge/knowledge_base.py`, any of the 102 IP102 pests can be queried even outside its primary crop table. The engine maps the pest to its biological family and returns complete IPM guidance:

1. **Borers (Stem, Shoot, Branch, Cane borers):** Chlorantraniliprole 18.5% SC / Flubendiamide (0.3-0.4 ml/L, 14d PHI) + Bt kurstaki / Trichogramma parasitoids.
2. **Hoppers & Leafhoppers (BPH, Cicadellidae, Planthoppers):** Triflemezopyrim 10% SC / Pymetrozine (0.5 ml/L, 14d PHI) + Beauveria bassiana / Metarhizium anisopliae.
3. **Caterpillars, Armyworms, Cutworms & Leaf Rollers:** Emamectin Benzoate 5% SG / Chlorantraniliprole (0.4 g/L, 7-14d PHI) + Bt + Cold-pressed Neem oil.
4. **Aphids, Whiteflies & Plant Bugs:** Imidacloprid 17.8% SL / Acetamiprid (0.5 ml/L, 14d PHI) + Neem oil with potassium soap (strictly avoids daytime spraying on flowering crops).
5. **Thrips:** Spinetoram 11.7% SC / Fipronil (0.5 ml/L, 7d PHI) + Spinosad + Blue sticky monitoring cards.
6. **Beetles & Weevils:** Lambda-Cyhalothrin 5% EC / Spinosad 45% SC (1.0 ml/L) + Diatomaceous earth dusting + Azadirachtin.
7. **Mites & Spider Mites:** Spiromesifen 22.9% SC / Abamectin 1.8% EC (0.8 ml/L, 7d PHI) + Wettable sulfur 80% WP (sulfur-oil application interval rules enforced).
8. **Scales & Mealybugs:** Buprofezin 25% SC / Dinotefuran 20% SG (1.5 ml/L, 14d PHI) + Paraffinic summer horticultural oil drench.
9. **Fruit Flies & Midges:** Malathion 50% EC protein bait splashes + Methyl Eugenol / Cue-lure pheromone monitoring traps.
10. **Soil & Subterranean Pests (Grubs, Wireworms, Mole Crickets, Locusts):** Chlorpyrifos 20% EC root drench or Fipronil 0.3% GR soil granules + Entomopathogenic nematodes (*Steinernema carpocapsae*).

---

## 5. Verification & Automated Test Results

The test suite was expanded to 28 unit and integration tests covering API endpoints, camera streaming, database operations, soil moisture sensor calibration, knowledge base matching, two-tier confidence enforcement, rice crop support, and the 102-pest taxonomy.

```
tests/test_api_endpoints.py::test_api_status_endpoint PASSED             [  3%]
tests/test_api_endpoints.py::test_api_crops_endpoint PASSED              [  7%]
tests/test_api_endpoints.py::test_api_select_crop PASSED                 [ 10%]
tests/test_api_endpoints.py::test_api_soil_moisture PASSED               [ 14%]
tests/test_api_endpoints.py::test_api_recommendation_query PASSED        [ 17%]
tests/test_api_endpoints.py::test_api_manual_analyze PASSED              [ 21%]
tests/test_api_endpoints.py::test_api_detections_list PASSED             [ 25%]
tests/test_camera_stream.py::test_camera_manager_synthetic_generation PASSED [ 28%]
tests/test_camera_stream.py::test_camera_manager_jpeg_encoding PASSED    [ 32%]
tests/test_camera_stream.py::test_rpicam_mjpeg_stream_parsing PASSED     [ 35%]
tests/test_camera_stream.py::test_api_index_endpoint PASSED              [ 39%]
tests/test_camera_stream.py::test_api_camera_status PASSED               [ 42%]
tests/test_camera_stream.py::test_api_camera_snapshot PASSED             [ 46%]
tests/test_database.py::test_database_crud_operations PASSED             [ 50%]
tests/test_knowledge_base.py::test_knowledge_base_supported_crops PASSED [ 53%]
tests/test_knowledge_base.py::test_infestation_level_calculation PASSED  [ 57%]
tests/test_knowledge_base.py::test_two_tier_confidence_and_uncertainty PASSED [ 60%]
tests/test_knowledge_base.py::test_integrated_plant_health_derivation PASSED [ 64%]
tests/test_knowledge_base.py::test_rice_crop_support_and_pests PASSED    [ 67%]
tests/test_knowledge_base.py::test_ip102_catalog_fallback_recommendations PASSED [ 71%]
tests/test_soil_moisture.py::test_soil_sensor_mock_reading PASSED        [ 75%]
tests/test_soil_moisture.py::test_soil_sensor_classification_thresholds PASSED [ 78%]
tests/test_vision_detector.py::test_load_102_labels PASSED               [ 82%]
tests/test_vision_detector.py::test_detection_box_structure PASSED       [ 85%]
tests/test_vision_detector.py::test_simulated_detector_multi_crop PASSED [ 89%]
tests/test_vision_detector.py::test_simulated_detector_force_pest PASSED [ 92%]
tests/test_vision_detector.py::test_tflite_runner_simulated_fallback PASSED [ 96%]
tests/test_vision_detector.py::test_get_detector_factory PASSED          [100%]

======================== 28 passed in 1.42s ========================
```
