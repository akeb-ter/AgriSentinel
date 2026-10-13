# AgriSentinel v2.0 - System Migration & Enhancement Changelog

## Working Title
> **AgriSentinel: An AI-Powered Crop Protection Robot for Smart Pest Detection, Plant Health Assessment, and Pest-Specific Pesticide Recommendation**

---

## 1. Overview of Architectural Pivot
In accordance with the panel recommendations outlined in `update.md`, AgriSentinel has transitioned from an autonomous 4WD wheeled rover with acoustic frequency repellents into a **stationary / portable smart imaging and soil probe stick**.

The core focus of the system is now:
1. High-resolution crop foliage imaging and real-time pest detection and counting.
2. Soil moisture root zone sensing to assess hydration and moisture-related plant stress.
3. Pest-specific agricultural pesticide recommendations (chemical & organic alternatives, dosage, timing, PHI, and PPE precautions).
4. Centralized SQLite database management system (DBMS) logging.
5. Mobile-first responsive web monitoring dashboard and documented REST/WebSocket APIs.

---

## 2. Hardware Subsystem Changes

### Clean Removal of Legacy Rover Modules
The following modules and their corresponding unit tests have been completely removed to eliminate dead code and keep the probe stick lightweight:
* `edge/drivers/motors.py` & `tests/test_motors.py` (L298N H-Bridge dual motor driver)
* `edge/drivers/ultrasonic.py` (Dual ultrasonic collision avoidance sensors)
* `edge/drivers/servo.py` & `tests/test_servo.py` (Pan-tilt camera scanning servo)
* `edge/drivers/gps.py` & `tests/test_gps.py` & `edge/gps_test.py` (UART GPS telemetry module)
* Acoustic frequency repellent & piezo buzzer code and tests.

### Added Hardware: Soil Moisture Sensor Subsystem
* **File:** `edge/drivers/soil_moisture.py`
* **Features:**
  * Supports physical I2C (Adafruit ADS1115 / ADS1015) and SPI (MCP3008) Analog-to-Digital Converters (ADCs).
  * Automatically activates a mock simulation mode with realistic environmental fluctuations when running on Windows/PC without hardware ADCs.
  * Classifies soil condition into three key agricultural tiers:
    * **Dry:** $< 25.0\%$ (drought risk / irrigation required)
    * **Optimal:** $25.0\% - 75.0\%$ (favorable crop root moisture)
    * **Waterlogged:** $> 75.0\%$ (excess moisture / fungal root rot risk)

---

## 3. Agricultural Intelligence & Multi-Crop Knowledge Base

### Multi-Crop Catalog (`config/knowledge_base.yaml` & `config/knowledge_base.json`)
AgriSentinel provides out-of-the-box knowledge bases and pesticide recommendation profiles for four major crops:

1. **Corn (*Zea mays*):**
   * Pests: Fall Armyworm (*Spodoptera frugiperda*), Asian Corn Borer (*Ostrinia furnacalis*), Corn Earworm (*Helicoverpa zea*), Corn Leaf Aphid (*Rhopalosiphum maidis*).
2. **Mungbean (*Vigna radiata*):**
   * Pests: Bean Aphid (*Aphis craccivora*), Bean Pod Borer (*Maruca vitrata*), Whitefly (*Bemisia tabaci*), Green Leafhopper (*Empoasca kerri*).
3. **Squash / Cucurbits (*Cucurbita*):**
   * Pests: Squash Bug (*Anasa tristis*), Melon Fruit Fly (*Bactrocera cucurbitae*), Squash Vine Borer (*Melittia cucurbitae*), Spotted Cucumber Beetle (*Diabrotica undecimpunctata*).
4. **Eggplant (*Solanum melongena*):**
   * Pests: Eggplant Fruit and Shoot Borer - EFSB (*Leucinodes orbonalis*), Striped Flea Beetle (*Phyllotreta striolata*), Serpentine Leafminer (*Liriomyza trifolii*), Two-Spotted Spider Mite (*Tetranychus urticae*).

### Two-Tier Confidence & Uncertainty Handling
To prevent improper chemical pesticide application on false positives:
* **High Confidence ($\ge 70\%$):** Displays verified pesticide trade names, active ingredients, application dosage, timing, Pre-Harvest Intervals (PHI), and organic alternatives.
* **Borderline / Uncertain Confidence ($40\% - 69\%$):** Displays an **Amber Caution Badge** (`[VERIFY FIRST]`) with candidate pest advice, instructing field scouting before chemical spraying.
* **Low Confidence ($< 40\%$):** Filtered out as background visual noise.

### Integrated Plant Health Evaluation
Combines pest infestation severity and soil moisture readings:
$$\text{Plant Health} = f(\text{Pest Count}, \text{Pest Species}, \text{Soil Moisture \%})$$
* **0 Pests + Optimal Soil:** Healthy / Pest-Free
* **0 Pests + Dry Soil:** Moisture Stress (Drought Risk)
* **0 Pests + Waterlogged Soil:** Excess Moisture (Fungal / Root Rot Risk)
* **1 - 2 Pests:** Mild Pest Stress (Early Infestation Stage)
* **3 - 5 Pests:** Under Moderate Pest Pressure
* **6+ Pests:** Severe Infestation (Critical Crop Damage Risk)

