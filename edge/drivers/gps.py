"""
AgriSentinel Edge Driver - GY-NEO6MV2 GPS Module
Reads NMEA sentences ($GPGGA, $GPRMC) from /dev/ttyS0 at 9600 baud.
"""

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("AgriSentinel-GPS")

GPS_SERIAL_PORT = os.getenv("GPS_SERIAL_PORT", "/dev/ttyS0")
GPS_BAUD_RATE = int(os.getenv("GPS_BAUD_RATE", "9600"))


class GPSReader:
    """GY-NEO6MV2 GPS Serial Reader and NMEA Parser."""

    def __init__(self, port: str = GPS_SERIAL_PORT, baudrate: int = GPS_BAUD_RATE):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.latitude = 0.0
        self.longitude = 0.0
        self.altitude = 0.0
        self.gps_fix = False
        self.satellites = 0

        self._init_serial()

    def _init_serial(self):
        """Initializes serial communication interface."""
        try:
            import serial
            self.serial_conn = serial.Serial(self.port, baudrate=self.baudrate, timeout=1.0)
            logger.info(f"[GPSReader] Connected to GPS module on {self.port} @ {self.baudrate} baud.")
        except Exception as e:
            logger.warning(f"[GPSReader] Hardware serial fallback (Mock Mode): {e}")

    def read_gps_data(self) -> Dict[str, Any]:
        """Reads and parses NMEA sentences ($GPGGA / $GPRMC) from serial stream."""
        if not self.serial_conn or not self.serial_conn.is_open:
            # Fallback mock GPS data for non-Raspberry Pi / indoor testing
            return {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "altitude": self.altitude,
                "gps_fix": self.gps_fix,
                "satellites": self.satellites,
            }

        try:
            import pynmea2
            line = self.serial_conn.readline().decode("utf-8", errors="replace").strip()

            if line.startswith("$GPGGA") or line.startswith("$GNGGA"):
                msg = pynmea2.parse(line)
                if msg.gps_qual and int(msg.gps_qual) > 0:
                    self.latitude = msg.latitude
                    self.longitude = msg.longitude
                    self.altitude = float(msg.altitude) if msg.altitude else 0.0
                    self.satellites = int(msg.num_sats) if msg.num_sats else 0
                    self.gps_fix = True

            elif line.startswith("$GPRMC") or line.startswith("$GNRMC"):
                msg = pynmea2.parse(line)
                if msg.status == "A":
                    self.latitude = msg.latitude
                    self.longitude = msg.longitude
                    self.gps_fix = True

        except Exception as e:
            logger.debug(f"[GPSReader] Parse error: {e}")

        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "gps_fix": self.gps_fix,
            "satellites": self.satellites,
        }

    def close(self):
        """Closes serial connection."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
                logger.info("[GPSReader] Serial connection closed.")
            except Exception:
                pass

