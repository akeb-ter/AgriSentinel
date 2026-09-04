"""
AgriSentinel Edge Driver - Piezo Transducer / Frequency Deterrent Controller

Governs acoustic and ultrasonic frequency emission (e.g., 1 kHz - 28 kHz)
using an N-Channel MOSFET driver connected to a Raspberry Pi Hardware PWM pin
(default: GPIO 13 / Physical Pin 33 / Hardware PWM1 Channel 1).

Supports:
1. gpiozero PWMOutputDevice (Preferred on Raspberry Pi OS Bookworm & Bullseye)
2. Synthetic / Mock fallback when running in testing or off-Pi environments.
3. Frequency sweep generation, single-tone bursts, and fail-safe zero-duty gate shutoff.
"""

import os
import sys
import time
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger("AgriSentinel-Piezo")

# Pin & Frequency Defaults
PIEZO_GPIO_PIN = int(os.getenv("PIEZO_GPIO_PIN", "13"))  # BCM GPIO 13 (Physical Pin 33)
DEFAULT_FREQUENCY = int(os.getenv("PIEZO_DEFAULT_FREQ", "20000"))  # 20 kHz ultrasonic default


class PiezoBuzzer:
    """Piezo Buzzer & Ultrasonic Transducer Controller with MOSFET PWM Gate Driver."""

    def __init__(self, pin: int = PIEZO_GPIO_PIN, default_frequency: int = DEFAULT_FREQUENCY):
        self.pin = pin
        self.frequency = default_frequency
        self.duty_cycle = 0.0
        self.is_synthetic = False
        self.backend = "SYNTHETIC"
        self._device: Optional[Any] = None

        self._init_driver()

    def _init_driver(self):
        """Initializes hardware PWM via gpiozero PWMOutputDevice or falls back to synthetic mode."""
        try:
            from gpiozero import PWMOutputDevice

            # Initialize with initial_value=0 (MOSFET Gate pulled LOW)
            self._device = PWMOutputDevice(
                self.pin,
                active_high=True,
                initial_value=0.0,
                frequency=self.frequency,
            )
            self.backend = "gpiozero.PWMOutputDevice"
            self.is_synthetic = False
            logger.info(
                f"[PiezoBuzzer] Initialized hardware PWM on GPIO {self.pin} "
                f"at {self.frequency} Hz (Backend: {self.backend})."
            )
        except Exception as e:
            self.is_synthetic = True
            self.backend = "SYNTHETIC"
            self._device = None
            logger.warning(
                f"[PiezoBuzzer] Hardware PWM unavailable on GPIO {self.pin}: {e}. "
                "Operating in SYNTHETIC MOCK MODE."
            )

    @property
    def is_active(self) -> bool:
        """Returns True if the PWM signal is actively driving the gate (duty cycle > 0)."""
        return self.duty_cycle > 0.0

    def start(self, frequency: Optional[int] = None, duty_cycle: float = 0.5):
        """
        Starts emitting continuous frequency signal.
        
        :param frequency: Frequency in Hertz (if None, uses current frequency).
        :param duty_cycle: PWM duty cycle between 0.0 and 1.0 (default: 0.5 for square wave).
        """
        if frequency is not None:
            self.set_frequency(frequency)

        duty_cycle = max(0.0, min(1.0, float(duty_cycle)))
        self.duty_cycle = duty_cycle

        if not self.is_synthetic and self._device is not None:
            try:
                self._device.value = duty_cycle
            except Exception as e:
                logger.error(f"[PiezoBuzzer] Failed to set PWM duty cycle: {e}")
        else:
            logger.debug(f"[PiezoBuzzer MOCK] Emit @ {self.frequency} Hz, duty={duty_cycle:.2f}")

    def stop(self):
        """
        Immediately drives the MOSFET gate LOW (duty cycle 0.0) to shut off power.
        Crucial for preventing continuous DC current through the transducer.
        """
        self.duty_cycle = 0.0
        if not self.is_synthetic and self._device is not None:
            try:
                self._device.value = 0.0
            except Exception as e:
                logger.error(f"[PiezoBuzzer] Error driving gate low: {e}")
        else:
            logger.debug("[PiezoBuzzer MOCK] Output stopped (Gate pulled LOW).")

    def set_frequency(self, frequency: int):
        """
        Adjusts the PWM frequency in Hertz.
        
        :param frequency: Target frequency in Hz (e.g., 1000 - 30000).
        """
        if frequency <= 0:
            raise ValueError("Frequency must be a positive integer.")

        self.frequency = int(frequency)

        if not self.is_synthetic and self._device is not None:
            try:
                self._device.frequency = self.frequency
            except Exception as e:
                logger.error(f"[PiezoBuzzer] Error setting frequency to {frequency} Hz: {e}")
        else:
            logger.debug(f"[PiezoBuzzer MOCK] Frequency set to {self.frequency} Hz.")

    def tone(self, frequency: int, duration: float = 1.0, duty_cycle: float = 0.5):
        """
        Emits a fixed-frequency tone burst for a specified duration, then shuts off.
        
        :param frequency: Frequency in Hz.
        :param duration: Burst duration in seconds.
        :param duty_cycle: PWM duty cycle (default 0.5).
        """
        try:
            self.start(frequency=frequency, duty_cycle=duty_cycle)
            time.sleep(max(0.0, duration))
        finally:
            self.stop()

    def sweep(
        self,
        start_hz: int = 19000,
        end_hz: int = 28000,
        step: int = 500,
        delay: float = 0.05,
        duty_cycle: float = 0.5,
    ):
        """
        Performs an acoustic or ultrasonic frequency sweep.
        
        :param start_hz: Starting frequency in Hz.
        :param end_hz: Ending frequency in Hz.
        :param step: Step increment in Hz.
        :param delay: Pause duration per step in seconds.
        :param duty_cycle: PWM duty cycle (default 0.5).
        """
        if start_hz <= 0 or end_hz <= 0 or step <= 0:
            raise ValueError("Frequencies and step must be positive integers.")

        # Ensure start is less than or equal to end for range, or determine direction
        direction = 1 if end_hz >= start_hz else -1
        actual_step = step if direction == 1 else -step

        try:
            self.start(frequency=start_hz, duty_cycle=duty_cycle)
            for freq in range(start_hz, end_hz + direction, actual_step):
                self.set_frequency(freq)
                time.sleep(max(0.001, delay))
        finally:
            self.stop()

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic state of the piezo controller."""
        return {
            "pin": self.pin,
            "frequency_hz": self.frequency,
            "duty_cycle": self.duty_cycle,
            "is_active": self.is_active,
            "backend": self.backend,
            "is_synthetic": self.is_synthetic,
        }

    def close(self):
        """Failsafe shutdown: stops PWM output and closes the GPIO device handle."""
        self.stop()
        if not self.is_synthetic and self._device is not None:
            try:
                self._device.close()
            except Exception as e:
                logger.error(f"[PiezoBuzzer] Error closing device: {e}")
            finally:
                self._device = None
        logger.info(f"[PiezoBuzzer] Driver on GPIO {self.pin} closed.")


# Singleton instance for quick module-level access
piezo = PiezoBuzzer()
