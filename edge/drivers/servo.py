"""
AgriSentinel Edge Drivers - Camera Pan Servo Controller

Governs camera pan-tilt mechanism using SG90 / MG996R servo motor on GPIO 18 (PWM Pin 12).
Supports hardware PWM via gpiozero / pigpio with synthetic fallback for simulation environments.
"""

import os
import time
import logging
from typing import Optional

logger = logging.getLogger("AgriSentinel-Servo")

# Pin & Angle Configuration
SERVO_GPIO_PIN = int(os.getenv("SERVO_GPIO_PIN", "18"))
MIN_ANGLE = int(os.getenv("SERVO_MIN_ANGLE", "-60"))
MAX_ANGLE = int(os.getenv("SERVO_MAX_ANGLE", "60"))
STEP_ANGLE = int(os.getenv("SERVO_STEP_ANGLE", "10"))


class ServoController:
    """Servo Motor Controller for camera pan sweep."""

    def __init__(self, pin: int = SERVO_GPIO_PIN, min_angle: int = MIN_ANGLE, max_angle: int = MAX_ANGLE):
        self.pin = pin
        self.min_angle = min_angle
        self.max_angle = max_angle
        self.current_angle = 0
        self.sweep_direction = 1  # 1 for increasing angle, -1 for decreasing
        self._servo = None
        self.is_synthetic = False

        self._init_driver()

    def _init_driver(self):
        """Initializes gpiozero AngularServo or falls back to synthetic mode."""
        try:
            from gpiozero import AngularServo

            self._servo = AngularServo(
                self.pin,
                min_angle=self.min_angle,
                max_angle=self.max_angle,
                min_pulse_width=0.0005,
                max_pulse_width=0.0025,
            )
            logger.info(f"[ServoController] Hardware AngularServo initialized on GPIO {self.pin}.")
        except (ImportError, Exception) as e:
            self.is_synthetic = True
            logger.warning(f"[ServoController] RPi GPIO unavailable ({e}). Operating in Synthetic Mode.")

    def set_angle(self, angle: float):
        """Sets the servo to a specific angle within min/max bounds."""
        clamped_angle = max(self.min_angle, min(self.max_angle, angle))
        self.current_angle = clamped_angle

        if self._servo and not self.is_synthetic:
            try:
                self._servo.angle = clamped_angle
            except Exception as e:
                logger.error(f"[ServoController] Error setting servo angle: {e}")
        else:
            logger.debug(f"[ServoController (Synthetic)] Angle set to {clamped_angle}°")

    def center(self):
        """Centers the camera servo (0 degrees)."""
        self.set_angle(0)

    def sweep_step(self, step_size: float = STEP_ANGLE) -> float:
        """
        Advances the camera pan angle by one step increment.
        Reverses sweep direction when reaching angle limits.
        Returns the new angle.
        """
        new_angle = self.current_angle + (step_size * self.sweep_direction)

        if new_angle >= self.max_angle:
            new_angle = self.max_angle
            self.sweep_direction = -1
        elif new_angle <= self.min_angle:
            new_angle = self.min_angle
            self.sweep_direction = 1

        self.set_angle(new_angle)
        return self.current_angle

    def close(self):
        """Releases GPIO resources."""
        if self._servo and not self.is_synthetic:
            try:
                self._servo.close()
            except Exception:
                pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing ServoController...")
    servo = ServoController()
    servo.center()
    time.sleep(0.5)
    for _ in range(12):
        angle = servo.sweep_step(15)
        print(f"Current Pan Angle: {angle}°")
        time.sleep(0.2)
    servo.center()
    servo.close()
    print("Servo test complete.")

