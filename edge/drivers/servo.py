"""
AgriSentinel Edge Drivers - Camera Pan Servo Controller

Governs camera pan-tilt mechanism using SG90 / MG996R servo motor on GPIO 18 (Physical Pin 12, Hardware PWM0).
Supports:
1. gpiozero AngularServo (Preferred for Raspberry Pi OS Bookworm & Bullseye on Pi 4)
2. RPi.GPIO.PWM (Fallback for legacy environments)
3. Synthetic / Mock mode with explicit diagnostics when no hardware GPIO is available.

Features jitter mitigation via PWM detachment when idle to prevent motor buzzing and overheating.
"""

import os
import sys
import time
import logging
from typing import Optional

logger = logging.getLogger("AgriSentinel-Servo")

# Pin & Angular Bounds Configuration (BCM Numbering)
SERVO_GPIO_PIN = int(os.getenv("SERVO_GPIO_PIN", "18"))  # BCM GPIO 18 (Physical Pin 12)
MIN_ANGLE = int(os.getenv("SERVO_MIN_ANGLE", "-60"))     # Left limit (degrees)
MAX_ANGLE = int(os.getenv("SERVO_MAX_ANGLE", "60"))      # Right limit (degrees)
STEP_ANGLE = int(os.getenv("SERVO_STEP_ANGLE", "10"))    # Autonomous sweep increment


