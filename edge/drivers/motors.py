"""
AgriSentinel Edge Drivers - L298N Dual H-Bridge Motor Controller

Governs 4x 12V DC gear motors attached to 4WD chassis via L298N Dual H-Bridge.
ENA and ENB speed pins are physically jumpered to 5V (100% full duty cycle / no PWM required).
Directional control uses 4 Raspberry Pi GPIO pins:
- Left Motor: IN1 (GPIO 5), IN2 (GPIO 6)
- Right Motor: IN3 (GPIO 19), IN4 (GPIO 26)

Supports hardware RPi.GPIO execution with seamless synthetic/mock fallback for non-Pi development.
"""

import os
import time
import logging
from typing import Dict, Any

logger = logging.getLogger("AgriSentinel-Motors")

# Default GPIO Pin Assignments for Directional Control
MOTOR_IN1_PIN = int(os.getenv("MOTOR_IN1_PIN", "5"))    # Left Motor Forward
MOTOR_IN2_PIN = int(os.getenv("MOTOR_IN2_PIN", "6"))    # Left Motor Reverse
MOTOR_IN3_PIN = int(os.getenv("MOTOR_IN3_PIN", "19"))   # Right Motor Forward
MOTOR_IN4_PIN = int(os.getenv("MOTOR_IN4_PIN", "26"))   # Right Motor Reverse


class MotorController:
    """L298N Dual H-Bridge Motor Controller for 4WD Chassis Directional Navigation."""

    def __init__(
        self,
        in1_pin: int = MOTOR_IN1_PIN,
        in2_pin: int = MOTOR_IN2_PIN,
        in3_pin: int = MOTOR_IN3_PIN,
        in4_pin: int = MOTOR_IN4_PIN,
    ):
        self.in1_pin = in1_pin
        self.in2_pin = in2_pin
        self.in3_pin = in3_pin
        self.in4_pin = in4_pin

        self.pins = [self.in1_pin, self.in2_pin, self.in3_pin, self.in4_pin]
        self.state = "STOPPED"
        self.is_synthetic = False
        self.GPIO = None

        self._init_gpio()

    def _init_gpio(self):
        """Initializes Raspberry Pi GPIO outputs or falls back to synthetic mode."""
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self.GPIO.setmode(self.GPIO.BCM)
            self.GPIO.setwarnings(False)

            for pin in self.pins:
                self.GPIO.setup(pin, self.GPIO.OUT)
                self.GPIO.output(pin, False)

            logger.info(
                f"[MotorController] Hardware GPIO initialized: "
                f"Left=(IN1:{self.in1_pin}, IN2:{self.in2_pin}), Right=(IN3:{self.in3_pin}, IN4:{self.in4_pin}). "
                f"ENA & ENB jumpered to 5V (Full Speed)."
            )
        except Exception as e:
            self.is_synthetic = True
            logger.warning(f"[MotorController] RPi GPIO unavailable ({e}). Operating in Synthetic Mode.")

    def _write_pins(self, in1: bool, in2: bool, in3: bool, in4: bool):
        """Internal helper to write logical boolean levels to directional GPIO pins."""
        if self.GPIO and not self.is_synthetic:
            try:
                self.GPIO.output(self.in1_pin, in1)
                self.GPIO.output(self.in2_pin, in2)
                self.GPIO.output(self.in3_pin, in3)
                self.GPIO.output(self.in4_pin, in4)
            except Exception as e:
                logger.error(f"[MotorController] GPIO write error: {e}")
        else:
            logger.debug(
                f"[MotorController (Synthetic)] Pins -> IN1:{int(in1)} IN2:{int(in2)} IN3:{int(in3)} IN4:{int(in4)}"
            )

    def forward(self):
        """Drives both left and right motors forward."""
        self._write_pins(in1=True, in2=False, in3=True, in4=False)
        self.state = "FORWARD"
        logger.info("[MotorController] Action: FORWARD (Left=FWD, Right=FWD)")

    def backward(self):
        """Drives both left and right motors in reverse."""
        self._write_pins(in1=False, in2=True, in3=False, in4=True)
        self.state = "REVERSE"
        logger.info("[MotorController] Action: REVERSE (Left=REV, Right=REV)")

    def reverse(self):
        """Alias for backward()."""
        self.backward()

    def spin_left(self):
        """Performs zero-radius skid-steer turn left (Left wheels reverse, Right wheels forward)."""
        self._write_pins(in1=False, in2=True, in3=True, in4=False)
        self.state = "LEFT"
        logger.info("[MotorController] Action: SPIN_LEFT (Left=REV, Right=FWD)")

    def spin_right(self):
        """Performs zero-radius skid-steer turn right (Left wheels forward, Right wheels reverse)."""
        self._write_pins(in1=True, in2=False, in3=False, in4=True)
        self.state = "RIGHT"
        logger.info("[MotorController] Action: SPIN_RIGHT (Left=FWD, Right=REV)")

    def turn_left(self):
        """Default left turn behavior: zero-radius skid-steer spin left."""
        self.spin_left()

    def turn_right(self):
        """Default right turn behavior: zero-radius skid-steer spin right."""
        self.spin_right()

    def left(self):
        """Alias for turn_left()."""
        self.turn_left()

    def right(self):
        """Alias for turn_right()."""
        self.turn_right()

    def pivot_left(self):
        """Performs pivot turn left by stopping left wheels and driving right wheels forward."""
        self._write_pins(in1=False, in2=False, in3=True, in4=False)
        self.state = "LEFT"
        logger.info("[MotorController] Action: PIVOT_LEFT (Left=STOP, Right=FWD)")

    def pivot_right(self):
        """Performs pivot turn right by driving left wheels forward and stopping right wheels."""
        self._write_pins(in1=True, in2=False, in3=False, in4=False)
        self.state = "RIGHT"
        logger.info("[MotorController] Action: PIVOT_RIGHT (Left=FWD, Right=STOP)")

    def stop(self):
        """Stops all motors by pulling all directional pins LOW."""
        self._write_pins(in1=False, in2=False, in3=False, in4=False)
        self.state = "STOPPED"
        logger.info("[MotorController] Action: STOP (All pins LOW)")

    def get_state(self) -> str:
        """Returns the current motor navigation state."""
        return self.state

    def cleanup(self):
        """Stops motors and safely releases GPIO pins."""
        self.stop()
        if self.GPIO and not self.is_synthetic:
            try:
                self.GPIO.cleanup(tuple(self.pins))
                logger.info("[MotorController] GPIO pins cleaned up.")
            except Exception:
                pass


