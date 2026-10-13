"""
AgriSentinel - Soil Moisture Sensor Driver

Supports capacitive and resistive analog soil moisture probes via:
1. I2C ADS1115 / ADS1015 ADC (Adafruit ADS1x15 / smbus)
2. SPI MCP3008 ADC (spidev)
3. Simulated Mock Sensor with realistic fluctuation (for testing on Windows/macOS/PC)
"""

import os
import time
import math
import random
import logging
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AgriSentinel-SoilMoisture")

# Configuration via environment variables
MOISTURE_DRY_THRESHOLD = float(os.getenv("MOISTURE_DRY_THRESHOLD", "25.0"))
MOISTURE_WET_THRESHOLD = float(os.getenv("MOISTURE_WET_THRESHOLD", "75.0"))
ADC_TYPE = os.getenv("SOIL_ADC_TYPE", "auto").lower()  # "ads1115", "mcp3008", "mock", "auto"

# Calibration counts (typically ~21000 in dry air, ~9500 in cup of water for ADS1115 16-bit)
ADC_AIR_VALUE = int(os.getenv("SOIL_ADC_AIR", "21000"))
ADC_WATER_VALUE = int(os.getenv("SOIL_ADC_WATER", "9500"))


class SoilMoistureSensor:
    """Analog Soil Moisture Sensor interface with automatic hardware detection and mock fallback."""

    def __init__(self, adc_type: str = ADC_TYPE):
        self.adc_type = adc_type
        self.hardware_available = False
        self.ads = None
        self.mcp = None
        self._mock_base_moisture = float(os.getenv("MOCK_SOIL_MOISTURE", "55.0"))
        self._init_hardware()

    def _init_hardware(self):
        """Attempts to initialize physical ADC interface, falling back to mock simulator."""
        if self.adc_type == "mock":
            logger.info("[SoilMoisture] Configured explicitly for Mock Simulator mode.")
            return

        # Attempt ADS1115 via adafruit_ads1x15 if installed
        try:
            import board
            import busio
            import adafruit_ads1x15.ads1115 as ADS
            from adafruit_ads1x15.analog_in import AnalogIn

            i2c = busio.I2C(board.SCL, board.SDA)
            ads_inst = ADS.ADS1115(i2c)
            self.ads = AnalogIn(ads_inst, ADS.P0)
            self.hardware_available = True
            self.adc_type = "ads1115"
            logger.info("[SoilMoisture] Physical ADS1115 ADC initialized on I2C channel A0.")
            return
        except Exception as e:
            logger.debug(f"[SoilMoisture] ADS1115 hardware not detected: {e}")

        # Attempt MCP3008 via spidev or gpiozero if installed
        try:
            from gpiozero import MCP3008
            self.mcp = MCP3008(channel=0)
            self.hardware_available = True
            self.adc_type = "mcp3008"
            logger.info("[SoilMoisture] Physical MCP3008 ADC initialized on SPI channel 0.")
            return
        except Exception as e:
            logger.debug(f"[SoilMoisture] MCP3008 hardware not detected: {e}")

        self.adc_type = "mock"
        logger.info("[SoilMoisture] No physical ADC hardware found. Running in high-fidelity Mock Simulation mode.")

    def read_moisture(self) -> Dict[str, Any]:
        """
        Reads soil moisture and calculates volumetric percentage and status classification.
        Returns:
            dict: {
                "moisture_percent": float,
                "raw_adc": Optional[int],
                "voltage": Optional[float],
                "status": str ("Dry", "Optimal", "Waterlogged"),
                "timestamp": float
            }
        """
        raw_adc = None
        voltage = None
        moisture_percent = 50.0

        if self.hardware_available and self.ads:
            try:
                raw_adc = self.ads.value
                voltage = round(self.ads.voltage, 3)
                # Capacitive probes: higher voltage/count in dry air, lower in water
                span = ADC_AIR_VALUE - ADC_WATER_VALUE
                if span != 0:
                    val = (ADC_AIR_VALUE - raw_adc) / span * 100.0
                    moisture_percent = max(0.0, min(100.0, val))
            except Exception as e:
                logger.warning(f"[SoilMoisture] Error reading ADS1115: {e}. Using fallback.")
                moisture_percent = self._simulate_reading()

        elif self.hardware_available and self.mcp:
            try:
                # MCP3008 returns a normalized value between 0.0 and 1.0
                raw_ratio = self.mcp.value
                raw_adc = int(raw_ratio * 1023)
                voltage = round(raw_ratio * 3.3, 3)
                # Map ratio to 0-100% moisture
                moisture_percent = max(0.0, min(100.0, (1.0 - raw_ratio) * 100.0))
            except Exception as e:
                logger.warning(f"[SoilMoisture] Error reading MCP3008: {e}. Using fallback.")
                moisture_percent = self._simulate_reading()

        else:
            moisture_percent = self._simulate_reading()
            raw_adc = int(ADC_AIR_VALUE - (moisture_percent / 100.0) * (ADC_AIR_VALUE - ADC_WATER_VALUE))
            voltage = round(1.2 + (moisture_percent / 100.0) * 1.8, 3)

        moisture_percent = round(moisture_percent, 1)

        # Classify status
        if moisture_percent < MOISTURE_DRY_THRESHOLD:
            status = "Dry"
        elif moisture_percent > MOISTURE_WET_THRESHOLD:
            status = "Waterlogged"
        else:
            status = "Optimal"

        return {
            "moisture_percent": moisture_percent,
            "raw_adc": raw_adc,
            "voltage": voltage,
            "status": status,
            "timestamp": time.time(),
        }

    def _simulate_reading(self) -> float:
        """Generates realistic slowly varying moisture readings around base value."""
        # Gentle oscillation +/- 2%
        drift = math.sin(time.time() / 15.0) * 2.0
        noise = random.uniform(-0.5, 0.5)
        sim_val = self._mock_base_moisture + drift + noise
        return max(0.0, min(100.0, sim_val))

    def set_mock_moisture(self, val: float):
        """Allows test runners to dynamically set mock soil moisture value."""
        self._mock_base_moisture = max(0.0, min(100.0, float(val)))

