"""
Unit and integration tests for edge.drivers.piezo and edge.piezo_test modules.
Tests standard buzzer support (Active and Passive modes).
"""

import time
import pytest
from edge.drivers.piezo import PiezoBuzzer
from edge.piezo_test import (
    run_buzzer_beeps,
    run_buzzer_continuous_on,
    run_piezo_sweep,
    run_piezo_tone,
)


def test_piezo_initialization():
    """Verify default initialization and diagnostic status."""
    device = PiezoBuzzer(pin=13, default_frequency=2500)
    assert device.pin == 13
    assert device.frequency == 2500
    assert device.duty_cycle == 0.0
    assert not device.is_active

    status = device.get_status()
    assert status["pin"] == 13
    assert status["frequency_hz"] == 2500
    assert status["duty_cycle"] == 0.0
    assert not status["is_active"]
    assert "backend" in status
    assert "is_synthetic" in status
    device.close()


def test_buzzer_digital_on_and_off():
    """Verify digital on() and off() for active buzzer operation."""
    device = PiezoBuzzer(pin=13)
    assert not device.is_active

    device.on()
    assert device.is_active
    assert device.duty_cycle == 1.0

    device.off()
    assert not device.is_active
    assert device.duty_cycle == 0.0
    device.close()


def test_piezo_start_and_stop():
    """Verify start and stop toggle duty cycle and active state."""
    device = PiezoBuzzer(pin=13)
    assert not device.is_active

    device.start(frequency=2800, duty_cycle=0.5)
    assert device.is_active
    assert device.frequency == 2800
    assert device.duty_cycle == 0.5

    device.stop()
    assert not device.is_active
    assert device.duty_cycle == 0.0
    device.close()


def test_piezo_frequency_validation():
    """Verify frequency bounds checking."""
    device = PiezoBuzzer(pin=13)
    device.set_frequency(3000)
    assert device.frequency == 3000

    with pytest.raises(ValueError):
        device.set_frequency(0)

    with pytest.raises(ValueError):
        device.set_frequency(-500)

    device.close()


def test_buzzer_beep_execution():
    """Verify pulsed beep routine completes cleanly."""
    device = PiezoBuzzer(pin=13)
    device.beep(on_time=0.01, off_time=0.01, n=2)
    assert not device.is_active
    assert device.duty_cycle == 0.0
    device.close()


def test_piezo_tone_execution():
    """Verify fixed-tone burst executes and guarantees zero duty cycle afterwards."""
    device = PiezoBuzzer(pin=13)
    start_time = time.time()
    device.tone(frequency=2500, duration=0.05, duty_cycle=0.5)
    elapsed = time.time() - start_time

    assert elapsed >= 0.04
    assert not device.is_active
    assert device.duty_cycle == 0.0
    device.close()


def test_buzzer_alarm_execution():
    """Verify deterrent alarm pattern runs for specified duration."""
    device = PiezoBuzzer(pin=13)
    start_time = time.time()
    device.alarm(duration=0.15, pattern="fast")
    elapsed = time.time() - start_time

    assert elapsed >= 0.10
    assert not device.is_active
    assert device.duty_cycle == 0.0
    device.close()


def test_piezo_sweep_execution():
    """Verify audible frequency sweep executes across specified range and cleanly stops."""
    device = PiezoBuzzer(pin=13)
    device.sweep(start_hz=1000, end_hz=1500, step=250, delay=0.01, duty_cycle=0.5)

    assert not device.is_active
    assert device.duty_cycle == 0.0
    assert device.frequency == 1500

    # Test invalid sweep inputs
    with pytest.raises(ValueError):
        device.sweep(start_hz=0, end_hz=2000, step=500)

    with pytest.raises(ValueError):
        device.sweep(start_hz=2000, end_hz=2500, step=0)

    device.close()


def test_piezo_close_cleanup():
    """Verify close safely shuts off output and handles multiple invocations."""
    device = PiezoBuzzer(pin=13)
    device.start(frequency=2500, duty_cycle=0.5)
    assert device.is_active

    device.close()
    assert not device.is_active
    assert device.duty_cycle == 0.0

    # Ensure second close() call is idempotent and does not raise
    device.close()


def test_cli_test_functions():
    """Verify the CLI diagnostic helpers complete cleanly."""
    device = PiezoBuzzer(pin=13)

    # Test beeps helper
    run_buzzer_beeps(buzzer_instance=device, count=2, on_time=0.01, off_time=0.01)
    assert not device.is_active

    # Test continuous on helper
    run_buzzer_continuous_on(buzzer_instance=device, duration=0.05)
    assert not device.is_active

    # Quick micro-sweep
    run_piezo_sweep(
        piezo_instance=device,
        start_hz=1000,
        end_hz=1200,
        step=200,
        delay=0.01,
        duty_cycle=0.5,
    )
    assert not device.is_active

    # Quick micro-tone
    run_piezo_tone(
        piezo_instance=device,
        frequency=2500,
        duration=0.05,
        duty_cycle=0.5,
    )
    assert not device.is_active
    device.close()
