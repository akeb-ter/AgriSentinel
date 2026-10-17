# AgriSentinel Project Report

## 1. Project Overview
**AgriSentinel** is an AI-powered smart crop protection probe designed for field deployment. It functions as a "sentinel" stick that monitors crop health in real-time. 

**Problem it Solves:**
Traditional crop monitoring often relies on manual inspection, which is labor-intensive and prone to human error. AgriSentinel automates the detection of pests and assessment of plant health by combining computer vision (for pest identification) and soil sensing (for hydration stress). It then provides actionable, crop-specific pesticide and bio-control recommendations based on a built-in agricultural knowledge base.

---

## 2. Architecture
The project follows a **modular edge-computing architecture**, designed to run on a Raspberry Pi (though it includes extensive simulation modes for PC development).

- **Execution Flow**: 
    1. `main.py` launches a **FastAPI** server.
    2. `ProbeController` (singleton) manages concurrent background threads for camera streaming and soil moisture monitoring.
    3. The **Vision Pipeline** processes frames through a pluggable detector (Edge Impulse, ONNX, or Simulated).
    4. The **Decision Engine** (`KnowledgeBase`) maps detections and soil data to plant health statuses and pesticide recommendations.
    5. **Persistence**: Detections are logged in a local **SQLite** database with associated image snapshots saved to the filesystem.
    6. **Frontend**: A mobile-friendly web dashboard provides a live MJPEG stream, telemetry, and a historical log of detections.

---

## 3. Core Subsystems
- **Probe Controller (`edge/probe_controller.py`)**: The "brain" of the system. It coordinates hardware drivers, AI inference, and the "Auto-Pause & Confirmation" workflow (which stabilizes the image and logs a detection when a pest is spotted).
- **Vision System (`edge/vision/detector.py`)**: A modular pipeline supporting multiple backends. It identifies pests, calculates confidence, and renders bounding boxes and telemetry overlays on the video feed.
- **Knowledge Base (`edge/knowledge_base.py`)**: An intelligence layer that loads crop-specific data from YAML/JSON. It implements a **Two-Tier Confidence Strategy**:
    - **Confirmed ($\ge 70\%$)**: Full recommendations.
    - **Uncertain ($40\%-69\%$)**: Amber warning requiring manual verification.
    - **Ignored ($< 40\%$)**: Filtered as noise.
- **Hardware Drivers (`edge/drivers/`)**: 
    - `soil_moisture.py`: Interfaces with ADS1115 (I2C) or MCP3008 (SPI) ADCs to measure soil moisture.
- **Database Layer (`edge/database.py`)**: Handles SQLite CRUD operations for detection logs and user management.
- **Web Interface (`web/` & `edge/web_app.py`)**: Provides the REST API and WebSocket alerts for real-time notifications.

---

## 4. Key Technologies
- **Languages**: Python 3.11
- **Frameworks**: 
    - **FastAPI / Uvicorn**: Backend API and server.
    - **OpenCV**: Image processing and video streaming.
- **Databases**: SQLite
- **AI/ML**: TensorFlow Lite (`.tflite` 102-class detection & classification runner), Edge Impulse (`.eim` binaries), ONNX.
- **Hardware Interfaces**: I2C (ADS1115), SPI (MCP3008), CSI Camera.
- **Frontend**: HTML/CSS/JS, MapLibre GL (for farm mapping).

---

## 5. Current Implementation State
**Implemented Features:**
- [x] Real-time MJPEG video streaming with AI overlays.
- [x] Multi-crop support (Rice, Corn, Mungbean, Squash, Eggplant).
- [x] 102-Class Agricultural Pest Taxonomy (IP102 benchmark catalog).
- [x] TensorFlow Lite inference engine (`TfliteRunner`) supporting quantized & float models.
- [x] Soil moisture sensing with status classification (Dry/Optimal/Waterlogged).
- [x] Automated "Auto-Pause" detection and logging workflow.
- [x] Comprehensive agricultural knowledge base with Two-Tier Confidence & 102-pest IPM fallback.
- [x] Historical detection logging with image snapshots.
- [x] WebSocket alerts for real-time pest notifications.
- [x] High-fidelity simulation mode for non-Pi environments.

**Missing / In Progress:**
- **User Authentication**: A `users_tbl` exists in the database, but the API endpoints for login/session management appear to be skeletal or missing from the main router.
- **Hardware Integration**: While drivers are written, actual field deployment requires copying the `.tflite` model into `edge/models/`.

---

## 6. Setup and Usage
**Installation:**
1. Create a virtual environment: `python -m venv venv`
2. Activate: `source venv/bin/activate` (Linux) or `.\venv\Scripts\Activate.ps1` (Windows).
3. Install dependencies: `pip install -r requirements.txt`.

**Running:**
- Execute `python main.py`.
- Dashboard: `http://localhost:8000/dashboard`.
- Video Feed: `http://localhost:8000/video_feed`.

**Testing:**
- Run the suite: `pytest tests/ -v`.

---

## 7. Observations & Recommendations
- **Code Quality**: The code is well-structured, highly modular, and follows a clean singleton pattern for the controller. The use of `asynccontextmanager` for lifespan events is a best practice.
- **Robustness**: The "Simulation Mode" is exceptionally well-implemented, allowing the entire system to be developed and tested on Windows without needing a Raspberry Pi or physical sensors.
- **Potential Bottlenecks**:
    - **Threading**: The `ProbeController` uses standard `threading.Thread`. While sufficient for this scale, the use of `cv2.VideoCapture` in a loop can sometimes lead to frame lag if the AI inference takes too long. Implementing a separate frame-buffer queue could improve smoothness.
    - **Database**: SQLite is perfect for a single probe, but if the system expands to a fleet of probes, a centralized database (e.g., PostgreSQL) will be required.
- **Improvement Suggestion**: Implement a "Calibration Mode" UI in the dashboard to allow users to set `ADC_AIR_VALUE` and `ADC_WATER_VALUE` for soil sensors without editing environment variables.
