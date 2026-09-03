"""
AgriSentinel Edge Driver - GY-NEO6MV2 / GY-GPS6MV2 GPS Module
Reads NMEA sentences ($GPGGA, $GPRMC) from /dev/ttyS0 at 9600 baud.
Compatible with both GY-NEO6MV2 and GY-GPS6MV2 (u-blox NEO-6M core) modules.
"""

import os
import logging
import time
from collections import deque
from typing import Dict, Any, Tuple, List

logger = logging.getLogger("AgriSentinel-GPS")

GPS_SERIAL_PORT = os.getenv("GPS_SERIAL_PORT", "/dev/ttyS0")
GPS_BAUD_RATE = int(os.getenv("GPS_BAUD_RATE", "9600"))


def _parse_nmea_degrees(raw_val: str, direction: str, is_lon: bool = False) -> float:
    """Converts NMEA DDMM.MMMM (or DDDMM.MMMM for lon) string to decimal degrees."""
    if not raw_val or not direction:
        return 0.0
    try:
        deg_len = 3 if is_lon else 2
        deg = float(raw_val[:deg_len])
        minutes = float(raw_val[deg_len:])
        decimal = deg + (minutes / 60.0)
        if direction.upper() in ["S", "W"]:
            decimal = -decimal
        return round(decimal, 6)
    except (ValueError, IndexError):
        return 0.0


class GPSReader:
    """GY-NEO6MV2 / GY-GPS6MV2 GPS Serial Reader and NMEA Parser with zero-dependency fallback."""

    def __init__(self, port: str = GPS_SERIAL_PORT, baudrate: int = GPS_BAUD_RATE):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.latitude = 0.0
        self.longitude = 0.0
        self.altitude = 0.0
        self.gps_fix = False
        self.satellites = 0
        self.last_raw_sentence = ""
        self.raw_buffer = deque(maxlen=20)
        self.last_valid_fix_time = 0.0
        self.is_synthetic = False

        self._init_serial()

    def _init_serial(self):
        """Initializes serial communication interface."""
        try:
            import serial
            self.serial_conn = serial.Serial(self.port, baudrate=self.baudrate, timeout=1.0)
            self.is_synthetic = False
            logger.info(f"[GPSReader] Connected to GPS module on {self.port} @ {self.baudrate} baud.")
        except Exception as e:
            self.is_synthetic = True
            logger.warning(f"[GPSReader] Hardware serial fallback (Mock Mode): {e}")

    def reconnect(self) -> bool:
        """Forces the serial port to close and reopen."""
        self.close()
        time.sleep(0.5)
        self._init_serial()
        return not self.is_synthetic

    def get_raw_nmea(self) -> List[str]:
        """Returns the most recent raw NMEA sentences buffered from the hardware."""
        return list(self.raw_buffer)

    def read_gps_data(self) -> Dict[str, Any]:
        """Reads and parses NMEA sentences ($GPGGA / $GPRMC) from serial stream."""
        if not self.serial_conn or not self.serial_conn.is_open:
            return self._get_payload()

        try:
            raw_bytes = self.serial_conn.readline()
            line = raw_bytes.decode("utf-8", errors="replace").strip() if isinstance(raw_bytes, bytes) else str(raw_bytes).strip()
            if line:
                self.last_raw_sentence = line
                self.raw_buffer.append(line)

            parsed_successfully = False
            fix_found = False

            # Try pynmea2 first if available
            try:
                import pynmea2
                if line.startswith("$GPGGA") or line.startswith("$GNGGA"):
                    msg = pynmea2.parse(line, check=False)
                    if msg.gps_qual and int(msg.gps_qual) > 0:
                        self.latitude = float(msg.latitude) if msg.latitude else 0.0
                        self.longitude = float(msg.longitude) if msg.longitude else 0.0
                        self.altitude = float(msg.altitude) if msg.altitude else 0.0
                        self.satellites = int(msg.num_sats) if msg.num_sats else 0
                        fix_found = True
                        parsed_successfully = True
                elif line.startswith("$GPRMC") or line.startswith("$GNRMC"):
                    msg = pynmea2.parse(line, check=False)
                    if msg.status == "A":
                        self.latitude = float(msg.latitude) if msg.latitude else 0.0
                        self.longitude = float(msg.longitude) if msg.longitude else 0.0
                        fix_found = True
                        parsed_successfully = True
            except (ImportError, Exception) as e:
                logger.debug(f"[GPSReader] pynmea2 parser fallback: {e}")

            # Fallback to native string parser if pynmea2 was unavailable or did not complete
            if not parsed_successfully:
                # Strip checksum if present
                content = line.split("*")[0]
                parts = content.split(",")
                header = parts[0] if len(parts) > 0 else ""

                if header in ["$GPGGA", "$GNGGA"] and len(parts) >= 10:
                    qual = parts[6]
                    if qual and qual != "0":
                        self.latitude = _parse_nmea_degrees(parts[2], parts[3], is_lon=False)
                        self.longitude = _parse_nmea_degrees(parts[4], parts[5], is_lon=True)
                        self.satellites = int(parts[7]) if parts[7].isdigit() else 0
                        self.altitude = float(parts[9]) if parts[9] else 0.0
                        fix_found = True

                elif header in ["$GPRMC", "$GNRMC"] and len(parts) >= 7:
                    status = parts[2]
                    if status == "A":
                        self.latitude = _parse_nmea_degrees(parts[3], parts[4], is_lon=False)
                        self.longitude = _parse_nmea_degrees(parts[5], parts[6], is_lon=True)
                        fix_found = True

            if fix_found:
                self.gps_fix = True
                self.last_valid_fix_time = time.time()
            elif time.time() - self.last_valid_fix_time > 5.0:
                self.gps_fix = False

        except Exception as e:
            logger.debug(f"[GPSReader] Parse error: {e}")

        return self._get_payload()

    def _get_payload(self) -> Dict[str, Any]:
        """Returns current GPS telemetry payload dictionary."""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "gps_fix": self.gps_fix,
            "satellites": self.satellites,
            "raw_sentence": self.last_raw_sentence,
        }

    def close(self):
        """Closes serial connection."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
                logger.info("[GPSReader] Serial connection closed.")
            except Exception:
                pass


if __name__ == "__main__":
    from edge.gps_test import main
    main()
