#!/usr/bin/env python3
"""
AgriSentinel - Standalone Piezo Transducer & MOSFET Frequency Sweep Diagnostic Tool

Validates hardware PWM generation, MOSFET gate switching, and acoustic/ultrasonic
frequency sweeps (e.g., 19 kHz - 28 kHz for crop protection deterrence).

Usage:
    # Run default frequency sweep (19 kHz to 28 kHz @ 500 Hz steps)
    python -m edge.piezo_test

    # Run continuous sweep in a loop
    python -m edge.piezo_test --loop

    # Run fixed-frequency test tone (e.g., 20 kHz for 3 seconds)
    python -m edge.piezo_test --tone 20000 --duration 3.0

    # Run audible test tone (e.g., 2.5 kHz to hear with human ears)
    python -m edge.piezo_test --tone 2500 --duration 1.5

    # Customize sweep parameters
    python -m edge.piezo_test --start-hz 18000 --end-hz 25000 --step 250 --delay 0.02
"""

import os
import sys
import time
import atexit
import argparse
import logging

# Ensure repository root is on sys.path for direct module invocation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from edge.drivers.piezo import PiezoBuzzer, PIEZO_GPIO_PIN

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AgriSentinel-PiezoTest")


def print_banner(pin: int, mode_desc: str):
    """Displays hardware wiring and diagnostic configuration banner."""
    print("\n" + "=" * 74)
    print("      AgriSentinel Piezo Transducer & MOSFET Frequency Test")
    print("=" * 74)
    print("  Hardware Wiring Reference:")
    print("    MOSFET Gate   -> Raspberry Pi Pin 33 (BCM GPIO 13 / Hardware PWM1)")
    print("    MOSFET Source -> Raspberry Pi Pin 34 (GND / Common Ground Bus)")
    print("    MOSFET Drain  -> Piezo Transducer Negative (-) lead")
    print("    Piezo (+)     -> External Supply Rail (+5V or +12V VCC)")
    print("    Pull-down     -> 10k resistor between Gate (Pin 33) and GND (Pin 34)")
    print("--------------------------------------------------------------------------")
    print(f"  Target GPIO Pin : BCM {pin} (Physical Pin 33)")
    print(f"  Test Mode       : {mode_desc}")
    print("--------------------------------------------------------------------------")
    print("  Press [Ctrl + C] at any time to safely terminate and pull gate LOW.")
    print("=" * 74 + "\n")


def run_piezo_sweep(
    piezo_instance: PiezoBuzzer,
    start_hz: int = 19000,
    end_hz: int = 28000,
    step: int = 500,
    delay: float = 0.05,
    duty_cycle: float = 0.5,
):
    """
    Executes a frequency sweep while printing live terminal progress.
    Guarantees gate is pulled LOW in finally block upon completion or interruption.
    """
    direction = 1 if end_hz >= start_hz else -1
    total_steps = abs(end_hz - start_hz) // step + 1

    print(
        f"[*] Starting frequency sweep: {start_hz} Hz -> {end_hz} Hz "
        f"(step: {step} Hz, delay: {delay * 1000:.0f}ms, duty: {duty_cycle * 100:.0f}%)..."
    )

    piezo_instance.start(frequency=start_hz, duty_cycle=duty_cycle)
    try:
        step_idx = 1
        for freq in range(start_hz, end_hz + direction, direction * step):
            piezo_instance.set_frequency(freq)
            bar_len = 25
            progress = step_idx / max(1, total_steps)
            filled = int(bar_len * progress)
            bar = "#" * filled + "-" * (bar_len - filled)

            # Categorize frequency band
            band = "AUDIBLE" if freq < 19000 else "ULTRASONIC"
            sys.stdout.write(
                f"\r  [{bar}] {progress * 100:5.1f}% | Freq: {freq:5d} Hz ({band:10s})"
            )
            sys.stdout.flush()
            time.sleep(delay)
            step_idx += 1

        print("\n[*] Frequency sweep cycle completed successfully.")
    finally:
        piezo_instance.stop()


