"""
AgriSentinel Edge Driver - Standard Buzzer & Deterrent Controller

Governs acoustic deterrent alerts using a standard 2-pin or 3-pin buzzer connected
to Raspberry Pi BCM GPIO 13 (Physical Pin 33).

Supports:
1. Active Buzzers: Driven via digital logic (HIGH = sound ON, LOW = sound OFF).
2. Passive Buzzers: Driven via audible PWM frequencies (e.g. 1 kHz - 3.5 kHz, centered at ~2.5 kHz).
3. GPIO Zero PWMOutputDevice with automatic SYNTHETIC / MOCK fallback for off-Pi testing.
4. Digital on/off, rhythmic beep pulses, rapid alert alarm patterns, and frequency sweeps.
"""

import os
import sys
import time
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger("AgriSentinel-Buzzer")

# Pin & Audible Frequency Defaults
PIEZO_GPIO_PIN = int(os.getenv("PIEZO_GPIO_PIN", "13"))  # BCM GPIO 13 (Physical Pin 33)
DEFAULT_FREQUENCY = int(os.getenv("BUZZER_DEFAULT_FREQ", "2500"))  # 2.5 kHz audible default


class PiezoBuzzer:
    """Standard Buzzer & Acoustic Deterrent Controller (supports Active and Passive buzzers)."""

    def __init__(self, pin: int = PIEZO_GPIO_PIN, default_frequency: int = DEFAULT_FREQUENCY):
        self.pin = pin
        self.frequency = default_frequency
        self.duty_cycle = 0.0
        self.is_synthetic = False
        self.backend = "SYNTHETIC"
        self._device: Optional[Any] = None

        self._init_driver()

    def _init_driver(self):
        """Initializes hardware PWM / digital pin via gpiozero PWMOutputDevice or falls back to synthetic mode."""
        try:
            from gpiozero import PWMOutputDevice

            # Initialize with initial_value=0 (Pin pulled LOW)
            self._device = PWMOutputDevice(
                self.pin,
                active_high=True,
                initial_value=0.0,
                frequency=self.frequency,
            )
            self.backend = "gpiozero.PWMOutputDevice"
            self.is_synthetic = False
            logger.info(
                f"[Buzzer] Initialized buzzer on GPIO {self.pin} "
                f"at {self.frequency} Hz (Backend: {self.backend})."
            )
        except Exception as e:
            self.is_synthetic = True
            self.backend = "SYNTHETIC"
            self._device = None
            logger.warning(
                f"[Buzzer] Hardware GPIO unavailable on GPIO {self.pin}: {e}. "
                "Operating in SYNTHETIC MOCK MODE."
            )

    @property
    def is_active(self) -> bool:
        """Returns True if the buzzer is actively sounding (duty cycle > 0)."""
        return self.duty_cycle > 0.0

    def on(self):
        """
        Turns the buzzer continuously ON (DC HIGH, 100% duty cycle).
        Ideal for Active Buzzers.
        """
        self.duty_cycle = 1.0
        if not self.is_synthetic and self._device is not None:
            try:
                self._device.value = 1.0
            except Exception as e:
                logger.error(f"[Buzzer] Failed to set ON state: {e}")
        else:
            logger.debug(f"[Buzzer MOCK] Turned ON (DC HIGH).")

    def off(self):
        """Turns the buzzer completely OFF (pin pulled LOW)."""
        self.stop()

    def start(self, frequency: Optional[int] = None, duty_cycle: float = 0.5):
        """
        Starts emitting continuous sound.
        For active buzzers, duty_cycle=1.0 provides steady DC voltage.
        For passive buzzers, duty_cycle=0.5 generates a square wave tone at frequency.

        :param frequency: Tone frequency in Hertz (if None, uses current frequency).
        :param duty_cycle: Duty cycle between 0.0 and 1.0 (default 0.5).
        """
        if frequency is not None:
            self.set_frequency(frequency)

        duty_cycle = max(0.0, min(1.0, float(duty_cycle)))
        self.duty_cycle = duty_cycle

        if not self.is_synthetic and self._device is not None:
            try:
                self._device.value = duty_cycle
            except Exception as e:
                logger.error(f"[Buzzer] Failed to set duty cycle: {e}")
        else:
            logger.debug(f"[Buzzer MOCK] Sound ON @ {self.frequency} Hz, duty={duty_cycle:.2f}")

    def stop(self):
        """Immediately silences the buzzer by driving the pin LOW."""
        self.duty_cycle = 0.0
        if not self.is_synthetic and self._device is not None:
            try:
                self._device.value = 0.0
            except Exception as e:
                logger.error(f"[Buzzer] Error driving pin LOW: {e}")
        else:
            logger.debug("[Buzzer MOCK] Output stopped (Pin pulled LOW).")

    def set_frequency(self, frequency: int):
        """
        Adjusts the tone frequency in Hertz (for passive buzzers).

        :param frequency: Target frequency in Hz (e.g., 500 - 5000 Hz).
        """
        if frequency <= 0:
            raise ValueError("Frequency must be a positive integer.")

        self.frequency = int(frequency)

        if not self.is_synthetic and self._device is not None:
            try:
                self._device.frequency = self.frequency
            except Exception as e:
                logger.error(f"[Buzzer] Error setting frequency to {frequency} Hz: {e}")
        else:
            logger.debug(f"[Buzzer MOCK] Frequency set to {self.frequency} Hz.")

    def beep(self, on_time: float = 0.2, off_time: float = 0.1, n: int = 3, duty_cycle: float = 1.0):
        """
        Emits a series of distinct beeps.
        Works for both active buzzers (duty_cycle=1.0) and passive buzzers (duty_cycle=0.5).

        :param on_time: Duration of each beep in seconds.
        :param off_time: Duration between beeps in seconds.
        :param n: Number of beeps to emit.
        :param duty_cycle: 1.0 for DC active buzzers, 0.5 for passive square wave.
        """
        try:
            for i in range(max(1, int(n))):
                self.start(duty_cycle=duty_cycle)
                time.sleep(max(0.01, on_time))
                self.stop()
                if i < n - 1:
                    time.sleep(max(0.01, off_time))
        finally:
            self.stop()

    def tone(self, frequency: int = 2500, duration: float = 1.0, duty_cycle: float = 0.5):
        """
        Emits a fixed-frequency audible tone burst (ideal for passive buzzers).

        :param frequency: Tone frequency in Hz (default: 2500 Hz).
        :param duration: Duration in seconds.
        :param duty_cycle: PWM duty cycle (default: 0.5 for square wave).
        """
        try:
            self.start(frequency=frequency, duty_cycle=duty_cycle)
            time.sleep(max(0.0, duration))
        finally:
            self.stop()

    def sweep(
        self,
        start_hz: int = 1000,
        end_hz: int = 3500,
        step: int = 250,
        delay: float = 0.03,
        duty_cycle: float = 0.5,
    ):
        """
        Performs an audible frequency siren sweep across a specified range.

        :param start_hz: Starting audible frequency in Hz (default: 1000).
        :param end_hz: Ending audible frequency in Hz (default: 3500).
        :param step: Step increment in Hz.
        :param delay: Pause duration per step in seconds.
        :param duty_cycle: PWM duty cycle (default 0.5).
        """
        if start_hz <= 0 or end_hz <= 0 or step <= 0:
            raise ValueError("Frequencies and step must be positive integers.")

        direction = 1 if end_hz >= start_hz else -1
        actual_step = step if direction == 1 else -step

        try:
            self.start(frequency=start_hz, duty_cycle=duty_cycle)
            for freq in range(start_hz, end_hz + direction, actual_step):
                self.set_frequency(freq)
                time.sleep(max(0.001, delay))
        finally:
            self.stop()

    def alarm(self, duration: float = 2.0, pattern: str = "fast"):
        """
        Plays a pest-deterrent acoustic alarm pattern.

        :param duration: Total duration of the alarm sequence in seconds.
        :param pattern: 'fast' (rapid 0.1s pulses) or 'chirp' (alternating frequencies).
        """
        end_time = time.time() + max(0.1, duration)
        try:
            if pattern == "chirp":
                while time.time() < end_time:
                    self.tone(frequency=2800, duration=0.08, duty_cycle=0.5)
                    self.tone(frequency=2100, duration=0.08, duty_cycle=0.5)
            else:
                # Fast alert beeps (works on both active and passive)
                while time.time() < end_time:
                    self.start(duty_cycle=1.0)
                    time.sleep(0.1)
                    self.stop()
                    time.sleep(0.08)
        finally:
            self.stop()

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic state of the buzzer controller."""
        return {
            "pin": self.pin,
            "frequency_hz": self.frequency,
            "duty_cycle": self.duty_cycle,
            "is_active": self.is_active,
            "backend": self.backend,
            "is_synthetic": self.is_synthetic,
        }

    def close(self):
        """Failsafe shutdown: stops output and releases GPIO device handle."""
        self.stop()
        if not self.is_synthetic and self._device is not None:
            try:
                self._device.close()
            except Exception as e:
                logger.error(f"[Buzzer] Error closing device: {e}")
            finally:
                self._device = None
        logger.info(f"[Buzzer] Driver on GPIO {self.pin} closed.")


# Aliases for clear naming while preserving backward compatibility
BuzzerController = PiezoBuzzer
Buzzer = PiezoBuzzer

# Singleton instance for quick module-level access
piezo = PiezoBuzzer()
buzzer = piezo
