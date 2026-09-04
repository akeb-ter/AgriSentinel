"""
Unit and integration tests for edge.drivers.piezo and edge.piezo_test modules.
"""

import time
import pytest
from edge.drivers.piezo import PiezoBuzzer
from edge.piezo_test import run_piezo_sweep, run_piezo_tone


def test_piezo_initialization():
    """Verify default initialization and diagnostic status."""
    device = PiezoBuzzer(pin=13, default_frequency=20000)
    assert device.pin == 13
    assert device.frequency == 20000
    assert device.duty_cycle == 0.0
    assert not device.is_active

    status = device.get_status()
    assert status["pin"] == 13
    assert status["frequency_hz"] == 20000
    assert status["duty_cycle"] == 0.0
    assert not status["is_active"]
    assert "backend" in status
    assert "is_synthetic" in status
    device.close()


def test_piezo_start_and_stop():
    """Verify start and stop toggle gate duty cycle and active state."""
    device = PiezoBuzzer(pin=13)
    assert not device.is_active

    device.start(frequency=22000, duty_cycle=0.5)
    assert device.is_active
    assert device.frequency == 22000
    assert device.duty_cycle == 0.5

    device.stop()
    assert not device.is_active
    assert device.duty_cycle == 0.0
    device.close()


def test_piezo_frequency_validation():
    """Verify frequency bounds checking."""
    device = PiezoBuzzer(pin=13)
    device.set_frequency(15000)
    assert device.frequency == 15000

    with pytest.raises(ValueError):
        device.set_frequency(0)

    with pytest.raises(ValueError):
        device.set_frequency(-500)

    device.close()


def test_piezo_tone_execution():
    """Verify fixed-tone burst executes and guarantees zero duty cycle afterwards."""
    device = PiezoBuzzer(pin=13)
    start_time = time.time()
    device.tone(frequency=24000, duration=0.05, duty_cycle=0.5)
    elapsed = time.time() - start_time

    assert elapsed >= 0.04
    assert not device.is_active
    assert device.duty_cycle == 0.0
    device.close()


def test_piezo_sweep_execution():
    """Verify frequency sweep executes across specified range and cleanly stops."""
    device = PiezoBuzzer(pin=13)
    device.sweep(start_hz=19000, end_hz=21000, step=1000, delay=0.01, duty_cycle=0.5)

    assert not device.is_active
    assert device.duty_cycle == 0.0
    assert device.frequency == 21000

    # Test invalid sweep inputs
    with pytest.raises(ValueError):
        device.sweep(start_hz=0, end_hz=20000, step=500)

    with pytest.raises(ValueError):
        device.sweep(start_hz=20000, end_hz=25000, step=0)

    device.close()


def test_piezo_close_cleanup():
    """Verify close safely shuts off output and handles multiple invocations."""
    device = PiezoBuzzer(pin=13)
    device.start(frequency=20000, duty_cycle=0.5)
    assert device.is_active

    device.close()
    assert not device.is_active
    assert device.duty_cycle == 0.0

    # Ensure second close() call is idempotent and does not raise
    device.close()


def test_cli_test_functions():
    """Verify the CLI diagnostic sweep and tone routines complete cleanly."""
    device = PiezoBuzzer(pin=13)
    # Quick micro-sweep
    run_piezo_sweep(
        piezo_instance=device,
        start_hz=19000,
        end_hz=20000,
        step=1000,
        delay=0.01,
        duty_cycle=0.5,
    )
    assert not device.is_active

    # Quick micro-tone
    run_piezo_tone(
        piezo_instance=device,
        frequency=20000,
        duration=0.05,
        duty_cycle=0.5,
    )
    assert not device.is_active
    device.close()
