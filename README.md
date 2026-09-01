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

## 3. Motor Driver Subsystem Testing (`L298N Dual H-Bridge`)

The `edge/drivers/motors.py` module governs directional movement (Forward, Backward, Left Spin, Right Spin, Pivot Left, Pivot Right, Stop) for the 4WD chassis.

### Hardware Wiring & 5V Jumper Configuration:
* **`ENA` / `ENB`**: Jumpered to onboard 5V pins (100% full speed duty cycle, freeing Pi PWM pins).
* **`IN1`**: Pin 29 (`GPIO 5`) - Left Motor Forward
* **`IN2`**: Pin 31 (`GPIO 6`) - Left Motor Reverse
* **`IN3`**: Pin 35 (`GPIO 19`) - Right Motor Forward
* **`IN4`**: Pin 37 (`GPIO 26`) - Right Motor Reverse
* **`GND`**: Pin 20 (or any Pi GND) connected to Common Ground Bus

### Running Motor Unit Tests:

```bash
python tests/test_motors.py
```

### Running Standalone Hardware Directional Test Sequence:

To run the interactive automated test sequence (Forward -> Reverse -> Left Spin -> Right Spin -> Pivot Left -> Pivot Right -> Stop):

```bash
python -m edge.drivers.motors
```

---

## 4. Running Subsystems & Autonomous Control

### Main Robot Control Loop

```bash
python -m edge.robot_main
```

### Running Automated Tests

```bash
python tests/test_motors.py
```
*or via pytest:*
```bash
pytest tests/ -v
```
