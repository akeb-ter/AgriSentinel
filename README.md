# AgriSentinel: AI-Powered Smart Crop Protection System

> **AgriSentinel: An AI-Powered Crop Protection System for Smart Pest Detection, Plant Health Assessment, and Pest-Specific Pesticide Recommendation**

AgriSentinel is an edge-deployed, AI-driven crop monitoring and protection platform engineered for field deployment on Raspberry Pi. It integrates real-time optical insect detection, autonomous crop identification, a 6-tier symptom-aware plant health assessment engine, an agricultural agronomic matrix, acoustic deterrent alerts, and an offline-capable Mobile Progressive Web App (PWA).

---

## Table of Contents
1. [Key Features](#1-key-features)
2. [Hardware Architecture & Pinouts](#2-hardware-architecture--pinouts)
3. [Environment Setup & Installation](#3-environment-setup--installation)
4. [Running the Application](#4-running-the-application)
5. [Systemd Service Management (`systemctl`)](#5-systemd-service-management-systemctl)
6. [Wi-Fi Configuration & Autonomous Hotspot](#6-wi-fi-configuration--autonomous-hotspot)
7. [System Usage Guide](#7-system-usage-guide)
8. [Automated Testing & Hardware Diagnostics](#8-automated-testing--hardware-diagnostics)
9. [REST API & WebSocket Documentation](#9-rest-api--websocket-documentation)
10. [Troubleshooting & FAQ](#10-troubleshooting--faq)

---

## 1. Key Features

- **100 Uniform IP102 Pests Catalog (20 Pests per Crop, Zero Overlap):**
  Comprehensive coverage across 5 staple crop systems:
  - **Rice** (*Oryza sativa*): 20 species (Rice leaf roller, Asiatic rice borer, Brown plant hopper, etc.)
  - **Corn** (*Zea mays*): 20 species (Fall armyworm, Asian corn borer, Corn leaf aphid, etc.)
  - **Wheat** (*Triticum*): 20 species (English grain aphid, Wheat blossom midge, Cereal leaf beetle, etc.)
  - **Citrus** (*Citrus spp.*): 20 species (Asian citrus psyllid, Citrus red mite, Citrus leafminer, etc.)
  - **Mango** (*Mangifera indica*): 20 species (Mango shoot caterpillar, Mango leafhopper, Mango stem borer, etc.)
- **Autonomous Crop Identification (`Auto-Detect`):**
  The system automatically infers and assigns the host crop directly from detected pest taxonomy (`infer_crop_from_pest`). No manual crop reconfiguration is required when moving the device between fields.
- **6-Tier Symptom-Aware Plant Health Assessment:**
  Evaluates real-time crop vigor, foliar damage, and infestation pressure:
  1. `Healthy / Pest-Free` — Pristine canopy, zero target pests detected.
  2. `Minimal Threat / Beneficial Insects Only` — Ecological balance preserved; beneficial predators present.
  3. `Early-Stage Spotting / Mild Pest Pressure` — 1–2 pests detected; minor pinhole or sap feeding.
  4. `Moderate Leaf Damage / Active Feeding` — 3–5 pests detected; visible foliar stripping or stem punctures.
  5. `Severe Defoliation / High Pest Density` — 6+ pests detected; critical economic threshold exceeded.
  6. `Critical Blight / Systemic Crop Failure` — Unchecked heavy infestation risking crop loss.
- **Agronomic Treatment Matrix & Scientific Citations:**
  Detailed chemical formulations (e.g., Chlorantraniliprole 18.5% SC, Imidacloprid 17.8% SL), application dosages, water spray volumes, Pre-Harvest Intervals (PHI), and certified organic bio-control alternatives with citations (IRRI, FAO, USDA, ICAR, UC IPM).
- **Beneficial Predator Safeguard:**
  Identifies predatory insects (ladybird beetles, lacewings, praying mantises, spiders) and marks them with a `[BENEFICIAL PREDATOR]` badge, withholding toxic chemical sprays to preserve natural biocontrol agents.
- **Multi-Model Edge Vision Engine:**
  - `comprehensive_102`: YOLO11s trained on the IP102 dataset (`ip102_yolo11s_640x640.tflite`).
  - `fast_scout_3pests`: YOLOv8n ultra-lightweight real-time scout (`yolov8n_aphid_fruitfly_scale.tflite`).
  - `cereal_diagnostic`: MobileNetV3 classifier (`cerealpestaid_mobilenetv3.tflite`).
  - `species_encyclopedia`: ONNX deep taxonomic classifier for 2,037 wild arthropods (`quarrying_insect_identifier_224x224.onnx`).
  - `EdgeImpulseRunner`: Linux aarch64 binary accelerator (`agrisentinel-linux-aarch64-v5-impulse-#1.eim`).
  - `SimulatedDetector`: Automated test pattern generator for headless or offline development.
- **Dual User Interfaces:**
  - **Desktop/Tablet Dashboard (`/dashboard`):** Real-time MJPEG feed, telemetry cards, live alert banner, paginated historical logs, and batch deletion.
  - **Mobile Progressive Web App (`/mobile`):** Field scouting interface with smartphone camera capture, instant image upload, offline PWA service worker caching, and touch-optimized controls.

---

## 2. Hardware Architecture & Pinouts

AgriSentinel integrates the **FEELWORLD 4K10X 4K PTZ Camera** (1/2.8" 8.29MP CMOS, 10X Optical Zoom, Pan ±125°, Tilt ±30°) as its primary optical vision subsystem:

```
+------------------------------------------------------------------------+
|                          Raspberry Pi 4B / 5                           |
|                                                                        |
|   +--------------------------+               +---------------------+   |
|   |  USB 3.0 / Ethernet PoE  |               |  GPIO Header (40-P) |   |
|   |  (UVC Video + VISCA UDP) |               |                     |   |
|   +------------+-------------+               +----------+----------+   |
+----------------|----------------------------------------|--------------+
                 |                                        |
                 v                                        v
  [ FEELWORLD 4K10X 4K PTZ ]                     [ Piezo Buzzer ]
  • USB 3.0 UVC: /dev/video0                     Pin 33 (BCM 13) -> Signal (+)
  • LAN PoE: rtsp://<ip>:554/live/av0            Pin 39 (GND)    -> Ground (-)
  • VISCA Control: UDP Port 52381 / 1259
  • Pan ±125° | Tilt ±30° | 10X Optical Zoom
```

### Hardware Interface & Pinout Table

| Component | Interface / Type | Raspberry Pi Connection | Protocol / Pin | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **FEELWORLD 4K10X PTZ** | USB 3.0 UVC | USB 3.0 Port (Blue) | V4L2 (`/dev/video0`) | Plug-and-play MJPEG compressed video |
| **FEELWORLD 4K10X (PoE)** | 100M Ethernet RJ45 | Ethernet Port (or PoE Switch) | RTSP + VISCA UDP `52381` | Low-latency IP stream & network PTZ |
| **Piezo Buzzer (+)** | PWM / Digital Out | Physical Pin 33 | **BCM GPIO 13** | Default pin; supports active/passive |
| **Piezo Buzzer (-)** | Ground | Physical Pin 39 (or 6, 9) | GND | Common system ground |
| *(Optional Buzzer Pin)* | PWM / Digital Out | Physical Pin 11 | BCM GPIO 17 | Alternative pin (`PIEZO_GPIO_PIN=17`) |
| *(Legacy Camera Fallback)* | CSI Ribbon / USB | Camera Port 0 / 1 | `libcamera-vid` / V4L2 | Supported as fallback fixed cameras |

> [!NOTE]
> When running on a non-Pi development machine (Windows, macOS, or x86_64 Linux) or without the physical PTZ camera attached, the driver automatically engages the **Virtual PTZ Viewport Engine**, allowing real-time simulated pan, tilt, zoom, presets, and auto-zoom verifications directly in your browser.

> [!TIP]
> **Raspberry Pi USB Performance & Live AI Toggle:**
> The FEELWORLD 4K10X camera connects via USB 3.0 UVC. To deliver a smooth, fluid 25–30 FPS MJPEG video stream on the Raspberry Pi:
> - Video capture and encoding run in a dedicated high-speed loop decoupled from AI inference.
> - A **Live AI Toggle** (`Live AI: ON` / `Live AI: OFF`) is available directly on both the Dashboard and Mobile PWA.
> - When `Live AI: OFF` is selected, background inference is paused to eliminate CPU contention and maintain zero-latency 30 FPS video streaming. Farmers can click **"Capture & Inspect Now"** at any time to run instant on-demand AI detection on the current frame.

---

## 3. Environment Setup & Installation

### 3.1 Prerequisites (Raspberry Pi OS / Linux)

Update system packages and install the required video, build, and network libraries:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv python3-dev libgl1-mesa-glx libglib2.0-0 network-manager git v4l-utils
```

### 3.2 Clone Repository

```bash
cd ~
git clone https://github.com/CharlesAnthony14/AgriSentinel.git
cd AgriSentinel
```

### 3.3 Create and Activate Virtual Environment

```bash
# On Linux / Raspberry Pi OS:
python3 -m venv venv
source venv/bin/activate

# On Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3.4 Install Python Dependencies

```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

#### Runtime Engine Details:
- **Raspberry Pi OS (Linux ARM):** Installs `tflite-runtime` or `ai-edge-litert` and `onnxruntime` automatically from `requirements.txt`.
- **Windows / macOS:** Uses modern `ai-edge-litert` (Google LiteRT) or `onnxruntime`.

---

## 4. Running the Application

### 4.1 Quick Start

Run the server using your active virtual environment:

```bash
python main.py
```

The terminal will display startup diagnostics:
```text
==================================================
 AgriSentinel Smart Crop Probe Server Starting
 An AI-Powered Crop Protection System
 Network Mode : Wi-Fi
 Probe IP     : 192.168.1.105
 Local Domain : http://agrisentinel.local:8000
 Web Dashboard: http://192.168.1.105:8000
==================================================
```

### 4.2 Configuration Environment Variables

You can customize port, host, camera source, and audio pins via environment variables:

```bash
# Example: Run on custom port with USB camera /dev/video1 and GPIO 17
HOST=0.0.0.0 PORT=8080 CAMERA_INDEX=1 PIEZO_GPIO_PIN=17 python main.py
```

| Variable | Default | Description |
| :--- | :--- | :--- |
| `HOST` | `0.0.0.0` | Bind IP address for server |
| `PORT` | `8000` | HTTP and WebSocket port |
| `CAMERA_INDEX` | `0` | Camera device index (`0` for `/dev/video0`) |
| `STREAM_WIDTH` | `640` | Video capture width |
| `STREAM_HEIGHT` | `480` | Video capture height |
| `PIEZO_GPIO_PIN` | `13` | BCM GPIO pin for acoustic buzzer (e.g. `13` or `17`) |
| `BUZZER_DEFAULT_FREQ` | `2500` | Audible frequency in Hz for passive piezo buzzer |
| `BG_DETECTION_INTERVAL` | `0.6` | Cooldown between continuous background AI inference passes (seconds) |

### 4.3 Web Access Points

Open a browser on any laptop, tablet, or mobile phone connected to the same network:

- **Desktop Dashboard:** `http://<pi-ip>:8000/dashboard` (or `http://agrisentinel.local:8000/dashboard`)
- **Mobile Scouting PWA:** `http://<pi-ip>:8000/mobile`
- **Developer Engineering Console:** `http://<pi-ip>:8000/dev_settings`
- **Direct Video Stream:** `http://<pi-ip>:8000/video_feed`
- **Interactive OpenAPI Docs:** `http://<pi-ip>:8000/docs`

---

## 5. Systemd Service Management (`systemctl`)

AgriSentinel provides a production-grade systemd service definition (`agrisentinel.service`) so that the probe launches automatically on Raspberry Pi boot and self-heals after unexpected crashes.

### 5.1 Service Configuration File (`agrisentinel.service`)

The repository includes `agrisentinel.service`:

```ini
[Unit]
Description=AgriSentinel Main Loop Service
After=network-online.target
Wants=network-online.target

[Service]
User=agrisentinel
Group=agrisentinel
WorkingDirectory=/home/agrisentinel/gh/remote/AgriSentinel

# Command to start using the virtual environment python:
ExecStart=/home/agrisentinel/gh/remote/AgriSentinel/venv/bin/python main.py

# Restart policy for continuous field resilience
Restart=always
RestartSec=5

# Forward standard output and error to journalctl
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

> [!TIP]
> Verify that `User`, `Group`, `WorkingDirectory`, and the path to `python` in `ExecStart` match your Raspberry Pi username and installation directory.

### 5.2 Installing and Enabling the Service

```bash
# 1. Copy service file to systemd directory
sudo cp agrisentinel.service /etc/systemd/system/

# 2. Reload systemd daemon to recognize changes
sudo systemctl daemon-reload

# 3. Enable service to start automatically on system boot
sudo systemctl enable agrisentinel.service

# 4. Start the service immediately
sudo systemctl start agrisentinel.service
```

### 5.3 Daily Service Commands

```bash
# Check running status and uptime:
sudo systemctl status agrisentinel.service

# Restart the service (e.g. after code pull or configuration edit):
sudo systemctl restart agrisentinel.service

# Stop the service:
sudo systemctl stop agrisentinel.service

# View live continuous output logs:
sudo journalctl -u agrisentinel.service -f -n 100
```

---

## 6. Wi-Fi Configuration & Autonomous Hotspot

AgriSentinel is equipped with robust network failover to ensure farmers can always connect to the device even in remote fields without cellular towers.

### 6.1 Configuring Wi-Fi via `scripts/set_wifi.sh`

Connect the probe to a farm Wi-Fi router or smartphone personal hotspot:

```bash
sudo bash scripts/set_wifi.sh --ssid="MyFarmHotspot" --pass="FarmSecure2026"
```

What `scripts/set_wifi.sh` accomplishes:
1. Creates or updates the NetworkManager profile for `wlan0`.
2. Enables **infinite connection retries** (`connection.autoconnect-retries 0`).
3. Sets connection priority to **100** so it takes precedence over secondary networks.
4. **Disables Wi-Fi power saving** (`802-11-wireless.powersave 2`), preventing the Pi's Wi-Fi chip from going to sleep when disconnected.
5. Attempts immediate activation if the network is currently in range.

### 6.2 Autonomous Hotspot Fallback & Watchdog

1. **Autonomous Hotspot Mode:**
   If no configured Wi-Fi network is detected, NetworkManager automatically initializes an ad-hoc Access Point named **`AgriSentinel-Hotspot`**. Farmers can connect directly using their phone or tablet without any external router.
2. **Wi-Fi Watchdog:**
   A background watchdog thread runs every 15 seconds inside `main.py`. If `wlan0` becomes disconnected, it automatically triggers `nmcli device wifi rescan` to circumvent `wpa_supplicant` backoff timers, instantly reconnecting as soon as the farmer approaches the probe with their personal hotspot.

---

## 7. System Usage Guide

### 7.1 Automatic Crop Identification (`Auto-Detect`)

1. By default, the probe is set to **`Auto-Detect`** mode (`crop_mode="auto"`).
2. Point the camera at crop foliage. When an insect is detected (e.g. *Brown plant hopper*), the knowledge base automatically maps it to its host crop (**Rice**).
3. The dashboard and mobile app instantly update their status badge to **`Host Crop: Rice (Auto-Identified)`**, evaluate the 6-tier health rating, and deliver rice-specific pesticide recommendations.
4. If inspecting a mono-crop field where you want strict class filtering, choose **Rice**, **Corn**, **Wheat**, **Citrus**, or **Mango** directly from the Crop selector dropdown.

### 7.2 Interpreting the 6-Tier Plant Health Rating

The system computes plant health by cross-referencing pest counts, foliar damage, and beneficial insect activity:

```
[Healthy / Pest-Free]           --> No pests detected; zero spray recommended.
[Minimal Threat / Beneficial]   --> Predators present (ladybugs/lacewings); preserve biocontrols.
[Early-Stage Spotting / Mild]   --> 1-2 pests; monitor closely or use cultural / neem oil controls.
[Moderate Leaf Damage / Active] --> 3-5 pests; initiate targeted pesticide treatment at recommended dosage.
[Severe Defoliation / High]     --> 6+ pests; immediate intervention required with chemical formulation.
[Critical Blight / Failure]     --> Heavy infestation; maximum dosage, immediate quarantine / rotation.
```

### 7.3 Beneficial Insect Predator Guard

When beneficial insects like **Ladybird Beetles (Coccinellidae)**, **Green Lacewings (Chrysopidae)**, **Spiders (Araneae)**, or **Praying Mantises (Mantodea)** enter the camera's field of view:
- A bright **lime green bounding box** is drawn around the insect.
- The UI displays an alert badge: `[BENEFICIAL PREDATOR - DO NOT SPRAY]`.
- Broad-spectrum chemical recommendations are suppressed to protect the orchard or field ecosystem.

### 7.4 Field Scouting with Mobile PWA (`/mobile`)

1. Open `http://<pi-ip>:8000/mobile` on your smartphone browser.
2. Tap **"Install"** or **"Add to Home Screen"** to install AgriSentinel as an offline-capable PWA.
3. Tap **"Take Leaf Photo"** to open your mobile phone camera.
4. Snap a photo of an infested leaf or pest.
5. The image is uploaded to `/api/detect/upload`, processed through the AI vision pipeline, and returns the identified pest, host crop, plant health status, and full pesticide regimen.

### 7.5 Managing Historical Detections

- Navigate to the **Detections History** section on the Dashboard.
- Filter records by **Host Crop**, **Pest Species**, or **Infestation Severity**.
- Use the **Batch Selection** checkboxes to select specific records and click **"Delete Selected"** to remove them and their disk snapshots simultaneously.
- Click **"Clear All Detections"** to completely purge the SQLite database and image storage.

---

## 8. Automated Testing & Hardware Diagnostics

AgriSentinel includes a 77-test verification suite covering API endpoints, vision pipelines, knowledge base rules, database transactions, mobile PWA routes, hardware GPIO drivers, and FEELWORLD 4K10X PTZ camera controls.

### 8.1 Running Automated Unit Tests

Run the full pytest suite from the project root:

```bash
pytest tests/ -v
```

Run specific test modules:
```bash
# Test the 100-pest IP102 catalog, auto-crop inference, and 6-tier health:
pytest tests/test_knowledge_base.py -v

# Test FastAPI REST endpoints and batch deletion:
pytest tests/test_api_endpoints.py -v

# Test AI vision detector and multi-model switching:
pytest tests/test_vision_detector.py -v

# Test Mobile PWA routes and photo upload:
pytest tests/test_mobile_pwa.py -v

# Test Piezo buzzer sound driver:
pytest tests/test_piezo.py -v
```

### 8.2 Standalone Hardware Diagnostics

AgriSentinel provides dedicated standalone command-line diagnostic tools in `edge/`:

#### 1. Buzzer & Sound Diagnostic (`edge.piezo_test`)
```bash
# Emit 3 audible test beeps on default GPIO 13:
python -m edge.piezo_test

# Test DC ON for 2 seconds (for active buzzers):
python -m edge.piezo_test --on 2.0

# Play a 2.5 kHz tone for 2 seconds (for passive buzzers):
python -m edge.piezo_test --tone 2500 --duration 2.0

# Run a siren frequency sweep (1.0 kHz to 3.5 kHz):
python -m edge.piezo_test --sweep

# Test on a custom GPIO pin (e.g., GPIO 17):
python -m edge.piezo_test --pin 17 --beep 3
```

#### 2. Camera & PTZ Subsystem Diagnostic (`edge.camera_test`)
```bash
# Run standalone FEELWORLD 4K10X PTZ Pan/Tilt/Zoom, Presets, and Auto-Zoom diagnostic:
python -m edge.camera_test --ptz-test

# Start local diagnostic web preview server:
python -m edge.camera_test
```

#### 3. AI Inference Benchmark (`edge.inference_test`)
```bash
# Benchmark model load times and frame inference speed:
python -m edge.inference_test
```

---

## 9. REST API & WebSocket Documentation

AgriSentinel provides a comprehensive OpenAPI-compliant REST API:

### Telemetry & Agronomics

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/status` | Current probe telemetry (active crop, detected pests, 6-tier health rating, infestation level) |
| `GET` | `/api/crops` | List of supported crops (Rice, Corn, Wheat, Citrus, Mango) and pest catalogs |
| `POST` | `/api/crop/select` | Set active crop or enable auto-detection (`{"crop": "auto"}` or `{"crop": "rice"}`) |
| `POST` | `/api/plot/update` | Update target farm area / field plot name |
| `POST` | `/api/analyze` | Force immediate on-demand camera capture, inference, and database log |
| `POST` | `/api/detect/upload` | Upload an image from mobile phone for instant detection and treatment |
| `GET` | `/api/recommendations/{crop}/{pest}` | Query agronomic matrix for pesticide recommendations and safety intervals |
| `GET` | `/api/stats` | Aggregate stats (total detections, pest frequency distribution, health trends) |

### FEELWORLD 4K10X PTZ Controls

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/ptz/status` | Current Pan, Tilt, Zoom (`1.0x`–`10.0x`), Presets, Patrol mode, and motion limits |
| `POST` | `/api/ptz/move` | Relative step or absolute coordinates (`{"action": "pan_left" | "tilt_up" | "home" | "set", "step": 5.0}`) |
| `POST` | `/api/ptz/preset` | Recall or save canopy preset (`{"action": "recall" | "save", "preset_id": 1, "name": "..."}`) |
| `POST` | `/api/ptz/patrol` | Configure automated patrol & auto-zoom (`{"patrol_mode": "preset_sweep" | "continuous_sweep" | "off", "auto_zoom_on_detect": true}`) |
| `POST` | `/api/dev/camera/config` | Switch connection mode (`usb_uvc` / `ip_rtsp`), resolution profile (`1080p_adaptive`, `720p_lightweight`, `4k_uhd`), and RTSP URL |

### Detections & Data Management

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/detections` | Paginated historical detections with filtering (`crop`, `pest`, `date`, `severity`) |
| `GET` | `/api/detections/{id}` | Retrieve single detection record by ID |
| `DELETE` | `/api/detections/{id}` | Delete detection record and its disk image |
| `POST` | `/api/detections/batch-delete` | Batch delete multiple records (`{"ids": ["id1", "id2"]}`) |
| `POST` | `/api/detections/clear` | Clear all historical detection records and images |

### Hardware & Vision Settings

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/dev/status` | System metrics (CPU, RAM, disk, temperature, Wi-Fi status, camera status) |
| `POST` | `/api/vision/live_toggle` | Toggle continuous background AI pest detection (`{"enabled": false}` for smooth 25–30 FPS streaming on Pi; manual inspection remains always available) |
| `POST` | `/api/dev/wifi/connect` | Configure Wi-Fi credentials via NetworkManager (`{"ssid": "...", "password": "..."}`) |
| `POST` | `/api/dev/camera/restart` | Restart camera capture loop without restarting the whole server |
| `POST` | `/api/dev/system/power` | Power management action (`{"action": "reboot"}` or `{"action": "shutdown"}`) |
| `GET` | `/api/dev/system/logs` | Fetch recent systemd journal logs |
| `GET` | `/api/dev/vision_settings` | Get active vision model profile and confidence thresholds |
| `POST` | `/api/dev/vision_settings` | Update active vision model (`comprehensive_102`, `fast_scout_3pests`, etc.) |

### Real-Time WebSocket Alerts

- **Endpoint:** `ws://<pi-ip>:8000/ws/alerts`
- **Payload Event Structure:**
```json
{
  "event": "pest_detected",
  "data": {
    "crop": "rice",
    "crop_mode": "auto",
    "pest_name": "Brown plant hopper",
    "confidence": 0.88,
    "plant_health": "Severe Defoliation / High Pest Density",
    "infestation_level": "Severe",
    "count": 6,
    "is_beneficial": false,
    "pesticide_recommendation": {
      "treatment": "Pymetrozine 50% WG @ 300 g/ha or Dinotefuran 20% SG @ 150-200 g/ha",
      "spray_timing": "Apply at early nymph emergence directed at plant base",
      "phi_days": 14,
      "organic_alternative": "Azadirachtin (Neem) 1% @ 3 ml/L or Beauveria bassiana",
      "citation": "IRRI Standard Evaluation System for Rice; FAO IPM Guidelines"
    }
  }
}
```

---

## 10. Troubleshooting & FAQ

### Q1: The camera feed shows a simulated animated pattern instead of my real camera.
- Ensure the camera is connected and enabled.
  - On Raspberry Pi CSI camera: test using `rpicam-still -t 2000 -o test.jpg`. If unavailable, ensure camera is enabled in `sudo raspi-config` under Interface Options.
  - On USB webcam: verify `/dev/video0` exists (`ls -l /dev/video*`). Set `CAMERA_INDEX=0` (or `1`) in your environment.
- Ensure no other service or process is using the camera (`sudo fuser /dev/video0`).

### Q2: Port 8000 is already in use.
- Run AgriSentinel on a different port:
  ```bash
  PORT=8080 python main.py
  ```
- Or terminate the conflicting process:
  ```bash
  sudo fuser -k 8000/tcp
  ```

### Q3: GPIO permission error when sounding the piezo buzzer.
- Ensure the `agrisentinel` service user belongs to the `gpio` group:
  ```bash
  sudo usermod -aG gpio,video agrisentinel
  ```

### Q4: How do I change the buzzer GPIO pin?
- Set the environment variable `PIEZO_GPIO_PIN=17` before starting `main.py`, or update `agrisentinel.service` with:
  ```ini
  Environment="PIEZO_GPIO_PIN=17"
  ```

### Q5: How do I view live application logs when running as a systemd service?
- Run:
  ```bash
  sudo journalctl -u agrisentinel.service -f -n 100
  ```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
