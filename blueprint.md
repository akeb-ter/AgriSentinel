# BLUEPRINT.md - AgriSentinel System Specification

This document serves as the technical master plan and implementation blueprint for **AgriSentinel**, an AI-assisted autonomous crop protection robot utilizing species-specific adaptive frequency repellent technology. It is structured for direct ingestion by developers and AI coding agents.

---

## 1. Project Objectives & Requirements Mapping

| Paper Objective | Feature Requirement | Implementation Details |
| :--- | :--- | :--- |
| **Obj 2.1: Manage user information** | User Profile & Login | Hardcoded single-user authentication (`admin`/`password123`) storing session token in `localStorage`. Simple profile management view. |
| **Obj 2.2: Monitor detected pests** | Real-time Detection Feed | Live telemetry logging detected pest classes (*stem borers*, *sucking insects*, *defoliators*, *grain/storage pests*) with timestamp, confidence score, and GPS location tags. |
| **Obj 2.3: Pest notifications** | Alert Engine | WebSocket push notifications triggered instantly when a target pest is detected. |
| **Obj 2.4: Monitor robot status** | System Telemetry Dashboard | Status indicator showing motor state (moving/stopped), dual obstacle clearance (front & rear ultrasonic distance metrics), GPS coordinates, and active AI pipeline. |
| **Obj 2.5: Monitor repellent system** | Audio Output Telemetry | Live display of the active dynamic frequency signal (in Hz) emitted by the audio system. |
| **Obj 2.6: Activate and control** | Remote Control Interface | GUI controls (Forward, Reverse, Left, Right, Stop, Auto/Manual Toggle, Frequency Override) sent via WebSockets/HTTP with bidirectional collision failsafe active. |

---

## 2. System Hardware & Electronics Architecture

### 2.1 Component Breakdown Overview

* **Primary Controller:** Raspberry Pi 4 Model B (4GB / 8GB RAM).
* **Vision & Pan Mechanism:** Camera Module mounted on a pan-tilt Servo Motor assembly (SG90 / MG996R) for active field-of-view scanning.
* **Dual Obstacle Detection:** Dual HC-SR04 Ultrasonic Distance Sensors (Front & Rear) for 360° bidirectional collision avoidance and reverse protection.
* **Chassis Actuation:** L298N Dual H-Bridge Motor Driver governing 4x 12V DC Gear Motors attached to chassis wheels.
* **Adaptive Audio Repellent:** TPA3116D2 Class-D Audio Amplifier connected to a Piezoelectric Horn Tweeter for high-frequency sweeps.
* **Localization Subsystem:** GY-NEO6MV2 / GY-GPS6MV2 GPS Module for live NMEA field coordinate logging.

---

### 2.2 Complete Raspberry Pi 4 Pinout Reference Table

