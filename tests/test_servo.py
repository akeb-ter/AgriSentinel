"""
Unit tests for edge.drivers.servo module (SG90 / MG996R Camera Pan Servo Controller).
Uses standard unittest framework with unittest.mock.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from edge.drivers.servo import (
    ServoController,
    SERVO_GPIO_PIN,
    MIN_ANGLE,
    MAX_ANGLE,
    STEP_ANGLE,
    run_test_sequence,
)


class TestServoController(unittest.TestCase):
    """Test suite for ServoController driver class."""

    def setUp(self):
        import logging
        self.logger = logging.getLogger("AgriSentinel-Servo")
        self.original_level = self.logger.level
        self.logger.setLevel(logging.CRITICAL)

    def tearDown(self):
        self.logger.setLevel(self.original_level)

    def test_servo_init_mock_fallback(self):
        """Verify ServoController initializes in synthetic fallback mode when hardware is absent."""
        servo = ServoController(pin=18, min_angle=-60, max_angle=60)
        self.assertEqual(servo.pin, 18)
        self.assertEqual(servo.min_angle, -60)
        self.assertEqual(servo.max_angle, 60)
        self.assertEqual(servo.current_angle, 0.0)
        self.assertEqual(servo.get_angle(), 0.0)
        self.assertIn(servo.backend, ["gpiozero", "RPi.GPIO", "SYNTHETIC"])

    def test_servo_angle_clamping(self):
        """Verify set_angle clamps values strictly within min_angle and max_angle bounds."""
        servo = ServoController(pin=18, min_angle=-60, max_angle=60)

        # Inside bounds
        servo.set_angle(25.4)
        self.assertEqual(servo.get_angle(), 25.4)

        servo.set_angle(-45.0)
        self.assertEqual(servo.get_angle(), -45.0)

        # Exceeds max bound (+90° clamped to +60°)
        servo.set_angle(90.0)
        self.assertEqual(servo.get_angle(), 60.0)

        # Below min bound (-120° clamped to -60°)
        servo.set_angle(-120.0)
        self.assertEqual(servo.get_angle(), -60.0)

    def test_servo_center_and_limits(self):
        """Verify center(), pan_left(), and pan_right() move to exact designated angles."""
        servo = ServoController(pin=18, min_angle=-60, max_angle=60)

        servo.pan_left()
        self.assertEqual(servo.get_angle(), -60.0)

        servo.center()
        self.assertEqual(servo.get_angle(), 0.0)

        servo.pan_right()
        self.assertEqual(servo.get_angle(), 60.0)

    def test_servo_sweep_step_progression_and_reversal(self):
        """Verify sweep_step advances angle and correctly reverses direction at limits."""
        servo = ServoController(pin=18, min_angle=-60, max_angle=60)
        servo.center()
        self.assertEqual(servo.current_angle, 0.0)
        self.assertEqual(servo.sweep_direction, 1)

        # Step 1: 0 -> 20
        new_ang = servo.sweep_step(20)
        self.assertEqual(new_ang, 20.0)

        # Step 2: 20 -> 40
        new_ang = servo.sweep_step(20)
        self.assertEqual(new_ang, 40.0)

        # Step 3: 40 -> 60 (hits max bound, reverses direction)
        new_ang = servo.sweep_step(20)
        self.assertEqual(new_ang, 60.0)
        self.assertEqual(servo.sweep_direction, -1)

        # Step 4: 60 -> 40 (decrements)
        new_ang = servo.sweep_step(20)
        self.assertEqual(new_ang, 40.0)

        # Step all the way to min bound (-60)
        for _ in range(5):
            servo.sweep_step(20)
        self.assertEqual(servo.current_angle, -60.0)
        self.assertEqual(servo.sweep_direction, 1)

    def test_servo_gpiozero_backend_mock(self):
        """Verify interaction with gpiozero.AngularServo mock handle."""
        servo = ServoController(pin=18, min_angle=-60, max_angle=60)
        mock_servo_dev = MagicMock()
        servo._servo = mock_servo_dev
        servo.backend = "gpiozero"
        servo.is_synthetic = False

        # Set angle
        servo.set_angle(30.0)
        self.assertEqual(mock_servo_dev.angle, 30.0)

        # Detach
        servo.detach()
        self.assertIsNone(mock_servo_dev.value)

        # Close
        servo.close()
        mock_servo_dev.close.assert_called_once()

    def test_servo_rpigpio_backend_mock(self):
        """Verify interaction and 50Hz PWM duty cycle calculation with RPi.GPIO mock."""
        servo = ServoController(pin=18, min_angle=-60, max_angle=60)
        mock_pwm = MagicMock()
        mock_gpio = MagicMock()
        servo._pwm = mock_pwm
        servo.GPIO = mock_gpio
        servo.backend = "RPi.GPIO"
        servo.is_synthetic = False

        # 0 degrees: duty = 2.5 + ((0 + 90) / 180) * 10 = 7.5%
        servo.center()
        mock_pwm.ChangeDutyCycle.assert_called_with(7.5)

        # -90 degrees (min pulse 0.5ms): duty = 2.5%
        # At -60 degrees: duty = round(2.5 + ((30) / 180) * 10, 2) = 4.17%
        servo.pan_left()
        mock_pwm.ChangeDutyCycle.assert_called_with(4.17)

        # Detach: duty cycle 0
        servo.detach()
        mock_pwm.ChangeDutyCycle.assert_called_with(0)

        # Cleanup
        servo.close()
        mock_pwm.stop.assert_called_once()
        mock_gpio.cleanup.assert_called_once_with(18)

    @patch("time.sleep", return_value=None)
    def test_run_test_sequence_execution(self, mock_sleep):
        """Verify run_test_sequence executes full calibration and sweep routine without errors."""
        with patch("edge.drivers.servo.ServoController") as mock_servo_cls:
            mock_inst = MagicMock()
            mock_inst.min_angle = -60
            mock_inst.max_angle = 60
            mock_inst.sweep_step.return_value = 10.0
            mock_servo_cls.return_value = mock_inst

            run_test_sequence()

            mock_inst.center.assert_called()
            mock_inst.pan_left.assert_called_once()
            mock_inst.pan_right.assert_called_once()
            mock_inst.detach.assert_called()
            mock_inst.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
