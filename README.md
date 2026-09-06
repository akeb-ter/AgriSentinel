# AgriSentinel - Autonomous Crop Protection Robot

AgriSentinel is an AI-assisted autonomous crop protection robot utilizing species-specific adaptive frequency repellent technology.

## Core Features
* 📷 **Real-Time AI Pest Detection**: Live video feed processing via OpenCV/TFLite to identify insect threats instantly.
* 🗺️ **GPS Telemetry & Heatmap Logs**: Plots live and historical pest detections on an interactive MapLibre map with density heatmaps.
* 🔊 **Acoustic Deterrent**: Triggers specific ultrasonic frequencies via a piezobuzzer to repel pests upon detection.
* ⚙️ **On-Screen Teleoperation**: Full directional control of the 4WD chassis and camera pan servo directly from the web dashboard.

---

## Table of Contents
1. [Hardware Architecture & Wiring](#1-hardware-architecture--wiring)
2. [Environment Setup & Installation](#2-environment-setup--installation)
3. [Configuration & Usage](#3-configuration--usage)
4. [Hardware Subsystems & Testing](#4-hardware-subsystems--testing)

---

## 1. Hardware Architecture & Wiring

For a complete pinout summary table, refer to **[Hardware Pinouts & Wiring Guide](markdowns/pinouts.md)**.

### Motor Driver (`L298N Dual H-Bridge`)
Governs directional movement for the 4WD chassis.
* **`ENA` / `ENB`**: Jumpered to onboard 5V pins (100% full speed duty cycle, freeing Pi PWM pins).
* **`IN1`**: Pin 29 (`GPIO 5`) - Left Motor Forward
* **`IN2`**: Pin 31 (`GPIO 6`) - Left Motor Reverse
* **`IN3`**: Pin 35 (`GPIO 19`) - Right Motor Forward
* **`IN4`**: Pin 37 (`GPIO 26`) - Right Motor Reverse
* **`GND`**: Pin 20 (or any Pi GND) connected to Common Ground Bus

### Camera Pan Servo (`SG90` / `MG996R`)
Governs the camera pan-tilt scanning mechanism on **Hardware PWM0**.
* **`Signal` (Yellow/Orange)**: Pin 12 (`GPIO 18`)
* **`VCC` (Red)**: 5V Supply Rail (Pin 2, Pin 4, or L298N 5V Out)
* **`GND` (Brown/Black)**: Common Ground Bus

### GPS Module (`GY-NEO6MV2` / `GY-GPS6MV2`)
Streams NMEA data over hardware UART `/dev/ttyS0` at 9600 baud.
* **`VCC`**: Pin 1 (3.3V)
* **`GND`**: Pin 14 (Ground)
* **`TX`**: Pin 10 (`GPIO 15` / `RXD0`)
* **`RX`**: Pin 8 (`GPIO 14` / `TXD0`)
*(Ensure `enable_uart=1` is set in `/boot/config.txt`)*

---

## 2. Environment Setup & Installation

To avoid system package conflicts (such as Python's `externally-managed-environment` error on Linux and Raspberry Pi OS Bookworm), always set up and activate a virtual environment (`venv`) before installing dependencies.

### Step 1: Create Virtual Environment
```bash
# On Raspberry Pi OS (recommended to inherit system GPIO packages):
python3 -m venv --system-site-packages venv

# On Windows / macOS / Generic Linux:
python -m venv venv
```

### Step 2: Activate Virtual Environment
* **Raspberry Pi OS / Linux / macOS:** `source venv/bin/activate`
* **Windows (PowerShell):** `.\venv\Scripts\Activate.ps1`

### Step 3: Upgrade pip and Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Systemd Service (Optional, for auto-boot)
To have AgriSentinel run automatically when the Raspberry Pi turns on:
```bash
sudo cp agrisentinel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable agrisentinel
sudo systemctl start agrisentinel
```

---

## 3. Configuration & Usage

### Running the Main Robot Server
Start the FastAPI server, which initializes the hardware and serves the dashboard:
```bash
python -m main
```

### Accessing the Web Dashboard
Open your browser and navigate to:
* **Dashboard:** [http://agrisentinel.local:8000](http://agrisentinel.local:8000) (or use your Pi's IP address)

### Connecting to Wi-Fi
You can configure the robot to connect to your target Wi-Fi network (or mobile hotspot) dynamically. The script uses NetworkManager to save the profile, disable Wi-Fi powersave, and guarantee infinite reconnect retries on boot.

**Option A: Via Web UI (Recommended)**
1. Navigate to the Developer Settings in the Web Dashboard.
2. In the "Network Connection" card, enter your SSID and Password.
3. Click **Connect & Save**.

**Option B: Via Terminal Script**
```bash
# Secure Networks
./scripts/set_wifi.sh --ssid="MyNetwork" --pass="MyPassword"

# Open Networks
./scripts/set_wifi.sh --ssid="OpenNetwork"
```

### Controlling the Camera Pan Servo
You can pan the camera left and right (from -60° to +60°) to scan for pests. The servo driver automatically detaches when idle to prevent buzzing and overheating.

**Option A: Via Web UI (Recommended)**
1. Navigate to the **Teleoperation** panel on the right side of the Web Dashboard.
2. Under "Camera Scan", tap or click the **Left** (`<`) and **Right** (`>`) arrow buttons.
3. The camera will smoothly step 5 degrees in the specified direction per click.

**Option B: Via Terminal Script (Testing & Calibration)**
To run a full automated hardware calibration sweep (Center → Far Left → Far Right → Smooth Sweep):
```bash
python -m edge.drivers.servo
```

### Controlling the Motor Driver
You can manually steer the 4WD chassis from the web interface, or run an automated directional verification sequence on the physical hardware.

**Option A: Via Web UI (Recommended)**
1. Navigate to the **Teleoperation** panel on the right side of the Web Dashboard.
2. Under "Movement", use the D-pad arrow buttons (Forward, Reverse, Left, Right) or keyboard arrow keys (`W` `A` `S` `D`).
3. The robot moves for as long as you hold down the button or key.

**Option B: Via Terminal Script (Testing & Verification)**
To run a full hardware test sequence (Forward → Reverse → Spin Left → Spin Right → Pivots):
```bash
python -m edge.drivers.motors
```

### Triggering the Piezo Buzzer
You can manually trigger the acoustic deterrent used to repel detected pests, or run a sweep test script to verify different frequencies.

**Option A: Via Web UI (Recommended)**
1. Navigate to the **Teleoperation** panel on the right side of the Web Dashboard.
2. Click and hold the **Test Buzzer** button.
3. The piezobuzzer will emit the deterrence frequency while active.

**Option B: Via Terminal Script (Testing & Calibration)**
To run an automated frequency sweep and verify PWM tone generation on the hardware:
```bash
python edge/piezo_test.py
```

### Monitoring GPS Telemetry
You can view live bot telemetry directly on the dashboard map, or stream raw NMEA diagnostic data from the terminal.

**Option A: Via Web UI (Recommended)**
1. Navigate to the **Dashboard** tab.
2. The interactive map will display the live bot location and connection badge.
3. Historical detection logs are explicitly tagged with `Live` or `Simulated` GPS fix states.

**Option B: Via Terminal Script (Testing & Diagnostics)**
To run an infinite continuous loop displaying satellite count, coordinates, and raw NMEA sentences (Press `Ctrl + C` to stop):
```bash
python edge/gps_test.py --raw
```

---

## 4. Hardware Subsystems & Testing

AgriSentinel includes comprehensive unit testing and live diagnostic scripts for each hardware subsystem.

### Full System Tests
Run all unit tests via `pytest`:
```bash
pytest tests/ -v
```

### Individual Subsystem Test Plans
For detailed calibration instructions, hardware checklists, and standalone debugging commands, refer to the dedicated Test Plan documents:

* 📷 **[Camera Subsystem Test Plan](markdowns/camera_test_plan.md)** (rpicam & OpenCV diagnostics)
* 📍 **[GPS Module Test Plan](markdowns/gps_test_plan.md)** (Raw NMEA streaming and baud rate testing)
* ⚙️ **[Motor Driver Test Plan](markdowns/motor_test_plan.md)** (Directional mapping and H-Bridge validation)
* 🔭 **[Servo Controller Test Plan](markdowns/servo_test_plan.md)** (PWM scanning and jitter mitigation)
