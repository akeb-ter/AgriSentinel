import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from edge.drivers.gps import GPSReader


def compute_nmea_checksum(sentence_body: str) -> str:
    """Computes standard XOR NMEA checksum hex string for a sentence without $ or *."""
    c = 0
    for char in sentence_body:
        c ^= ord(char)
    return f"{c:02X}"


def format_nmea(sentence_body: str) -> bytes:
    """Formats a full valid NMEA sentence with leading $ and trailing *<CHECKSUM>\n."""
    chk = compute_nmea_checksum(sentence_body)
    return f"${sentence_body}*{chk}\n".encode("utf-8")


class TestGPSReader(unittest.TestCase):
    """Test suite for GPSReader driver class."""

    def setUp(self):
        import logging
        self.logger = logging.getLogger("AgriSentinel-GPS")
        self.original_level = self.logger.level
        self.logger.setLevel(logging.CRITICAL)

    def tearDown(self):
        self.logger.setLevel(self.original_level)

    def test_gps_reader_mock_fallback_mode(self):
        """Verify GPSReader returns mock/default telemetry when serial interface is unavailable."""
        reader = GPSReader(port="/dev/nonexistent_port", baudrate=9600)
        self.assertIsNone(reader.serial_conn)

        data = reader.read_gps_data()
        self.assertEqual(data["latitude"], 0.0)
        self.assertEqual(data["longitude"], 0.0)
        self.assertEqual(data["altitude"], 0.0)
        self.assertFalse(data["gps_fix"])
        self.assertEqual(data["satellites"], 0)

    def test_gps_reader_gpgga_sentence_parsing(self):
        """Verify parsing of valid $GPGGA NMEA sentences with exact checksum (*40)."""
        reader = GPSReader(port="/dev/ttyS0", baudrate=9600)

        # Coordinates: 14.5995 N, 120.9842 E (Manila), 8 satellites, fix=1, alt=545.4m
        gpgga_line = format_nmea("GPGGA,123519,1435.9700,N,12059.0520,E,1,08,0.9,545.4,M,46.9,M,,")
        self.assertTrue(gpgga_line.endswith(b"*40\n"))

        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.readline.side_effect = [gpgga_line, b""]
        reader.serial_conn = mock_serial

        data = reader.read_gps_data()

        self.assertTrue(data["gps_fix"])
        self.assertEqual(data["satellites"], 8)
        self.assertAlmostEqual(data["altitude"], 545.4, places=1)
        self.assertAlmostEqual(data["latitude"], 14.5995, places=4)
        self.assertAlmostEqual(data["longitude"], 120.9842, places=4)

    def test_gps_reader_gprmc_sentence_parsing(self):
        """Verify parsing of valid $GPRMC NMEA sentences with exact checksum (*6D)."""
        reader = GPSReader(port="/dev/ttyS0", baudrate=9600)

        # Active status "A", Coordinates: 14.5995 N, 120.9842 E
        gprmc_line = format_nmea("GPRMC,123519,A,1435.9700,N,12059.0520,E,022.4,084.4,230394,003.1,W")
        self.assertTrue(gprmc_line.endswith(b"*6D\n"))

        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.readline.side_effect = [gprmc_line, b""]
        reader.serial_conn = mock_serial

        data = reader.read_gps_data()

        self.assertTrue(data["gps_fix"])
        self.assertAlmostEqual(data["latitude"], 14.5995, places=4)
        self.assertAlmostEqual(data["longitude"], 120.9842, places=4)

    def test_gps_reader_malformed_nmea_handling(self):
        """Verify graceful handling of corrupt or malformed serial NMEA data."""
        reader = GPSReader(port="/dev/ttyS0", baudrate=9600)

        corrupt_line = b"$GPGGA,CORRUPT,INVALID_DATA,,,,\n"

        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.readline.return_value = corrupt_line
        reader.serial_conn = mock_serial

        # Should not raise exception
        data = reader.read_gps_data()
        self.assertIsInstance(data, dict)
        self.assertIn("latitude", data)
        self.assertIn("longitude", data)

    def test_gps_reader_close_connection(self):
        """Verify close method properly terminates serial connection."""
        reader = GPSReader(port="/dev/ttyS0", baudrate=9600)
        mock_serial = MagicMock()
        mock_serial.is_open = True
        reader.serial_conn = mock_serial

        reader.close()
        mock_serial.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