| Component | Module Pin | Raspberry Pi Pin | GPIO / Port | Signal / Purpose | Circuit & Logic Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary Front Ultrasonic (HC-SR04)** | `VCC` | Pin 2 | `5V Power` | 5V Supply Rail | Powered by 5V rail |
| | `GND` | Pin 6 | `GND` | Common Ground | Connected to common system ground |
| | `Trig` | Pin 16 | `GPIO 23` | Front Trigger Output | 3.3V Logic Digital Output |
| | `Echo` | Pin 18 | `GPIO 24` | Front Echo Input | 5V to 3.3V via 1kΩ / 2kΩ voltage divider |
| **Secondary Rear Ultrasonic (HC-SR04)** | `VCC` | Pin 4 | `5V Power` | 5V Supply Rail | Powered by 5V rail |
| | `GND` | Pin 9 | `GND` | Common Ground | Connected to common system ground |
| | `Trig` | Pin 13 | `GPIO 27` | Rear Trigger Output | 3.3V Logic Digital Output |
| | `Echo` | Pin 15 | `GPIO 22` | Rear Echo Input | 5V to 3.3V via 1kΩ / 2kΩ voltage divider |
| **GY-NEO6MV2 / GY-GPS6MV2 GPS Module** | `VCC` | Pin 1 | `3.3V Power` | GPS Power Supply | Powered by Pi 3.3V rail |
| | `GND` | Pin 14 | `GND` | Common Ground | Connected to common system ground |
| | `TX` | Pin 10 | `GPIO 15` | UART Serial Data In (`RXD0`) | Pi UART `/dev/ttyS0` (9600 baud NMEA) |
| | `RX` | Pin 8 | `GPIO 14` | UART Serial Data Out (`TXD0`) | Pi UART `/dev/ttyS0` |
| **L298N Motor Driver** | `ENA` | Pin 32 | `GPIO 12` | Left Motors Speed (PWM) | Hardware PWM0 speed control |
| | `ENB` | Pin 33 | `GPIO 13` | Right Motors Speed (PWM) | Hardware PWM1 speed control |
| | `IN1` | Pin 29 | `GPIO 5` | Left Motor Direction 1 | Digital Output (High/Low) |
| | `IN2` | Pin 31 | `GPIO 6` | Left Motor Direction 2 | Digital Output (High/Low) |
| | `IN3` | Pin 35 | `GPIO 19` | Right Motor Direction 1 | Digital Output (High/Low) |
| | `IN4` | Pin 37 | `GPIO 26` | Right Motor Direction 2 | Digital Output (High/Low) |
| | `12V Terminal` | - | - | Motor Power Positive (+) | Connected to 11.1V battery pack (+) |
| | `GND Terminal` | Pin 20 | `GND` | Motor Power Negative (-) | Tied to 11.1V battery (-) and Pi GND |
| | `OUT1 – OUT4` | - | - | Motor Drive Terminals | Parallel pairs to left and right 12V DC motors |
| **Servo Motor (SG90/MG996R)** | `Signal (Yellow/Orange)` | Pin 12 | `GPIO 18` | Camera Pan Servo Control | Hardware PWM0 signal (50Hz / 1–2ms pulse) |
| | `VCC (Red)` | L298N 5V Out | `5V Power` | Servo Supply Rail | 5V supply with 100µF–470µF buffer capacitor |
| | `GND (Brown/Black)` | Pin 9 | `GND` | Common Ground | Connected to common system ground |
| **TPA3116D2 Audio Amp** | `VCC (+)` | - | - | Amp Power Positive (+) | Wired in parallel to 11.1V battery pack (+) |
| | `GND (-)` | Pin 25 | `GND` | Amp Power Negative (-) | Tied to 11.1V battery (-) and Pi GND |
| | `IN_L` / `IN_G` | AUX / DAC Jack | - | Audio Line Input | 3.5mm AUX jack Tip and Sleeve (or USB DAC) |
| | `OUT_L (+/-)` | Piezo Tweeter | - | High-Freq Audio Output | Piezo Horn Tweeter with 8–10Ω series resistor |

---

### 2.3 Power Distribution & Electrical Safety Topology

To prevent microcontrollers from resetting due to voltage sags and back-EMF noise generated by high-current DC motors and audio amplifiers, AgriSentinel employs a strict **isolated dual-power topology**:

1. **Pi Logic Subsystem Power:**
   * Powered independently via a dedicated 5V / 3A USB-C Power Bank directly connected to the Raspberry Pi 4 USB-C power port.
   * Isolates CPU operations, edge inference workloads, and sensor logic from inductive motor noise and voltage dips.

2. **Actuation & Audio Subsystem Power:**
   * Powered by a 3x 3.7V 18650 Li-ion battery pack in series (11.1V nominal, 12.6V peak charge).
   * Supplies power in parallel to the L298N Motor Driver `12V` input and the TPA3116D2 Audio Amplifier `VCC` terminal.

