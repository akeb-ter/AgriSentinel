"""
AgriSentinel Edge Drivers - L298N Dual H-Bridge Motor Controller

Governs 4x 12V DC gear motors attached to 4WD chassis via L298N Dual H-Bridge.
ENA and ENB speed pins are physically jumpered to 5V (100% full duty cycle / no PWM required).
Directional control uses 4 Raspberry Pi GPIO pins (BCM numbering):
- Left Motor: IN1 (BCM GPIO 5, Physical Pin 29), IN2 (BCM GPIO 6, Physical Pin 31)
- Right Motor: IN3 (BCM GPIO 19, Physical Pin 35), IN4 (BCM GPIO 26, Physical Pin 37)

Supports:
1. gpiozero DigitalOutputDevice (Preferred for Raspberry Pi OS Bookworm & Bullseye on Pi 4)
2. RPi.GPIO (Fallback for legacy environments)
3. Synthetic / Mock mode with explicit warnings when no GPIO library is available.
"""

import os
import sys
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("AgriSentinel-Motors")

# Default GPIO Pin Assignments (BCM Numbering)
MOTOR_IN1_PIN = int(os.getenv("MOTOR_IN1_PIN", "5"))    # BCM GPIO 5 (Pin 29) - Left Forward
MOTOR_IN2_PIN = int(os.getenv("MOTOR_IN2_PIN", "6"))    # BCM GPIO 6 (Pin 31) - Left Reverse
MOTOR_IN3_PIN = int(os.getenv("MOTOR_IN3_PIN", "19"))   # BCM GPIO 19 (Pin 35) - Right Forward
MOTOR_IN4_PIN = int(os.getenv("MOTOR_IN4_PIN", "26"))   # BCM GPIO 26 (Pin 37) - Right Reverse


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
        self.backend = "SYNTHETIC"  # "gpiozero", "RPi.GPIO", or "SYNTHETIC"
        self.is_synthetic = False

        # Hardware handles
        self._gpiozero_devices = {}
        self.GPIO = None

        self._init_gpio()

    def _init_gpio(self):
        """Initializes hardware GPIO using gpiozero (preferred) or RPi.GPIO (fallback)."""
        # Try Backend 1: gpiozero (Standard for Raspberry Pi 4 Bookworm / Bullseye)
        try:
            from gpiozero import DigitalOutputDevice

            self._gpiozero_devices = {
                self.in1_pin: DigitalOutputDevice(self.in1_pin, active_high=True, initial_value=False),
                self.in2_pin: DigitalOutputDevice(self.in2_pin, active_high=True, initial_value=False),
                self.in3_pin: DigitalOutputDevice(self.in3_pin, active_high=True, initial_value=False),
                self.in4_pin: DigitalOutputDevice(self.in4_pin, active_high=True, initial_value=False),
            }
            self.backend = "gpiozero"
            self.is_synthetic = False
            logger.info(
                f"[MotorController] Live hardware initialized using gpiozero (BCM pins: "
                f"IN1={self.in1_pin}, IN2={self.in2_pin}, IN3={self.in3_pin}, IN4={self.in4_pin})."
            )
            return
        except Exception as gz_err:
            logger.debug(f"[MotorController] gpiozero unavailable: {gz_err}")

        # Try Backend 2: RPi.GPIO
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self.GPIO.setmode(self.GPIO.BCM)
            self.GPIO.setwarnings(False)

            for pin in self.pins:
                self.GPIO.setup(pin, self.GPIO.OUT, initial=self.GPIO.LOW)

            self.backend = "RPi.GPIO"
            self.is_synthetic = False
            logger.info(
                f"[MotorController] Live hardware initialized using RPi.GPIO (BCM pins: "
                f"IN1={self.in1_pin}, IN2={self.in2_pin}, IN3={self.in3_pin}, IN4={self.in4_pin})."
            )
            return
        except Exception as rpi_err:
            logger.debug(f"[MotorController] RPi.GPIO unavailable: {rpi_err}")

        # Backend 3: Synthetic / Mock Mode
        self.backend = "SYNTHETIC"
        self.is_synthetic = True
        logger.warning(
            "[MotorController] No physical GPIO library (gpiozero or RPi.GPIO) is available. "
            "OPERATING IN SYNTHETIC MOCK MODE - PHYSICAL PINS WILL NOT BE DRIVEN!"
        )

    def _write_pins(self, in1: bool, in2: bool, in3: bool, in4: bool):
        """Writes boolean logic levels to directional pins using the active hardware backend."""
        if self.backend == "gpiozero":
            try:
                self._gpiozero_devices[self.in1_pin].value = in1
                self._gpiozero_devices[self.in2_pin].value = in2
                self._gpiozero_devices[self.in3_pin].value = in3
                self._gpiozero_devices[self.in4_pin].value = in4
            except Exception as e:
                logger.error(f"[MotorController] gpiozero write error: {e}")

        elif self.backend == "RPi.GPIO" and self.GPIO:
            try:
                self.GPIO.output(self.in1_pin, in1)
                self.GPIO.output(self.in2_pin, in2)
                self.GPIO.output(self.in3_pin, in3)
                self.GPIO.output(self.in4_pin, in4)
            except Exception as e:
                logger.error(f"[MotorController] RPi.GPIO write error: {e}")

        else:
            logger.debug(
                f"[MotorController (Synthetic)] BCM Pins -> "
                f"IN1({self.in1_pin}):{int(in1)} IN2({self.in2_pin}):{int(in2)} "
                f"IN3({self.in3_pin}):{int(in3)} IN4({self.in4_pin}):{int(in4)}"
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
        """Performs zero-radius skid-steer turn left (Left wheels forward, Right wheels reverse)."""
        self._write_pins(in1=True, in2=False, in3=False, in4=True)
        self.state = "LEFT"
        logger.info("[MotorController] Action: SPIN_LEFT (Left=FWD, Right=REV)")

    def spin_right(self):
        """Performs zero-radius skid-steer turn right (Left wheels reverse, Right wheels forward)."""
        self._write_pins(in1=False, in2=True, in3=True, in4=False)
        self.state = "RIGHT"
        logger.info("[MotorController] Action: SPIN_RIGHT (Left=REV, Right=FWD)")

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
        """Performs pivot turn left by driving left wheels forward and stopping right wheels."""
        self._write_pins(in1=True, in2=False, in3=False, in4=False)
        self.state = "LEFT"
        logger.info("[MotorController] Action: PIVOT_LEFT (Left=FWD, Right=STOP)")

    def pivot_right(self):
        """Performs pivot turn right by stopping left wheels and driving right wheels forward."""
        self._write_pins(in1=False, in2=False, in3=True, in4=False)
        self.state = "RIGHT"
        logger.info("[MotorController] Action: PIVOT_RIGHT (Left=STOP, Right=FWD)")

    def stop(self):
        """Stops all motors by pulling all directional pins LOW (0V)."""
        self._write_pins(in1=False, in2=False, in3=False, in4=False)
        self.state = "STOPPED"
        logger.info("[MotorController] Action: STOP (All pins LOW / 0V)")

    def get_state(self) -> str:
        """Returns the current motor navigation state."""
        return self.state

    def cleanup(self):
        """Stops motors and safely closes GPIO hardware handles."""
        self.stop()
        if self.backend == "gpiozero":
            try:
                for dev in self._gpiozero_devices.values():
                    dev.close()
                logger.info("[MotorController] gpiozero devices closed.")
            except Exception:
                pass
        elif self.backend == "RPi.GPIO" and self.GPIO:
            try:
                self.GPIO.cleanup(tuple(self.pins))
                logger.info("[MotorController] RPi.GPIO pins cleaned up.")
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
    print("\n=================================================================")
    print("      AgriSentinel L298N Motor Driver Test Sequence")
    print("=================================================================")
    print("  Wiring Reference (BCM vs Physical Pin):")
    print("    IN1 -> BCM GPIO  5 (Physical Pin 29) [Left FWD]")
    print("    IN2 -> BCM GPIO  6 (Physical Pin 31) [Left REV]")
    print("    IN3 -> BCM GPIO 19 (Physical Pin 35) [Right FWD]")
    print("    IN4 -> BCM GPIO 26 (Physical Pin 37) [Right REV]")
    print("    ENA & ENB -> Fitted with 5V Onboard Jumper Caps")
    print("    GND       -> Common Ground Bus (e.g. Pin 20/39 to L298N GND)")
    print("-----------------------------------------------------------------")

    motors = MotorController()

    if motors.is_synthetic:
        print("\n [!] CRITICAL WARNING: SYNTHETIC MOCK MODE IS ACTIVE!")
        print("     Neither 'gpiozero' nor 'RPi.GPIO' could be accessed.")
        print("     Physical pins are NOT receiving electrical signals.")
        print("     To fix on Raspberry Pi OS Bookworm/Bullseye:")
        print("         pip install gpiozero lgpio")
        print("-----------------------------------------------------------------\n")
    else:
        print(f"\n [✓] HARDWARE ACTIVE: Using '{motors.backend}' backend.")
        print("     Live electrical signals ARE being driven to GPIO pins.\n")

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
