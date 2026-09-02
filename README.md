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

## 3. GPS Module Testing & Verification (`GY-NEO6MV2` / `GY-GPS6MV2`)

The GY-NEO6MV2 and GY-GPS6MV2 GPS modules stream NMEA data over hardware UART `/dev/ttyS0` at 9600 baud. Both modules use the u-blox NEO-6M core and are fully interchangeable in this system.

### Running GPS Unit Tests

```bash
python tests/test_gps.py
```

### Running Standalone Continuous GPS Live Monitor (Press Ctrl+C to Stop)

To continuously debug and view live coordinates, satellite count, fix status, and raw NMEA stream:

```bash
python edge/gps_test.py
```
*or via module execution:*
```bash
python -m edge.gps_test
```
*or directly from the driver:*
```bash
python -m edge.drivers.gps
```

#### Diagnostic & Debug CLI Options:

| Option | Flag | Default | Description |
| :--- | :--- | :--- | :--- |
| `--raw` | `-r` | *Disabled* | Print all incoming raw NMEA sentences (`$GPGGA`, `$GPRMC`, etc.) in real time |
| `--interval` | `-i` | `1.0` | Telemetry refresh interval in seconds (e.g. `0.5` for faster polling) |
| `--port` | `-p` | `/dev/ttyS0` | Serial port device path (or set via `$GPS_SERIAL_PORT`) |
| `--baud` | `-b` | `9600` | Serial baud rate (or set via `$GPS_BAUD_RATE`) |

#### Debugging Usage Examples:

* **Real-time Raw NMEA Inspection** (verify serial transmission even before satellite lock):
  ```bash
  python edge/gps_test.py --raw
  ```
* **Fast 0.5s Refresh with Verbose Raw Data:**
  ```bash
  python edge/gps_test.py --raw --interval 0.5
  ```
* **Custom Serial Device (e.g., USB-to-UART bridge):**
  ```bash
  python edge/gps_test.py --port /dev/ttyUSB0 --baud 9600
  ```

### Hardware Setup & Verification on Raspberry Pi 4

1. **Enable UART Interface:**
   Ensure hardware serial is enabled in `/boot/config.txt` (or `/boot/firmware/config.txt`):
   ```text
   enable_uart=1
   ```
2. **Wiring Verification:**
   * `VCC` -> Pin 1 (3.3V)
   * `GND` -> Pin 14 (Ground)
   * `TX` -> Pin 10 (GPIO 15 / RXD0)
   * `RX` -> Pin 8 (GPIO 14 / TXD0)

3. **Running Main Robot Loop with Live GPS & Dual Ultrasonic Telemetry:**
   ```bash
   python -m edge.robot_main
   ```

---

## 4. Running Subsystems & Autonomous Control

### Main Robot Control Loop

```bash
python -m edge.robot_main
```

### Running All Automated Tests

```bash
python -m unittest discover tests
```
*or:*
```bash
pytest tests/ -v
```
