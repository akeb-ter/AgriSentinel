# Motor Driver Test Plan & Specification (v1.0)

## 1. Overview & Objectives
This document specifies the verification plan, hardware wiring, and directional logic for the **L298N Dual H-Bridge Motor Driver** governing the AgriSentinel 4WD chassis.

### Hardware Details:
- **Motor Driver:** L298N Dual H-Bridge
- **Actuators:** 4x 12V DC Gear Motors (Left pair on OUT1/OUT2, Right pair on OUT3/OUT4)
- **Power Supply:** 3S Li-ion Battery Pack (11.1V nominal, 12.6V peak) connected to L298N `12V` and `GND` terminals
- **Grounding:** Common Ground Bus tied between battery negative (-), L298N GND, and Raspberry Pi GND pins.

---

## 2. 5V Jumper Configuration (ENA / ENB)

To optimize Raspberry Pi pin allocation and ensure consistent full-torque drive:
- **`ENA` (Left Enable)**: Fitted with physical 5V onboard jumper cap (100% full speed).
- **`ENB` (Right Enable)**: Fitted with physical 5V onboard jumper cap (100% full speed).
- **Raspberry Pi Pins Saved:** GPIO 12 (Pin 32) and GPIO 13 (Pin 33) are freed from PWM requirements.

---

## 3. Raspberry Pi 4 Pinout Reference

| L298N Terminal | Raspberry Pi Pin | GPIO Port | Signal / Purpose | Logic Level |
| :--- | :--- | :--- | :--- | :--- |
| **`ENA` / `ENB`** | - | `5V Jumper` | Hardware Motor Enable (Full Speed) | 5V Onboard Jumper |
| **`IN1`** | Pin 29 | `GPIO 5` | Left Motor Forward Control | 3.3V Logic Digital Output |
| **`IN2`** | Pin 31 | `GPIO 6` | Left Motor Reverse Control | 3.3V Logic Digital Output |
| **`IN3`** | Pin 35 | `GPIO 19` | Right Motor Forward Control | 3.3V Logic Digital Output |
| **`IN4`** | Pin 37 | `GPIO 26` | Right Motor Reverse Control | 3.3V Logic Digital Output |
| **`12V Terminal`** | - | - | 11.1V Battery Positive (+) | Direct to 3S Battery (+) |
| **`GND Terminal`** | Pin 20 (or 6, 9, 14, 25) | `GND` | Common Reference Ground | Tied to Battery (-) & Pi GND |

---

## 4. Directional Logic Matrix

The 4WD chassis supports both zero-radius skid-steer spin maneuvers and pivot turns:

| Maneuver | `IN1` (GPIO 5) | `IN2` (GPIO 6) | `IN3` (GPIO 19) | `IN4` (GPIO 26) | State Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`FORWARD`** | `HIGH` | `LOW` | `HIGH` | `LOW` | Left wheels FWD, Right wheels FWD |
| **`BACKWARD`** | `LOW` | `HIGH` | `LOW` | `HIGH` | Left wheels REV, Right wheels REV |
| **`SPIN_LEFT` (Default Left)** | `HIGH` | `LOW` | `LOW` | `HIGH` | Left wheels FWD, Right wheels REV (Zero-radius spin left) |
| **`SPIN_RIGHT` (Default Right)**| `LOW` | `HIGH` | `HIGH` | `LOW` | Left wheels REV, Right wheels FWD (Zero-radius spin right) |
| **`PIVOT_LEFT`** | `HIGH` | `LOW` | `LOW` | `LOW` | Left wheels FWD, Right wheels STOP (Pivot turn left) |
| **`PIVOT_RIGHT`** | `LOW` | `LOW` | `HIGH` | `LOW` | Left wheels STOP, Right wheels FWD (Pivot turn right) |
| **`STOP`** | `LOW` | `LOW` | `LOW` | `LOW` | All motors de-energized |

---

## 5. Verification & Test Execution

### 5.1 Automated Unit Tests
Verify driver logic, mock GPIO state transitions, and edge cases:
```bash
python tests/test_motors.py
```
*or via discover:*
```bash
python -m unittest discover -s tests -p "test_motors.py"
```

### 5.2 Standalone Hardware Test Sequence
Run the timed multi-directional test sequence on the physical robot:
```bash
python -m edge.drivers.motors
```

#### Test Sequence Steps:
1. **Forward Motion:** Drives forward for 2.0 seconds -> Stops for 1.0 second.
2. **Backward Motion:** Drives reverse for 2.0 seconds -> Stops for 1.0 second.
3. **Left Spin:** Spins counter-clockwise for 2.0 seconds -> Stops for 1.0 second.
4. **Right Spin:** Spins clockwise for 2.0 seconds -> Stops for 1.0 second.
5. **Pivot Left:** Pivots around stopped left wheel for 1.0 second -> Stops for 0.5 seconds.
6. **Pivot Right:** Pivots around stopped right wheel for 1.0 second -> Stops for 0.5 seconds.
7. **Final Safe Shutdown:** Ensures all directional pins are pulled LOW and releases GPIO resources.

---

## 6. Bench Testing Safety Checklist
- [ ] **Chassis Elevation:** Place robot chassis on a stand so all 4 drive wheels spin freely in the air.
- [ ] **Jumpers Fitted:** Check that both `ENA` and `ENB` headers have jumper caps securely attached to 5V.
- [ ] **Ground Reference:** Ensure common ground is securely connected between L298N `GND` and Raspberry Pi `GND`.
- [ ] **Dual Power Isolation:** Ensure Raspberry Pi logic is powered via USB-C power bank and motors are powered via 11.1V Li-ion pack.

