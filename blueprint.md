# BLUEPRINT.md - AgriSentinel System Specification

This document serves as the technical master plan and implementation blueprint for **AgriSentinel**, an AI-assisted autonomous crop protection robot utilizing species-specific adaptive frequency repellent technology[cite: 1]. It is structured for direct ingestion by developers and AI coding agents.

---

## 1. Project Objectives & Requirements Mapping

| Paper Objective | Feature Requirement | Implementation Details |
| :--- | :--- | :--- |
| **Obj 2.1: Manage user information**[cite: 1] | User Profile & Login | Hardcoded single-user authentication (`admin`/`password123`) storing session token in `localStorage`. Simple profile management view[cite: 1]. |
| **Obj 2.2: Monitor detected pests**[cite: 1] | Real-time Detection Feed | Live telemetry logging detected pest classes (*stem borers*, *sucking insects*, *defoliators*, *grain/storage pests*) with timestamp and confidence score[cite: 1, 2]. |
| **Obj 2.3: Pest notifications**[cite: 1] | Alert Engine | WebSocket push notifications triggered instantly when a target pest is detected[cite: 1]. |
| **Obj 2.4: Monitor robot status**[cite: 1] | System Telemetry Dashboard | Status indicator showing motor state (moving/stopped), obstacle clearance (ultrasonic distance), and active AI pipeline[cite: 1]. |
| **Obj 2.5: Monitor repellent system**[cite: 1] | Audio Output Telemetry | Live display of the active dynamic frequency signal (in Hz) emitted by the audio system[cite: 1]. |
| **Obj 2.6: Activate and control**[cite: 1] | Remote Control Interface | GUI controls (Forward, Reverse, Left, Right, Stop, Auto/Manual Toggle, Frequency Override) sent via WebSockets/HTTP[cite: 1]. |

---

## 2. System Hardware & Electronics Architecture

### Component Breakdown

* **Primary Controller:** Raspberry Pi 4[cite: 1].
* **Vision Capture:** Camera Module[cite: 1].
* **Obstacle Detection:** Ultrasonic Sensor for autonomous collision avoidance[cite: 1].
* **Actuation:** Motor Driver governing DC Motors attached to the chassis wheels[cite: 1].
* **Audio Output:** Audio Amplifier Module connected to a high-frequency speaker capable of generating dynamic sweeps[cite: 1].

---

## 3. Technology Stack & Directory Structure

### Software Stack

* **Edge Processing (Robot):** Python[cite: 1].
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
│   │   ├── motors.py                # Motor PWM driver
│   │   ├── ultrasonic.py            # Obstacle reader
│   │   └── synthesizer.py           # Dynamic adaptive audio generator
│   ├── vision.py                    # EI Linux Runner & OpenCV capture
│   └── robot_main.py                # Main autonomous control loop
├── backend/
│   ├── app.py                       # FastAPI application & WebSocket handlers
│   ├── database.py                  # SQLite configuration
│   └── models.py                    # Pydantic schemas & DB models
├── frontend/
│   ├── index.html                   # Mobile-first web application interface
│   ├── src/                         # Dashboard UI components & WebSocket client
│   └── dist/                        # Static build files served by FastAPI
└── README.md

```

---

## 4. Edge AI & Adaptive Repellent Logic

### ML Pipeline (Edge Impulse)

1. **Target Pest Classes:** `stem_borer`, `sucking_insect`, `defoliator`, `grain_storage_pest`.

2. **Detection Logic:** Executed on live camera frame capture. Valid detections trigger the species-specific sound mapping.

### Dynamic Frequency Modulation

Because fixed frequencies allow pests to acclimate over time, the system uses continuously changing adaptive sound frequencies to increase repellent effectiveness.

$$\text{Frequency Signal } S(t) = \sin\left(2\pi \cdot (f_0 + \Delta f \cdot \sin(2\pi f_m t)) \cdot t\right)$$

---

## 5. Implementation Sequence for Developers

### Step 1: Hardware Driver Setup (`edge/drivers/`)

* Implement motor driving logic for autonomous movement.

* Implement obstacle detection using ultrasonic sensors to prevent field collisions.

* Implement audio generation to emit species-specific frequency sweeps.

### Step 2: Inference Loop Integration (`edge/vision.py`)

* Process frames captured via the camera.

* On valid AI detection, dispatch pest details to the dynamic synthesizer and send a JSON payload to the backend.

### Step 3: Backend API & Telemetry (`backend/app.py`)

* Create a database table for tracking detections.

* Expose endpoints for login, user data, historical detections, and WebSocket telemetry mapping to specific system monitors.

### Step 4: Web Dashboard & Mobile APK (`frontend/`)

* Build a responsive single-page application mapping to the GUI objectives.

* Setup MIT App Inventor using a `WebViewer` pointing to the local backend server for the mobile application build.
