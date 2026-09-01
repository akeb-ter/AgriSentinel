"""
Unit tests for edge.drivers.gps module (GY-NEO6MV2 GPS Driver).
Uses standard unittest framework for maximum compatibility.
"""

import unittest
from unittest.mock import MagicMock

from edge.drivers.gps import GPSReader


class TestGPSReader(unittest.TestCase):
    """Test suite for GPSReader driver class."""

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
        """Verify parsing of valid $GPGGA NMEA sentences."""
        reader = GPSReader(port="/dev/ttyS0", baudrate=9600)

        # Simulated NMEA stream with a valid $GPGGA sentence
        # Coordinates: 14.5995 N, 120.9842 E (Manila), 8 satellites, fix=1
        gpgga_line = b"$GPGGA,123519,1435.9700,N,12059.0520,E,1,08,0.9,545.4,M,46.9,M,,*47\n"

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
        """Verify parsing of valid $GPRMC NMEA sentences."""
        reader = GPSReader(port="/dev/ttyS0", baudrate=9600)

        # Simulated NMEA stream with a valid $GPRMC sentence (status "A" = Active)
        gprmc_line = b"$GPRMC,123519,A,1435.9700,N,12059.0520,E,022.4,084.4,230394,003.1,W*6A\n"

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