---

## 4. Vision Pipeline & Capture Workflow

* **File:** `edge/vision/detector.py` & `edge/probe_controller.py`
* **Inference Runtime:**
  * Pluggable detector supporting compiled Edge Impulse Linux `.eim` binaries on Raspberry Pi, ONNX Runtime, and a `SimulatedDetector` for cross-platform development on Windows.
  * Bounding box annotation with color-coded labels, confidence percentages, and top diagnostic status bar.
* **Auto-Pause & Confirmation Loop:**
  * Probe runs live video preview stream (`/video_feed`).
  * When a candidate pest is detected, the controller pauses the stream briefly for image stabilization, grabs a clean high-resolution frame, confirms detection, evaluates soil moisture and plant health, writes the annotated snapshot to `web/static/detections/`, saves the record to SQLite, and broadcasts a real-time WebSocket alert.
* **On-Demand Manual Inspection:**
  * Instant "Capture & Inspect Now" trigger via dashboard button or `POST /api/analyze`.

---

## 5. Database (DBMS) Persistence

* **File:** `edge/database.py`
* **SQLite Table (`detections`):**
  * `id`: Auto-incrementing primary key
  * `timestamp`: ISO 8601 string
  * `crop_type`: Selected crop (`corn`, `mungbean`, `squash`, `eggplant`)
  * `farm_area`: User-assigned field plot / zone
  * `detected_pest`: Common name of detected pest species
  * `pest_count`: Estimated count of pests in the frame
  * `infestation_level`: `None`, `Low`, `Moderate`, `Severe`
  * `soil_moisture_percent`: Float percentage at inspection time
  * `soil_status`: `Dry`, `Optimal`, `Waterlogged`
  * `plant_health_status`: Holistic plant health evaluation
  * `confidence`: Model confidence score (0.0 to 1.0)
  * `recommended_pesticide`: Chemical insecticide product and active ingredient
  * `organic_alternative`: Bio-control / organic solution
  * `dosage_instruction`: Application dilution and timing
  * `safety_precautions`: Required PPE and environmental warnings
  * `image_path`: Path to annotated snapshot (`/static/detections/...`)
  * `status`: `CONFIRMED`, `UNCERTAIN`, `PEST_FREE`

---

## 6. Mobile-First Web Dashboard & REST/WebSocket API

### Frontend (`web/templates/dashboard.html`)
* **Responsive Layout:** Optimized for smartphones, tablets, and desktop workstations.
* **Header Controls:** Dynamic crop selector dropdown and field plot input.
* **Live Video Feed:** Real-time MJPEG stream with detection bounding boxes.
* **Sensor Metrics Cards:** Real-time Soil Moisture gauge, Pest Count counter, Infestation level badge, and Plant Health status.
* **Pesticide Advisor Tab:** Standalone lookup for all supported crops and pests without requiring camera capture.
* **Inspection History Gallery:** Filterable table with snapshot photo modals and record management.
* **Alerts:** Polyphonic Web Audio polite chime synthesizer and WebSocket toast popups (`/ws/alerts`).

### REST & WebSocket API Endpoints (`edge/web_app.py`)
* `GET /api/status`: Probe telemetry and current sensor state
* `GET /api/soil-moisture`: Live soil moisture reading and status
* `GET /api/crops`: List of supported crops and cataloged pests
* `POST /api/crop/select`: Switch active crop
* `POST /api/plot/update`: Switch field plot / zone tag
* `POST /api/analyze`: Trigger immediate camera capture and AI analysis
* `GET /api/detections`: Paginated historical detection records with filtering
* `GET /api/detections/{id}`: Single inspection record details
* `DELETE /api/detections/{id}`: Delete inspection record and image
* `GET /api/recommendations/{crop}/{pest}`: Query agricultural knowledge base
* `GET /api/stats`: Inspection summary statistics
* `WebSocket /ws/alerts`: Real-time detection event stream

---

## 7. Verification & Automated Test Suite

A comprehensive test suite with 20 unit and integration tests has been implemented and verified via `pytest`:
* `tests/test_soil_moisture.py`: Validates sensor readings, mock mode, and status thresholds.
* `tests/test_knowledge_base.py`: Validates crop catalogs, infestation tiers, two-tier confidence, and plant health logic.
* `tests/test_database.py`: Validates SQLite CRUD operations, filtering, and stats aggregation.
* `tests/test_api_endpoints.py`: Validates all FastAPI REST endpoints.
* `tests/test_camera_stream.py`: Validates frame generation, MJPEG stream parser, and diagnostic endpoints.

All 20 tests pass cleanly:
```bash
pytest tests/ -v
# 20 passed in 1.21s
```
