# GPS Module Test Plan & Diagnostic Specification (v1.0)

## 1. Overview & Objectives
This document specifies the verification, continuous monitoring, and troubleshooting procedures for the **GY-NEO6MV2 / GY-GPS6MV2** GPS module on the AgriSentinel robot.

The GPS subsystem streams live NMEA sentences ($GPGGA, $GPRMC) over the Raspberry Pi 4 hardware UART interface (`/dev/ttyS0`) at 9600 baud to timestamp and geographically tag crop pest detections and autonomous navigation events.

---

## 2. Raspberry Pi 4 Hardware Wiring Reference

| GPS Pin | Wire Color | Raspberry Pi Pin | GPIO / Port | Signal / Purpose | Logic & Connection Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`VCC`** | Red | **Pin 1** *(or Pin 2)* | `3.3V Power` *(or 5V)* | GPS Module Power | GY-NEO6MV2 has an onboard 3.3V LDO regulator |
| **`GND`** | Black | **Pin 6, 9, 14, 20** | `GND` | Common Ground | Tied to Raspberry Pi common ground bus |
| **`TX`** | Yellow / Blue | **Pin 10** | **`GPIO 15`** (`RXD0`) | Serial Data In to Pi | **GPS Transmit $\rightarrow$ Pi Receive** |
| **`RX`** | Green / White | **Pin 8** | **`GPIO 14`** (`TXD0`) | Serial Data Out from Pi | **Pi Transmit $\rightarrow$ GPS Receive** (optional) |

> **IMPORTANT WIRING NOTE:** 
> Always cross TX and RX: the **GPS TX** pin must connect to the **Raspberry Pi RX (Pin 10 / GPIO 15)**.

---

## 3. Standalone Continuous Diagnostic Tool (`edge/gps_test.py`)

The standalone test script runs in an **infinite continuous loop** that displays live satellite count, coordinates, altitude, fix status, and raw NMEA sentences. It runs non-stop and is **stopped only by pressing `Ctrl + C`**.

### 3.1 Running the Continuous Test

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

### 3.2 CLI Options & Flags

| Flag | Long Option | Default | Description |
| :--- | :--- | :--- | :--- |
| `-p` | `--port` | `/dev/ttyS0` | Serial port device path (e.g. `/dev/ttyS0`, `/dev/serial0`, or `COM3`) |
| `-b` | `--baud` | `9600` | Serial baud rate |
| `-i` | `--interval` | `1.0` | Telemetry refresh interval in seconds |
| `-r` | `--raw` | `False` | Verbose mode: prints incoming raw NMEA sentences for debugging |

#### Example: Verbose Raw NMEA Debugging
```bash
python edge/gps_test.py --raw --interval 0.5
```

---

## 4. Hardware Verification & Troubleshooting Checklist

### 4.1 Raspberry Pi 4 UART Configuration
1. **Enable Hardware UART:**
   Add `enable_uart=1` to `/boot/config.txt` (or `/boot/firmware/config.txt` on Bookworm):
   ```text
   enable_uart=1
   ```
2. **Disable Serial Console (Frees `/dev/ttyS0` for GPS data):**
   ```bash
   sudo raspi-config
   ```
   Navigate to: `Interface Options` $\rightarrow$ `Serial Port`
   - *Would you like a login shell over serial?* $\rightarrow$ **No**
   - *Would you like the serial port hardware enabled?* $\rightarrow$ **Yes**
   - Reboot the Raspberry Pi: `sudo reboot`
3. **Check User Permissions:**
   Ensure your user belongs to the `dialout` group:
   ```bash
   sudo usermod -a -G dialout $USER
   ```

### 4.2 Module LED Indicators & Satellite Lock
- **LED Off:** Power is disconnected or voltage is below 3.0V.
- **LED Solid ON:** GPS module is powered on and actively searching for satellites, but **no 3D satellite lock yet**.
- **LED Blinking (Once per second):** **3D Satellite Fix is acquired!** Valid latitude and longitude are now locked.

### 4.3 Antenna Positioning
- The small square ceramic patch antenna must have its metal surface facing **upwards toward the open sky**.
- Initial **Cold Start** takes **1 to 3 minutes** under open sky.
- Testing indoors or near thick concrete walls can prevent satellite reception. If testing indoors, position the antenna on a window ledge facing the sky.

---

## 5. Automated Unit Tests
To verify the NMEA checksum generator, sentence parser ($GPGGA, $GPRMC), and fallback handlers:
```bash
python tests/test_gps.py
```