def run_test_sequence(move_duration: float = 2.0, pause_duration: float = 1.0):
    """
    Executes a complete directional test sequence:
    1. Forward (2s) -> Stop (1s)
    2. Backward (2s) -> Stop (1s)
    3. Spin Left (2s) -> Stop (1s)
    4. Spin Right (2s) -> Stop (1s)
    5. Pivot Left (1s) -> Stop (0.5s)
    6. Pivot Right (1s) -> Stop (0.5s)
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("\n========================================================")
    print("  AgriSentinel L298N Motor Driver Test Sequence")
    print("  Note: ENA & ENB are 5V Jumpered (Full Speed Operation)")
    print("========================================================\n")

    motors = MotorController()

    try:
        # Step 1: Forward
        print(f"[*] Step 1/6: Driving FORWARD for {move_duration}s...")
        motors.forward()
        time.sleep(move_duration)

        print(f"[*] Pausing (STOP) for {pause_duration}s...")
        motors.stop()
        time.sleep(pause_duration)

        # Step 2: Backward
        print(f"[*] Step 2/6: Driving BACKWARD (Reverse) for {move_duration}s...")
        motors.backward()
        time.sleep(move_duration)

        print(f"[*] Pausing (STOP) for {pause_duration}s...")
        motors.stop()
        time.sleep(pause_duration)

        # Step 3: Spin Left
        print(f"[*] Step 3/6: Turning LEFT (Skid-steer spin) for {move_duration}s...")
        motors.left()
        time.sleep(move_duration)

        print(f"[*] Pausing (STOP) for {pause_duration}s...")
        motors.stop()
        time.sleep(pause_duration)

        # Step 4: Spin Right
        print(f"[*] Step 4/6: Turning RIGHT (Skid-steer spin) for {move_duration}s...")
        motors.right()
        time.sleep(move_duration)

        print(f"[*] Pausing (STOP) for {pause_duration}s...")
        motors.stop()
        time.sleep(pause_duration)

        # Step 5: Pivot Left
        print("[*] Step 5/6: PIVOT LEFT (Inside wheel stopped) for 1.0s...")
        motors.pivot_left()
        time.sleep(1.0)

        print("[*] Pausing (STOP) for 0.5s...")
        motors.stop()
        time.sleep(0.5)

        # Step 6: Pivot Right
        print("[*] Step 6/6: PIVOT RIGHT (Inside wheel stopped) for 1.0s...")
        motors.pivot_right()
        time.sleep(1.0)

        print("[*] Test sequence completed successfully. Bringing motors to full stop.")
        motors.stop()

    except KeyboardInterrupt:
        print("\n[!] Test sequence interrupted by user. Stopping motors...")
    finally:
        motors.cleanup()
        print("[*] Motor driver cleanup complete.\n")


if __name__ == "__main__":
    run_test_sequence()

