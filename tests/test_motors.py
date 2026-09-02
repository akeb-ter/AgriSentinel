import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from edge.drivers.motors import (
    MotorController,
    MOTOR_IN1_PIN,
    MOTOR_IN2_PIN,
    MOTOR_IN3_PIN,
    MOTOR_IN4_PIN,
    run_test_sequence,
)


class TestMotorController(unittest.TestCase):
    """Test suite for MotorController driver class."""

    def setUp(self):
        import logging
        self.logger = logging.getLogger("AgriSentinel-Motors")
        self.original_level = self.logger.level
        self.logger.setLevel(logging.CRITICAL)

    def tearDown(self):
        self.logger.setLevel(self.original_level)

    def test_motor_init_fallback_mode(self):
        """Verify MotorController gracefully enters synthetic/mock mode if RPi.GPIO is absent."""
        controller = MotorController(in1_pin=5, in2_pin=6, in3_pin=19, in4_pin=26)
        self.assertEqual(controller.state, "STOPPED")
        self.assertEqual(controller.get_state(), "STOPPED")
        self.assertEqual(controller.in1_pin, 5)
        self.assertEqual(controller.in2_pin, 6)
        self.assertEqual(controller.in3_pin, 19)
        self.assertEqual(controller.in4_pin, 26)

    def test_motor_forward_motion(self):
        """Verify forward() sets correct directional pins: IN1=1, IN2=0, IN3=1, IN4=0."""
        controller = MotorController(in1_pin=5, in2_pin=6, in3_pin=19, in4_pin=26)
        mock_gpio = MagicMock()
        controller.GPIO = mock_gpio
        controller.backend = "RPi.GPIO"
        controller.is_synthetic = False

        controller.forward()

        self.assertEqual(controller.get_state(), "FORWARD")
        mock_gpio.output.assert_has_calls([
            call(5, True),
            call(6, False),
            call(19, True),
            call(26, False),
        ])

    def test_motor_backward_and_reverse_motion(self):
        """Verify backward() and reverse() set correct pins: IN1=0, IN2=1, IN3=0, IN4=1."""
        controller = MotorController(in1_pin=5, in2_pin=6, in3_pin=19, in4_pin=26)
        mock_gpio = MagicMock()
        controller.GPIO = mock_gpio
        controller.backend = "RPi.GPIO"
        controller.is_synthetic = False

        controller.backward()
        self.assertEqual(controller.get_state(), "REVERSE")
        mock_gpio.output.assert_has_calls([
            call(5, False),
            call(6, True),
            call(19, False),
            call(26, True),
        ])

        mock_gpio.reset_mock()
        controller.reverse()
        self.assertEqual(controller.get_state(), "REVERSE")
        mock_gpio.output.assert_has_calls([
            call(5, False),
            call(6, True),
            call(19, False),
            call(26, True),
        ])

    def test_motor_skid_steer_spin_left_and_turn_left(self):
        """Verify spin_left(), turn_left(), and left() perform counter-rotation: IN1=0, IN2=1, IN3=1, IN4=0."""
        controller = MotorController(in1_pin=5, in2_pin=6, in3_pin=19, in4_pin=26)
        mock_gpio = MagicMock()
        controller.GPIO = mock_gpio
        controller.backend = "RPi.GPIO"
        controller.is_synthetic = False

        controller.spin_left()
        self.assertEqual(controller.get_state(), "LEFT")
        mock_gpio.output.assert_has_calls([
            call(5, False),
            call(6, True),
            call(19, True),
            call(26, False),
        ])

        mock_gpio.reset_mock()
        controller.turn_left()
        self.assertEqual(controller.get_state(), "LEFT")
        mock_gpio.output.assert_has_calls([
            call(5, False),
            call(6, True),
            call(19, True),
            call(26, False),
        ])

        mock_gpio.reset_mock()
        controller.left()
        self.assertEqual(controller.get_state(), "LEFT")
        mock_gpio.output.assert_has_calls([
            call(5, False),
            call(6, True),
            call(19, True),
            call(26, False),
        ])

    def test_motor_skid_steer_spin_right_and_turn_right(self):
        """Verify spin_right(), turn_right(), and right() perform counter-rotation: IN1=1, IN2=0, IN3=0, IN4=1."""
        controller = MotorController(in1_pin=5, in2_pin=6, in3_pin=19, in4_pin=26)
        mock_gpio = MagicMock()
        controller.GPIO = mock_gpio
        controller.backend = "RPi.GPIO"
        controller.is_synthetic = False

        controller.spin_right()
        self.assertEqual(controller.get_state(), "RIGHT")
        mock_gpio.output.assert_has_calls([
            call(5, True),
            call(6, False),
            call(19, False),
            call(26, True),
        ])

        mock_gpio.reset_mock()
        controller.turn_right()
        self.assertEqual(controller.get_state(), "RIGHT")
        mock_gpio.output.assert_has_calls([
            call(5, True),
            call(6, False),
            call(19, False),
            call(26, True),
        ])

        mock_gpio.reset_mock()
        controller.right()
        self.assertEqual(controller.get_state(), "RIGHT")
        mock_gpio.output.assert_has_calls([
            call(5, True),
            call(6, False),
            call(19, False),
            call(26, True),
        ])

    def test_motor_pivot_left_and_pivot_right(self):
        """Verify pivot turns (stopping inside wheels and powering outside wheels forward)."""
        controller = MotorController(in1_pin=5, in2_pin=6, in3_pin=19, in4_pin=26)
        mock_gpio = MagicMock()
        controller.GPIO = mock_gpio
        controller.backend = "RPi.GPIO"
        controller.is_synthetic = False

        # Pivot Left: Left wheels STOP (0, 0), Right wheels FWD (1, 0)
        controller.pivot_left()
        self.assertEqual(controller.get_state(), "LEFT")
        mock_gpio.output.assert_has_calls([
            call(5, False),
            call(6, False),
            call(19, True),
            call(26, False),
        ])

        # Pivot Right: Left wheels FWD (1, 0), Right wheels STOP (0, 0)
        mock_gpio.reset_mock()
        controller.pivot_right()
        self.assertEqual(controller.get_state(), "RIGHT")
        mock_gpio.output.assert_has_calls([
            call(5, True),
            call(6, False),
            call(19, False),
            call(26, False),
        ])

    def test_motor_stop_action(self):
        """Verify stop() pulls all directional pins to LOW."""
        controller = MotorController(in1_pin=5, in2_pin=6, in3_pin=19, in4_pin=26)
        mock_gpio = MagicMock()
        controller.GPIO = mock_gpio
        controller.backend = "RPi.GPIO"
        controller.is_synthetic = False

        controller.forward()
        mock_gpio.reset_mock()

        controller.stop()
        self.assertEqual(controller.get_state(), "STOPPED")
        mock_gpio.output.assert_has_calls([
            call(5, False),
            call(6, False),
            call(19, False),
            call(26, False),
        ])

    def test_motor_cleanup(self):
        """Verify cleanup() brings motors to stop and invokes GPIO cleanup on directional pins."""
        controller = MotorController(in1_pin=5, in2_pin=6, in3_pin=19, in4_pin=26)
        mock_gpio = MagicMock()
        controller.GPIO = mock_gpio
        controller.backend = "RPi.GPIO"
        controller.is_synthetic = False

        controller.cleanup()
        self.assertEqual(controller.get_state(), "STOPPED")
        mock_gpio.cleanup.assert_called_once_with((5, 6, 19, 26))

    @patch("time.sleep", return_value=None)
    def test_run_test_sequence_execution(self, mock_sleep):
        """Verify run_test_sequence executes full multi-directional test without exceptions."""
        with patch("edge.drivers.motors.MotorController") as mock_controller_cls:
            mock_instance = MagicMock()
            mock_controller_cls.return_value = mock_instance

            run_test_sequence(move_duration=0.01, pause_duration=0.01)

            mock_instance.forward.assert_called_once()
            mock_instance.backward.assert_called_once()
            mock_instance.left.assert_called_once()
            mock_instance.right.assert_called_once()
            mock_instance.pivot_left.assert_called_once()
            mock_instance.pivot_right.assert_called_once()
            self.assertGreaterEqual(mock_instance.stop.call_count, 6)
            mock_instance.cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
