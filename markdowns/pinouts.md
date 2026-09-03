# AgriSentinel - Hardware Pinouts & Wiring Guide

Complete hardware pinout reference and GPIO mapping for the AgriSentinel autonomous robot chassis.

---

## 📍 Raspberry Pi 4 GPIO Pinout Summary

| Physical Pin | BCM / GPIO | Component | Function | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Pin 1** | `3.3V` | GPS Module | `VCC` | 3.3V Power Supply |
| **Pin 2** | `5V` | Servo / Drivers | `VCC` | 5V Power Supply Rail |
| **Pin 8** | `GPIO 14` | GPS Module | `RX` | UART Transmit (Pi TX -> GPS RX) |
| **Pin 10** | `GPIO 15` | GPS Module | `TX` | UART Receive (Pi RX <- GPS TX) |
| **Pin 12** | `GPIO 18` | Servo Motor | `Signal` | Hardware PWM0 Camera Pan Control |
| **Pin 14** | `GND` | GPS Module | `GND` | Ground Connection |
| **Pin 20** | `GND` | Motor Driver | `GND` | Ground Connection |
| **Pin 29** | `GPIO 5` | L298N H-Bridge | `IN1` | Left Motor Forward |
| **Pin 31** | `GPIO 6` | L298N H-Bridge | `IN2` | Left Motor Reverse |
| **Pin 35** | `GPIO 19` | L298N H-Bridge | `IN3` | Right Motor Forward |
| **Pin 37** | `GPIO 26` | L298N H-Bridge | `IN4` | Right Motor Reverse |

---

## ⚙️ 1. Motor Driver (`L298N Dual H-Bridge`)

Controls directional movement for the 4WD chassis.

* **`ENA` / `ENB`**: Jumpered to onboard 5V pins (100% full speed duty cycle, freeing Pi PWM pins).
* **`IN1`**: Physical Pin 29 (`GPIO 5`) - Left Motor Forward
* **`IN2`**: Physical Pin 31 (`GPIO 6`) - Left Motor Reverse
* **`IN3`**: Physical Pin 35 (`GPIO 19`) - Right Motor Forward
* **`IN4`**: Physical Pin 37 (`GPIO 26`) - Right Motor Reverse
* **`GND`**: Physical Pin 20 (or any GND) connected to Common Ground Bus

---

## 🔭 2. Camera Pan Servo (`SG90` / `MG996R`)

Governs the camera pan-tilt scanning mechanism using Hardware PWM0.

* **`Signal` (Yellow/Orange)**: Physical Pin 12 (`GPIO 18`)
* **`VCC` (Red)**: 5V Supply Rail (Pin 2, Pin 4, or L298N 5V Out)
* **`GND` (Brown/Black)**: Common Ground Bus (Pin 6, Pin 9, Pin 14, or Pin 20)

---

## 🛰️ 3. GPS Module (`GY-NEO6MV2` / `GY-GPS6MV2`)

Streams NMEA sentence data over hardware UART `/dev/ttyS0` at 9600 baud.

* **`VCC`**: Physical Pin 1 (3.3V)
* **`GND`**: Physical Pin 14 (Ground)
* **`TX`**: Physical Pin 10 (`GPIO 15` / `RXD0`)
* **`RX`**: Physical Pin 8 (`GPIO 14` / `TXD0`)

> [!NOTE]
> Hardware serial must be enabled on the Raspberry Pi by adding `enable_uart=1` to `/boot/config.txt` (or `/boot/firmware/config.txt`).

---

## ⚡ Common Power & Ground Distribution

* **Common Ground Bus**: All grounds (Raspberry Pi GND, L298N GND, Servo GND, GPS GND) **MUST** be connected to a shared common ground to ensure signal integrity and prevent noise/floating pins.
* **External Power**: Motors and high-torque servos should be powered by an external battery pack (e.g. 7.4V - 12V Li-Ion / LiPo) routed through the L298N power terminal or a step-down buck converter to avoid drawing excessive current from the Raspberry Pi GPIO 5V rail.

