# Camera Pan Servo Test Plan & Specification (v1.0)

## 1. Overview & Objectives
This document specifies the verification plan, hardware pinout, PWM control parameters, and test sequences for the **Camera Pan Servo Mechanism** (`SG90` / `MG996R`) on the AgriSentinel robot.

The pan servo rotates the camera module across the front quadrant ($-60^\circ$ to $+60^\circ$) to expand field-of-view scanning for crop pests during autonomous navigation and obstacle hold maneuvers.

---

## 2. Raspberry Pi 4 Pinout Reference

| Servo Lead | Wire Color | Raspberry Pi Pin | GPIO / Port | Signal / Purpose | Electrical Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`Signal`** | Yellow / Orange | **Pin 12** | **`GPIO 18`** | Hardware PWM0 Signal | 3.3V Logic 50Hz PWM pulse train |
| **`VCC`** | Red | Pin 2 or Pin 4 (or L298N 5V Out) | `5V Power` | Servo Power Supply Rail | 5V rail (buffer capacitor 100µF–470µF recommended) |
| **`GND`** | Brown / Black | Pin 6, Pin 9, Pin 14, or Pin 20 | `GND` | Common Ground | Tied to Raspberry Pi common ground bus |

---

## 3. PWM Timing & Angular Control Parameters

Standard analog and digital hobby servos expect a **50 Hz** PWM frequency (20.0 ms period):

$$\text{Period } T = \frac{1}{50\text{ Hz}} = 20.0\text{ ms}$$

| Position | Physical Angle | Pulse Width | Duty Cycle (50Hz) | Operational Description |
| :--- | :---: | :---: | :---: | :--- |
| **Full Mechanical Min** | $-90^\circ$ | 0.5 ms | 2.50% | Extreme hardware limit (unused) |
| **Software Min Limit** | **$-60^\circ$** | **0.83 ms** | **4.17%** | **Camera Pan Far Left Limit** |
| **Center / Default** | **$0^\circ$** | **1.50 ms** | **7.50%** | **Camera Facing Straight Forward** |
| **Software Max Limit** | **$+60^\circ$** | **2.17 ms** | **10.83%** | **Camera Pan Far Right Limit** |
| **Full Mechanical Max** | $+90^\circ$ | 2.5 ms | 12.50% | Extreme hardware limit (unused) |

### 3.1 Jitter & Buzzing Mitigation
Servos (especially SG90 and MG996R) frequently hum, buzz, and overheat when a continuous PWM pulse train is sent while the horn is stationary under zero mechanical load.
- **Solution:** The driver implements `servo.detach()`, which sets the PWM signal to `None` / 0 duty cycle after completing movements.
- This allows the servo gearbox to hold position passively without thermal stress, buzzing noise, or battery drain.

---

## 4. Verification & Test Execution

### 4.1 Automated Unit Tests
Verifies angular clamping ($-60^\circ$ to $+60^\circ$), centering, bidirectional sweep step reversal, and PWM detachment:
```bash
python tests/test_servo.py
```

### 4.2 Standalone Hardware Calibration Sequence
Executes the timed multi-point calibration routine on the physical robot:
```bash
python -m edge.drivers.servo
```

#### Calibration Sequence Steps:
1. **Step 1 (Center):** Drives servo horn to $0^\circ$ (straight ahead) $\rightarrow$ Holds for 1.5 seconds.
2. **Step 2 (Far Left):** Rotates to $-60^\circ$ $\rightarrow$ Holds for 1.5 seconds.
3. **Step 3 (Re-Center):** Returns to $0^\circ$ $\rightarrow$ Holds for 1.0 second.
4. **Step 4 (Far Right):** Rotates to $+60^\circ$ $\rightarrow$ Holds for 1.5 seconds.
5. **Step 5 (Smooth Pan Sweep):** Steps across $-60^\circ \rightarrow +60^\circ$ in $5^\circ$ increments, returns to $0^\circ$.
6. **Step 6 (Safe Detach):** Ceases PWM output to eliminate idle buzzing, releases GPIO resources.

### 4.3 Autonomous Loop Integration Test
Verifies camera pan sweeps simultaneously during autonomous navigation:
```bash
python -m edge.robot_main
```

---

## 5. Bench Testing Safety Checklist
- [ ] **Horn Alignment:** Ensure the servo horn is mounted such that $0^\circ$ aligns with the camera pointing straight forward.
- [ ] **Wire Clearance:** Ensure the camera CSI ribbon cable and USB wires have sufficient slack to sweep $-60^\circ$ to $+60^\circ$ without tension or snagging.
- [ ] **Independent 5V Rail:** Confirm servo VCC is powered from a stable 5V rail (not back-powering from 3.3V logic pins).
- [ ] **Common Ground:** Confirm servo ground is tied to Raspberry Pi ground.

