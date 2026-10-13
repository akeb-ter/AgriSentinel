# AgriSentinel: Smart Crop Protection Probe

**Working Title:**
> **AgriSentinel: An AI-Powered Crop Protection Robot for Smart Pest Detection, Plant Health Assessment, and Pest-Specific Pesticide Recommendation**

AgriSentinel is an AI-assisted smart crop monitoring probe stick designed for field deployment. It integrates an imaging camera pointed at crop foliage, an analog capacitive/resistive soil moisture sensor embedded in the root zone, an AI vision detection engine, an agricultural pesticide knowledge base, and a mobile-friendly web dashboard.

---

## Table of Contents
1. [System Architecture & Hardware Wiring](#1-system-architecture--hardware-wiring)
2. [Supported Crops & Agricultural Knowledge Base](#2-supported-crops--agricultural-knowledge-base)
3. [Environment Setup & Installation](#3-environment-setup--installation)
4. [Running the Probe Server & Dashboard](#4-running-the-probe-server--dashboard)
5. [REST API & WebSocket Documentation](#5-rest-api--websocket-documentation)
6. [Subsystem Verification & Testing](#6-subsystem-verification--testing)

---

## 1. System Architecture & Hardware Wiring

AgriSentinel operates as a streamlined skeletal probe stick with two primary sensing subsystems:

### 1. Imaging Camera Subsystem
Captures crop canopy images for real-time pest identification, bounding box annotation, and pest counting.
* **Raspberry Pi Camera Module** (via native `rpicam-vid` / `libcamera-vid` CSI ribbon)
* **USB UVC Webcam** (via OpenCV DirectShow on Windows or V4L2 on Linux)
* **Synthetic Fallback Mode** (built-in animated test pattern for headless and CI environments)

### 2. Soil Moisture Sensor Subsystem
Measures volumetric soil moisture % to assess root hydration and identify moisture-related plant stress (drought vs. waterlogged root rot risk).
* **Sensor Type:** Analog Capacitive (v1.2/v2.0) or Resistive Soil Moisture Probe
* **ADC Interface:** ADS1115 (I2C) or MCP3008 (SPI)
  * **ADS1115 Wiring:**
    * `VDD` -> 3.3V (Pin 1)
    * `GND` -> Ground (Pin 6/9/14)
    * `SCL` -> BCM GPIO 3 / SCL (Pin 5)
    * `SDA` -> BCM GPIO 2 / SDA (Pin 3)
    * `A0`  -> Soil Moisture Sensor Analog Output
  * **Mock Simulator:** Automatically activated when running on Windows/PC without hardware ADC.

---

## 2. Supported Crops & Agricultural Knowledge Base

The system includes pre-configured agricultural profiles and pesticide recommendations defined in `config/knowledge_base.yaml` (and JSON fallback):

| Crop | Pests Detected & Cataloged | Common Symptoms & Health Indicators |
| :--- | :--- | :--- |
| **Corn** (*Zea mays*) | Fall Armyworm, Asian Corn Borer, Corn Earworm, Aphid | Whorl destruction, window-pane leaves, sawdust frass |
| **Mungbean** (*Vigna radiata*) | Bean Aphid, Pod Borer, Whitefly, Green Leafhopper | Leaf curling, chlorosis, pod boreholes, honeydew mold |
| **Squash** (*Cucurbita*) | Squash Bug, Melon Fruit Fly, Squash Vine Borer, Cucumber Beetle | Stem puncture, wilted vines, speckled foliage |
| **Eggplant** (*Solanum melongena*) | Fruit & Shoot Borer (EFSB), Flea Beetle, Leafminer, Spider Mite | Drooping shoot tips, bored fruits, stippled leaves |

### Two-Tier Confidence Strategy
* **High Confidence ($\ge 70\%$):** Displays verified pesticide recommendations, application rates, timing, Pre-Harvest Intervals (PHI), and organic bio-control alternatives.
* **Borderline / Uncertain ($40\% - 69\%$):** Flags an **Amber Warning Badge** (`UNCERTAIN DETECTION`) advising manual visual confirmation before chemical spray.
* **Low Confidence ($< 40\%$):** Filtered out as background noise to prevent false alarms.

---

## 3. Environment Setup & Installation

Always set up and activate a Python virtual environment:

### Step 1: Create and Activate Virtual Environment
```bash
# On Linux / Raspberry Pi OS:
python3 -m venv venv
source venv/bin/activate

# On Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 2: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Running the Probe Server & Dashboard

### Start the Application Server
```bash
python main.py
```

### Access the Web Dashboard
* **Local Web Dashboard:** [http://localhost:8000/dashboard](http://localhost:8000/dashboard) (or `http://agrisentinel.local:8000`)
* **Live Video Feed:** [http://localhost:8000/video_feed](http://localhost:8000/video_feed)
* **Developer Settings:** [http://localhost:8000/dev_settings](http://localhost:8000/dev_settings)

---

## 5. REST API & WebSocket Documentation

* `GET /api/status`: Real-time probe telemetry (active crop, plot, soil moisture %, pest count, plant health).
* `GET /api/soil-moisture`: Current soil moisture reading and status (`Dry`, `Optimal`, `Waterlogged`).
* `GET /api/crops`: List of supported crops and their pest catalogs.
* `POST /api/crop/select`: Switch target crop (`{"crop": "mungbean"}`).
* `POST /api/plot/update`: Update farm zone / field plot (`{"farm_area": "Plot A - Greenhouse 1"}`).
* `POST /api/analyze`: Trigger immediate on-demand camera capture, inference, and database log.
* `GET /api/detections`: Paginated historical detection records with filtering.
* `GET /api/recommendations/{crop}/{pest}`: Query knowledge base directly.
* `WebSocket /ws/alerts`: Real-time WebSocket connection broadcasting pest detection events and audio chime signals.

---

## 6. Subsystem Verification & Testing

AgriSentinel includes comprehensive unit and integration tests via `pytest`:

```bash
pytest tests/ -v
```

All 20 test suites cover:
* Soil Moisture sensor driver and classification thresholds
* Multi-crop knowledge base loader and uncertainty logic
* SQLite database CRUD operations and stats summary
* Camera frame generation and MJPEG parser
* FastAPI REST API endpoints