def run_piezo_tone(
    piezo_instance: PiezoBuzzer,
    frequency: int = 20000,
    duration: float = 2.0,
    duty_cycle: float = 0.5,
):
    """Emits a single fixed-frequency tone burst."""
    band = "AUDIBLE" if frequency < 19000 else "ULTRASONIC"
    print(f"[*] Emitting fixed tone: {frequency} Hz ({band}) for {duration:.1f}s (duty: {duty_cycle * 100:.0f}%)...")
    try:
        piezo_instance.start(frequency=frequency, duty_cycle=duty_cycle)
        elapsed = 0.0
        step = 0.1
        while elapsed < duration:
            time.sleep(min(step, duration - elapsed))
            elapsed += step
            sys.stdout.write(f"\r  Progress: {min(100.0, (elapsed / duration) * 100):5.1f}% [{elapsed:.1f}s / {duration:.1f}s]")
            sys.stdout.flush()
        print("\n[*] Tone burst completed.")
    finally:
        piezo_instance.stop()


# Aliases to match user code convention
test_piezo_sweep = run_piezo_sweep
test_piezo_tone = run_piezo_tone
# Tell pytest not to collect these as test functions
run_piezo_sweep.__test__ = False
test_piezo_sweep.__test__ = False
run_piezo_tone.__test__ = False
test_piezo_tone.__test__ = False


def main():
    parser = argparse.ArgumentParser(
        description="AgriSentinel Piezo Transducer & MOSFET Frequency Test Utility"
    )
    parser.add_argument(
        "--pin",
        type=int,
        default=PIEZO_GPIO_PIN,
        help=f"BCM GPIO pin connected to MOSFET Gate (default: {PIEZO_GPIO_PIN})",
    )
    parser.add_argument(
        "--tone",
        type=int,
        default=None,
        help="Emit a constant single frequency tone in Hz instead of sweeping (e.g. 2500 or 20000)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=2.0,
        help="Duration of single tone burst in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--start-hz",
        type=int,
        default=19000,
        help="Sweep starting frequency in Hz (default: 19000)",
    )
    parser.add_argument(
        "--end-hz",
        type=int,
        default=28000,
        help="Sweep ending frequency in Hz (default: 28000)",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=500,
        help="Sweep step increment in Hz (default: 500)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="Sweep delay per frequency step in seconds (default: 0.05)",
    )
    parser.add_argument(
        "--duty",
        type=float,
        default=0.5,
        help="PWM duty cycle between 0.0 and 1.0 (default: 0.5 for square wave)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Continuously repeat the test sequence until Ctrl+C",
    )

    args = parser.parse_args()

    mode_str = (
        f"Constant Tone @ {args.tone} Hz ({args.duration}s)"
        if args.tone is not None
        else f"Frequency Sweep: {args.start_hz} Hz -> {args.end_hz} Hz (step {args.step} Hz, delay {args.delay}s)"
    )
    if args.loop:
        mode_str += " [CONTINUOUS REPEAT]"

    print_banner(args.pin, mode_str)

    # Instantiate buzzer driver
    device = PiezoBuzzer(pin=args.pin)

    # Register safety exit handler to ensure gate is never left HIGH
    def safe_exit():
        device.close()

    atexit.register(safe_exit)

    try:
        while True:
            if args.tone is not None:
                test_piezo_tone(
                    piezo_instance=device,
                    frequency=args.tone,
                    duration=args.duration,
                    duty_cycle=args.duty,
                )
            else:
                test_piezo_sweep(
                    piezo_instance=device,
                    start_hz=args.start_hz,
                    end_hz=args.end_hz,
                    step=args.step,
                    delay=args.delay,
                    duty_cycle=args.duty,
                )

            if not args.loop:
                break

            print("[*] Pausing 1.0s before next cycle...")
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\n\n[!] Interrupted by user. Shutting down safely...")
    finally:
        device.close()
        print("[*] MOSFET gate pulled LOW. Test ended.\n")


if __name__ == "__main__":
    main()