3. **Unified Grounding Scheme:**
   * All negative reference terminals—including 11.1V battery (-), Raspberry Pi GND pins (Pins 6, 9, 14, 20, 25), L298N GND terminal, and Servo GND—are connected to a single common reference ground bus.

```text
               +-------------------------------------------------------+
               |           ISOLATED DUAL-POWER ARCHITECTURE            |
               +-------------------------------------------------------+

  +-----------------------+                    +-----------------------+
  |  5V / 3A Power Bank   |                    | 11.1V Li-ion Battery  |
  +-----------+-----------+                    +-----------+-----------+
              | (USB-C)                                    |
              v                                            |
   +--------------------+                                  |
   | Raspberry Pi 4 B   |                                  |
   | (CPU & Inference)  |                                  |
   +---------+----------+                                  |
             |                                             |
    Common   | (Pi GND Pins 6, 9, 14, 20, 25)              | (11.1V + Rail)
    Ground   +--------------------+------------------------+
    Bus      |                    |                        |
             v                    v                        v
     +---------------+    +---------------+        +---------------+
     | SG90 Servo    |    | L298N Driver  |        | TPA3116D2 Amp |
     | (Camera Pan)  |    | (12V Motors)  |        | (Audio Horn)  |
     +---------------+    +---------------+        +---------------+
```

---

## 3. Technology Stack & Directory Structure

### Software Stack

* **Edge Processing (Robot):** Python 3.10+.
* **Edge Machine Learning:** Edge Impulse FOMO Model optimized for lightweight vision detection.
* **Backend Framework:** FastAPI (Python) serving REST APIs and WebSocket streams over LAN.
* **Database Layer:** SQLite (embedded single-file database).
* **Frontend GUI:** Vite + Vue.js (or HTML5 + Tailwind CSS).
* **Mobile Client:** MIT App Inventor application wrapping the responsive Web Dashboard via `WebViewer`.

### Repository Layout

```text
agrisentinel/
├── edge/
│   ├── models/
│   │   └── model.eim                # Edge Impulse FOMO binary
│   ├── drivers/
│   │   ├── __init__.py
│   │   ├── motors.py                # L298N Motor driver (GPIO 5, 6, 12, 13, 19, 26)
│   │   ├── servo.py                 # SG90/MG996R Pan-tilt servo driver (GPIO 18)
│   │   ├── ultrasonic.py            # Dual HC-SR04 Obstacle readers (Front: 23/24, Rear: 27/22)
│   │   ├── gps.py                   # GY-NEO6MV2 / GY-GPS6MV2 serial reader (/dev/ttyS0 @ 9600 baud)
│   │   └── synthesizer.py           # Dynamic adaptive audio generator
│   ├── vision.py                    # EI Linux Runner & OpenCV capture
│   ├── camera_test.py               # Local FastAPI camera preview & streaming server
│   ├── gps_test.py                  # Standalone continuous GPS diagnostic & monitor
│   └── robot_main.py                # Main autonomous control & dual failsafe loop
├── backend/
│   ├── app.py                       # FastAPI application & WebSocket handlers
│   ├── database.py                  # SQLite configuration
│   └── models.py                    # Pydantic schemas & DB models (Dual clearance & GPS tags)
├── frontend/
│   ├── index.html                   # Mobile-first web application interface
│   ├── src/                         # Dashboard UI components & WebSocket client
│   └── dist/                        # Static build files served by FastAPI
├── markdowns/
│   ├── camera_test_plan.md          # Camera subsystem specification
│   └── gps_test_plan.md             # GPS diagnostic and testing specification
├── requirements.txt                 # Project dependencies (pyserial, pynmea2, gpiozero/RPi.GPIO)
└── README.md
```

---

## 4. Edge AI, Dual Avoidance & GPS Telemetry Logic

### 4.1 Camera Pan Sweep & Vision Pipeline