class ServoController:
    """Servo Motor Controller for camera pan sweep with PWM jitter mitigation."""

    def __init__(
        self,
        pin: int = SERVO_GPIO_PIN,
        min_angle: int = MIN_ANGLE,
        max_angle: int = MAX_ANGLE,
    ):
        self.pin = pin
        self.min_angle = min_angle
        self.max_angle = max_angle
        self.current_angle = 0.0
        self.sweep_direction = 1  # 1 for increasing angle, -1 for decreasing
        self.backend = "SYNTHETIC"  # "gpiozero", "RPi.GPIO", or "SYNTHETIC"
        self.is_synthetic = False

        # Hardware handles
        self._servo = None
        self._pwm = None
        self.GPIO = None

        self._init_driver()

    def _init_driver(self):
        """Initializes hardware PWM via gpiozero (preferred) or RPi.GPIO (fallback)."""
        # Backend 1: gpiozero AngularServo
        try:
            from gpiozero import AngularServo

            self._servo = AngularServo(
                self.pin,
                min_angle=self.min_angle,
                max_angle=self.max_angle,
                min_pulse_width=0.0005,
                max_pulse_width=0.0025,
            )
            self.backend = "gpiozero"
            self.is_synthetic = False
            logger.info(
                f"[ServoController] Live hardware initialized using gpiozero on BCM GPIO {self.pin} (Pin 12). "
                f"Range: [{self.min_angle}°, {self.max_angle}°]."
            )
            return
        except Exception as gz_err:
            logger.debug(f"[ServoController] gpiozero AngularServo unavailable: {gz_err}")

        # Backend 2: RPi.GPIO PWM
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self.GPIO.setmode(self.GPIO.BCM)
            self.GPIO.setwarnings(False)
            self.GPIO.setup(self.pin, self.GPIO.OUT)

            # 50 Hz PWM (20ms cycle)
            self._pwm = self.GPIO.PWM(self.pin, 50)
            self._pwm.start(0)  # Start with 0 duty cycle (detached)

            self.backend = "RPi.GPIO"
            self.is_synthetic = False
            logger.info(
                f"[ServoController] Live hardware initialized using RPi.GPIO.PWM on BCM GPIO {self.pin} (Pin 12)."
            )
            return
        except Exception as rpi_err:
            logger.debug(f"[ServoController] RPi.GPIO PWM unavailable: {rpi_err}")

        # Backend 3: Synthetic / Mock Mode
        self.backend = "SYNTHETIC"
        self.is_synthetic = True
        logger.warning(
            f"[ServoController] No physical GPIO library available for GPIO {self.pin}. "
            f"OPERATING IN SYNTHETIC MOCK MODE - SERVO HARDWARE WILL NOT MOVE!"
        )

    def set_angle(self, angle: float):
        """Sets the camera pan servo to a specific angle within min/max bounds."""
        clamped_angle = max(float(self.min_angle), min(float(self.max_angle), float(angle)))
        self.current_angle = round(clamped_angle, 1)

        if self.backend == "gpiozero" and self._servo:
            try:
                self._servo.angle = self.current_angle
            except Exception as e:
                logger.error(f"[ServoController] gpiozero angle set error: {e}")

        elif self.backend == "RPi.GPIO" and self._pwm:
            try:
                # 50Hz = 20ms period. 0.5ms (-90 deg) = 2.5% duty; 2.5ms (+90 deg) = 12.5% duty.
                duty = round(2.5 + ((self.current_angle + 90.0) / 180.0) * 10.0, 2)
                self._pwm.ChangeDutyCycle(duty)
            except Exception as e:
                logger.error(f"[ServoController] RPi.GPIO PWM set error: {e}")

        else:
            logger.debug(f"[ServoController (Synthetic)] Pan angle set to {self.current_angle} deg")

    def center(self):
        """Centers the camera servo (0 degrees straight forward)."""
        self.set_angle(0.0)
        logger.info("[ServoController] Position: CENTER (0 deg)")

    def pan_left(self):
        """Pans camera to maximum left limit."""
        self.set_angle(self.min_angle)
        logger.info(f"[ServoController] Position: LEFT LIMIT ({self.min_angle} deg)")

    def pan_right(self):
        """Pans camera to maximum right limit."""
        self.set_angle(self.max_angle)
        logger.info(f"[ServoController] Position: RIGHT LIMIT ({self.max_angle} deg)")

    def sweep_step(self, step_size: float = STEP_ANGLE) -> float:
        """
        Advances the camera pan angle by one step increment.
        Reverses sweep direction when reaching angular limits.
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

    def detach(self):
        """
        Stops sending PWM pulses when servo is stationary.
        Prevents jitter, buzzing noise, and thermal buildup in analog/digital servos.
        """
        if self.backend == "gpiozero" and self._servo:
            try:
                # Setting value to None in gpiozero stops PWM pulse train
                self._servo.value = None
            except Exception:
                pass
        elif self.backend == "RPi.GPIO" and self._pwm:
            try:
                self._pwm.ChangeDutyCycle(0)
            except Exception:
                pass
        logger.debug("[ServoController] PWM pulse detached (idle sleep).")

    def get_angle(self) -> float:
        """Returns the current pan angle in degrees."""
        return self.current_angle

    def close(self):
        """Releases GPIO hardware resources."""
        self.detach()
        if self.backend == "gpiozero" and self._servo:
            try:
                self._servo.close()
                logger.info("[ServoController] gpiozero servo closed.")
            except Exception:
                pass
        elif self.backend == "RPi.GPIO":
            try:
                if self._pwm:
                    self._pwm.stop()
                if self.GPIO:
                    self.GPIO.cleanup(self.pin)
                logger.info("[ServoController] RPi.GPIO PWM cleaned up.")
            except Exception:
                pass

    def cleanup(self):
        """Alias for close()."""
        self.close()


def run_test_sequence():
    """
    Executes an interactive calibration & verification sequence:
    1. Center (0 deg) -> Hold 1.5s
    2. Left Limit (-60 deg) -> Hold 1.5s
    3. Return Center (0 deg) -> Hold 1.0s
    4. Right Limit (+60 deg) -> Hold 1.5s
    5. Return Center (0 deg) -> Hold 1.0s
    6. Continuous Smooth Sweep (-60 deg -> +60 deg -> 0 deg)
    7. Safe Detach & Resource Release
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("\n=================================================================")
    print("      AgriSentinel Camera Pan Servo Test Sequence")
    print("=================================================================")
    print("  Hardware Wiring Reference:")
    print("    Signal (Yellow/Orange) -> BCM GPIO 18 (Physical Pin 12, PWM0)")
    print("    VCC (Red)              -> 5V Supply Rail (Pin 2/4 or L298N 5V)")
    print("    GND (Brown/Black)      -> Common System Ground (Pin 6/9/14/20)")
    print("  Angular Range: -60 deg (Far Left) to +60 deg (Far Right), 0 deg (Center)")
    print("-----------------------------------------------------------------")

    servo = ServoController()

    if servo.is_synthetic:
        print("\n [!] CRITICAL WARNING: SYNTHETIC MOCK MODE IS ACTIVE!")
        print("     Neither 'gpiozero' nor 'RPi.GPIO' could be accessed.")
        print("     Physical servo horn WILL NOT MOVE.")
        print("     To fix on Raspberry Pi OS Bookworm/Bullseye:")
        print("         sudo apt install -y python3-gpiozero python3-lgpio")
        print("-----------------------------------------------------------------\n")
    else:
        print(f"\n [OK] HARDWARE ACTIVE: Using '{servo.backend}' backend on GPIO {servo.pin}.")
        print("     Live PWM signals ARE being transmitted to the servo.\n")

    try:
        # Step 1: Center
        print("[*] Step 1/5: Centering camera servo to 0 deg (Straight Forward)...")
        servo.center()
        time.sleep(1.5)

        # Step 2: Left Limit
        print(f"[*] Step 2/5: Panning to Left limit ({servo.min_angle} deg)...")
        servo.pan_left()
        time.sleep(1.5)

        # Step 3: Re-Center
        print("[*] Step 3/5: Returning to Center (0 deg)...")
        servo.center()
        time.sleep(1.0)

        # Step 4: Right Limit
        print(f"[*] Step 4/5: Panning to Right limit (+{servo.max_angle} deg)...")
        servo.pan_right()
        time.sleep(1.5)

        # Return Center before sweep
        servo.center()
        time.sleep(1.0)

        # Step 5: Continuous Sweep
        print("[*] Step 5/5: Executing continuous pan sweep across field of view...")
        # Sweep from -60 to +60
        servo.set_angle(servo.min_angle)
        time.sleep(0.5)
        for _ in range(24):
            ang = servo.sweep_step(5)
            print(f"    Pan Angle: {ang:5.1f} deg")
            time.sleep(0.08)

        print("[*] Returning camera to Center (0 deg)...")
        servo.center()
        time.sleep(0.5)

        print("[*] Detaching PWM pulse to eliminate idle servo buzzing...")
        servo.detach()

        print("\n[OK] Servo calibration and sweep test completed successfully!\n")

    except KeyboardInterrupt:
        print("\n[!] Servo test interrupted by user.")
    finally:
        servo.close()
        print("[*] Servo GPIO resources cleanly released.\n")


if __name__ == "__main__":
    run_test_sequence()
