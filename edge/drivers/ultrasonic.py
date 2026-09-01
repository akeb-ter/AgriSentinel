"""
AgriSentinel Edge Driver - Dual HC-SR04 Ultrasonic Distance Sensors
Manages Front and Rear ultrasonic sensors for bidirectional collision avoidance.
"""

import os
import time
import logging
from typing import Dict, Tuple

logger = logging.getLogger("AgriSentinel-Ultrasonic")

# Default GPIO Pin Assignments
FRONT_TRIG_PIN = int(os.getenv("FRONT_TRIG_PIN", "23"))
FRONT_ECHO_PIN = int(os.getenv("FRONT_ECHO_PIN", "24"))
REAR_TRIG_PIN = int(os.getenv("REAR_TRIG_PIN", "27"))
REAR_ECHO_PIN = int(os.getenv("REAR_ECHO_PIN", "22"))


class DistanceSensor:
    """Individual HC-SR04 Ultrasonic Sensor Driver Interface."""

    def __init__(self, trig_pin: int, echo_pin: int, name: str = "Sensor"):
        self.trig_pin = trig_pin
        self.echo_pin = echo_pin
        self.name = name
        self._is_hardware_available = False

        try:
            # Check for RPi.GPIO or gpiozero hardware access
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self.GPIO.setmode(self.GPIO.BCMI) if hasattr(self.GPIO, "BCMI") else self.GPIO.setmode(self.GPIO.BCM)
            self.GPIO.setup(self.trig_pin, self.GPIO.OUT)
            self.GPIO.setup(self.echo_pin, self.GPIO.IN)
            self.GPIO.output(self.trig_pin, False)
            self._is_hardware_available = True
            logger.info(f"[{self.name}] Initialized HC-SR04 hardware (Trig={trig_pin}, Echo={echo_pin}).")
        except Exception as e:
            logger.warning(f"[{self.name}] Hardware initialization fallback (Mock Mode): {e}")

    def read_distance_cm(self) -> float:
        """Reads current distance in centimeters. Returns 999.0 on timeout/mock."""
        if not self._is_hardware_available:
            # Fallback mock value for non-Raspberry Pi / testing environments
            return 100.0

        try:
            # Send 10us pulse to trigger
            self.GPIO.output(self.trig_pin, True)
            time.sleep(0.00001)
            self.GPIO.output(self.trig_pin, False)

            pulse_start = time.time()
            pulse_end = time.time()

            timeout_start = time.time()
            while self.GPIO.input(self.echo_pin) == 0:
                pulse_start = time.time()
                if pulse_start - timeout_start > 0.05:
                    return 999.0  # Timeout

            while self.GPIO.input(self.echo_pin) == 1:
                pulse_end = time.time()
                if pulse_end - pulse_start > 0.05:
                    return 999.0  # Timeout

            pulse_duration = pulse_end - pulse_start
            distance_cm = round(pulse_duration * 17150, 2)
            return distance_cm
        except Exception as e:
            logger.error(f"[{self.name}] Distance read error: {e}")
            return 999.0

    def cleanup(self):
        """Cleans up GPIO pins if hardware driver was loaded."""
        if self._is_hardware_available:
            try:
                self.GPIO.cleanup((self.trig_pin, self.echo_pin))
            except Exception:
                pass


class DualUltrasonicSensors:
    """Manager class instantiating Front and Rear HC-SR04 ultrasonic sensors."""

    def __init__(
        self,
        front_trig: int = FRONT_TRIG_PIN,
        front_echo: int = FRONT_ECHO_PIN,
        rear_trig: int = REAR_TRIG_PIN,
        rear_echo: int = REAR_ECHO_PIN,
    ):
        self.front_sensor = DistanceSensor(front_trig, front_echo, name="FrontSensor")
        self.rear_sensor = DistanceSensor(rear_trig, rear_echo, name="RearSensor")

    def read_clearance(self) -> Dict[str, float]:
        """Returns distance clearance dictionary for front and rear sensors in cm."""
        return {
            "front_obstacle_cm": self.front_sensor.read_distance_cm(),
            "rear_obstacle_cm": self.rear_sensor.read_distance_cm(),
        }

    def cleanup(self):
        """Cleans up both front and rear sensor GPIO assignments."""
        self.front_sensor.cleanup()
        self.rear_sensor.cleanup()


# Instantiated singletons for direct module usage
FrontSensor = DistanceSensor(FRONT_TRIG_PIN, FRONT_ECHO_PIN, name="FrontSensor")
RearSensor = DistanceSensor(REAR_TRIG_PIN, REAR_ECHO_PIN, name="RearSensor")