1. **Servo Pan Sweep:** The camera module is mounted on an SG90/MG996R servo motor controlled via GPIO 18 PWM. During navigation and obstacle hold maneuvers, the camera automatically sweeps across angles (from $-60^\circ$ to $+60^\circ$) to provide wider field-of-view scanning for crop pests.

2. **Target Pest Classes:** `stem_borer`, `sucking_insect`, `defoliator`, `grain_storage_pest`.

3. **Detection & Repellent Trigger:** Frames captured during pan sweeps are evaluated by the Edge Impulse FOMO model. Valid pest detections trigger the dynamic frequency synthesizer matching the pest class.

### 4.2 Bidirectional Collision Failsafe Logic

Autonomous drive routines and manual overrides continuously monitor both **Front** (`GPIO 23/24`) and **Rear** (`GPIO 27/22`) ultrasonic distance sensors:
* **Forward Movement Failsafe:** If `front_obstacle_cm < 30.0 cm`, forward motion is automatically prohibited or halted.
* **Reverse Movement Failsafe:** If `rear_obstacle_cm < 30.0 cm`, reverse motion is automatically prohibited or halted.
* **Obstacle Avoidance Maneuver:** When forward traversal is blocked by an obstacle ($< 30\text{ cm}$), the robot halts, sweeps the camera pan mechanism to log target surroundings, checks rear clearance ($> 30\text{ cm}$), and performs controlled reverse path corrections.

### 4.3 GPS Telemetry Flow

The GY-NEO6MV2 / GY-GPS6MV2 GPS module streams NMEA data over Pi hardware UART `/dev/ttyS0` at 9600 baud:
* **Parsed NMEA Sentences:** `$GPGGA` (Global Positioning System Fix Data) and `$GPRMC` (Recommended Minimum Specific GPS Data).
* **Telemetry Payload Integration:** Extracted latitude, longitude, altitude, and fix status are combined with dual ultrasonic clearance metrics (`front_obstacle_cm`, `rear_obstacle_cm`) and pest detection events in real time.

### 4.4 Dynamic Frequency Modulation

Because fixed frequencies allow pests to acclimate over time, the system uses continuously changing adaptive sound frequencies to increase repellent effectiveness:

$$\text{Frequency Signal } S(t) = \sin\left(2\pi \cdot (f_0 + \Delta f \cdot \sin(2\pi f_m t)) \cdot t\right)$$

---

## 5. Implementation Sequence for Developers

### Step 1: Hardware Driver Setup (`edge/drivers/`)

* Implement `motors.py` governing L298N direction and PWM speed.
* Implement `servo.py` governing GPIO 18 PWM pan-tilt camera sweeps.
* Implement `ultrasonic.py` instantiating `FrontSensor` (GPIO 23/24) and `RearSensor` (GPIO 27/22) for bidirectional distance clearance readings.
* Implement `gps.py` using `pyserial` and `pynmea2` to stream NMEA `$GPGGA` / `$GPRMC` latitude/longitude coordinates over `/dev/ttyS0`.
* Implement `synthesizer.py` for generating dynamic high-frequency audio sweeps.

### Step 2: Main Robot Loop (`edge/robot_main.py`)

* Integrate dual ultrasonic clearance evaluation, 30 cm bidirectional collision failsafe, GPS telemetry collection, camera servo panning, and motor control into a unified main loop.

### Step 3: Inference Loop Integration (`edge/vision.py`)

* Process live frames captured via the camera stream.
* On valid AI detection, attach GPS location tags (`latitude`, `longitude`) and dispatch pest details to the dynamic synthesizer and backend WebSocket stream.

### Step 4: Backend API & Web Telemetry (`backend/app.py` & `backend/models.py`)

* Define Pydantic models for system telemetry payloads (including `front_obstacle_cm`, `rear_obstacle_cm`, `latitude`, `longitude`, `gps_fix`).
* Expose REST and WebSocket endpoints for real-time monitoring and GUI remote control.
