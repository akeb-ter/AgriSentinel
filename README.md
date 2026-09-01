# AgriSentinel - Autonomous Crop Protection Robot

AgriSentinel is an AI-assisted autonomous crop protection robot utilizing species-specific adaptive frequency repellent technology.

---

## 1. Environment Setup & Installation

To avoid system package conflicts (such as Python's `externally-managed-environment` error on Linux and Raspberry Pi OS Bookworm), always set up and activate a virtual environment (`venv`) before installing dependencies.

### Step 1: Create Virtual Environment

```bash
# On Linux / Raspberry Pi OS / macOS / Windows:
python3 -m venv venv
```

### Step 2: Activate Virtual Environment

* **Raspberry Pi OS / Linux / macOS:**
  ```bash
  source venv/bin/activate
  ```
* **Windows (PowerShell):**
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
* **Windows (Command Prompt):**
  ```cmd
  venv\Scripts\activate.bat
  ```

### Step 3: Upgrade pip and Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 2. Camera Subsystem Testing (`rpicam` & OpenCV)

The `edge/camera_test.py` module provides a local FastAPI server streaming live video. It automatically selects the optimal capture backend:
1. **`rpicam-vid` / `libcamera-vid`**: Native hardware pipeline for Raspberry Pi Camera Module.
2. **OpenCV VideoCapture**: For USB webcams and desktop development.
3. **Synthetic Test Generator**: Diagnostic fallback when no camera is attached.

### Running on Raspberry Pi 4 (CSI Camera Module)

```bash
python3 -m edge.camera_test
```
*(The server will automatically detect `rpicam-vid` or `libcamera-vid` on your Raspberry Pi).*

### Running on Local PC (Webcam or Synthetic Mode)

```bash
python -m edge.camera_test
```

### Accessing the Web Dashboard

Open your browser and navigate to:
* **Web UI Dashboard:** [http://localhost:8000](http://localhost:8000) (or `http://<RPI_IP>:8000`)
* **Raw Video Stream:** [http://localhost:8000/video_feed](http://localhost:8000/video_feed)
* **Camera Diagnostics JSON:** [http://localhost:8000/api/camera/status](http://localhost:8000/api/camera/status)
* **Snapshot JPEG:** [http://localhost:8000/api/camera/snapshot](http://localhost:8000/api/camera/snapshot)

---

## 3. Running Subsystems & Autonomous Control

### Main Robot Control Loop

```bash
python -m edge.robot_main
```

### Running Automated Tests

```bash
pytest tests/ -v
```
