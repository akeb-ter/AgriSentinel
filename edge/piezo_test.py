#!/usr/bin/env python3
"""
AgriSentinel - Standalone Standard Buzzer Diagnostic & Testing Tool

Validates hardware GPIO pin output, rhythmic alert beeping, continuous DC sounding,
and audible PWM frequency tones on Raspberry Pi BCM GPIO 13 (Physical Pin 33).

Usage:
    # 1. Default quick test (emits 3 audible test beeps - works on both Active & Passive buzzers!)
    python -m edge.piezo_test

    # 2. Continuous DC ON for 2 seconds (ideal for testing Active Buzzers)
    python -m edge.piezo_test --on 2.0

    # 3. Emit 5 custom test beeps
    python -m edge.piezo_test --beep 5

    # 4. Continuous deterrent alarm beeping loop (press Ctrl+C to stop)
    python -m edge.piezo_test --loop

    # 5. Play audible tone at 2.5 kHz for 2 seconds (ideal for testing Passive Buzzers)
    python -m edge.piezo_test --tone 2500 --duration 2.0

    # 6. Audible siren frequency sweep (1 kHz to 3.5 kHz)
    python -m edge.piezo_test --sweep

    # 7. Test on a different GPIO pin (e.g. GPIO 17)
    python -m edge.piezo_test --pin 17
"""

import os
import sys
import time
import argparse
import logging

# Ensure repository root is on sys.path for direct module invocation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from edge.drivers.piezo import PiezoBuzzer, PIEZO_GPIO_PIN

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AgriSentinel-BuzzerTest")


def print_banner(pin: int, mode_desc: str):
    """Displays hardware wiring and diagnostic configuration banner."""
    print("\n" + "=" * 74)
    print("           AgriSentinel Standard Buzzer Diagnostic Tool")
    print("=" * 74)
    print("  Hardware Wiring Reference (Standard 2-Pin Buzzer):")
    print(f"    Buzzer Positive (+) (Long Lead)  -> Raspberry Pi Pin 33 (BCM GPIO {pin})")
    print("    Buzzer Negative (-) (Short Lead) -> Raspberry Pi Pin 34 (GND / Ground)")
    print("--------------------------------------------------------------------------")
    print(f"  Target GPIO Pin : BCM {pin} (Physical Pin 33)")
    print(f"  Test Mode       : {mode_desc}")
    print("--------------------------------------------------------------------------")
    print("  Press [Ctrl + C] at any time to safely terminate and silence buzzer.")
    print("=" * 74 + "\n")


def run_buzzer_beeps(
    buzzer_instance: PiezoBuzzer,
    count: int = 3,
    on_time: float = 0.2,
    off_time: float = 0.1,
    duty_cycle: float = 1.0,
):
    """Executes distinct test beeps with console progress."""
    print(f"[*] Emitting {count} test beeps (ON: {on_time*1000:.0f}ms, OFF: {off_time*1000:.0f}ms)...")
    try:
        for i in range(1, count + 1):
            sys.stdout.write(f"\r  -> Beep {i}/{count} [BEEP]")
            sys.stdout.flush()
            buzzer_instance.on()
            time.sleep(on_time)
            buzzer_instance.off()
            sys.stdout.write(f"\r  -> Beep {i}/{count} [....]")
            sys.stdout.flush()
            if i < count:
                time.sleep(off_time)
        print(f"\n[*] Completed {count} test beeps successfully.")
    finally:
        buzzer_instance.off()


def run_buzzer_continuous_on(buzzer_instance: PiezoBuzzer, duration: float = 2.0):
    """Turns buzzer continuously ON for a set duration (DC HIGH)."""
    print(f"[*] Turning buzzer continuously ON for {duration:.1f} seconds (Active Buzzer Test)...")
    try:
        buzzer_instance.on()
        elapsed = 0.0
        step = 0.1
        while elapsed < duration:
            time.sleep(min(step, duration - elapsed))
            elapsed += step
            pct = min(100.0, (elapsed / duration) * 100)
            sys.stdout.write(f"\r  Sounding: {pct:5.1f}% [{elapsed:.1f}s / {duration:.1f}s]")
            sys.stdout.flush()
        print("\n[*] Continuous sound completed.")
    finally:
        buzzer_instance.off()


def run_piezo_tone(
    piezo_instance: PiezoBuzzer,
    frequency: int = 2500,
    duration: float = 2.0,
    duty_cycle: float = 0.5,
):
    """Emits an audible PWM tone burst (Passive Buzzer Test)."""
    print(f"[*] Emitting audible tone: {frequency} Hz for {duration:.1f}s (duty: {duty_cycle * 100:.0f}%)...")
    try:
        piezo_instance.start(frequency=frequency, duty_cycle=duty_cycle)
        elapsed = 0.0
        step = 0.1
        while elapsed < duration:
            time.sleep(min(step, duration - elapsed))
            elapsed += step
            sys.stdout.write(
                f"\r  Tone Progress: {min(100.0, (elapsed / duration) * 100):5.1f}% [{elapsed:.1f}s / {duration:.1f}s]"
            )
            sys.stdout.flush()
        print("\n[*] Audible tone burst completed.")
    finally:
        piezo_instance.stop()


def run_piezo_sweep(
    piezo_instance: PiezoBuzzer,
    start_hz: int = 1000,
    end_hz: int = 3500,
    step: int = 250,
    delay: float = 0.03,
    duty_cycle: float = 0.5,
):
    """Executes an audible siren sweep across frequency range."""
    direction = 1 if end_hz >= start_hz else -1
    total_steps = abs(end_hz - start_hz) // step + 1

    print(
        f"[*] Starting audible siren sweep: {start_hz} Hz -> {end_hz} Hz "
        f"(step: {step} Hz, delay: {delay * 1000:.0f}ms)..."
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

            sys.stdout.write(
                f"\r  [{bar}] {progress * 100:5.1f}% | Freq: {freq:5d} Hz (AUDIBLE)"
            )
            sys.stdout.flush()
            time.sleep(delay)
            step_idx += 1

        print("\n[*] Audible siren sweep completed successfully.")
    finally:
        piezo_instance.stop()


def run_alarm_loop(buzzer_instance: PiezoBuzzer):
    """Runs a continuous pest-deterrent alarm sequence until Ctrl+C."""
    print("[*] Starting continuous deterrent alarm pattern. Press Ctrl+C to terminate.")
    cycle = 1
    try:
        while True:
            sys.stdout.write(f"\r[*] Alarm Cycle #{cycle}: Pulsing alert sequence... ")
            sys.stdout.flush()
            # 3 fast bursts of solid DC ON/OFF (works on active buzzers)
            for _ in range(3):
                buzzer_instance.on()
                time.sleep(0.15)
                buzzer_instance.off()
                time.sleep(0.08)
            # Brief pause between bursts
            time.sleep(0.4)
            cycle += 1
    except KeyboardInterrupt:
        print("\n[*] Deterrent alarm stopped by user.")
    finally:
        buzzer_instance.off()


# Backward compatibility aliases
test_piezo_sweep = run_piezo_sweep
test_piezo_tone = run_piezo_tone
run_buzzer_beeps.__test__ = False
run_buzzer_continuous_on.__test__ = False
run_alarm_loop.__test__ = False
run_piezo_sweep.__test__ = False
test_piezo_sweep.__test__ = False
run_piezo_tone.__test__ = False
test_piezo_tone.__test__ = False


def main():
    parser = argparse.ArgumentParser(
        description="AgriSentinel Standard Buzzer Diagnostic & Testing Tool"
    )
    parser.add_argument(
        "--pin",
        type=int,
        default=PIEZO_GPIO_PIN,
        help=f"BCM GPIO pin connected to Buzzer Positive lead (default: {PIEZO_GPIO_PIN})",
    )
    parser.add_argument(
        "--on",
        type=float,
        nargs="?",
        const=2.0,
        default=None,
        help="Turn buzzer continuously ON for specified seconds (default: 2.0s, Active Buzzer test)",
    )
    parser.add_argument(
        "--beep",
        type=int,
        nargs="?",
        const=3,
        default=None,
        help="Emit specified number of test beeps (default: 3 beeps)",
    )
    parser.add_argument(
        "--tone",
        type=int,
        default=None,
        help="Emit audible PWM tone at given frequency in Hz (e.g., 2500, Passive Buzzer test)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=2.0,
        help="Duration in seconds for tone or continuous test (default: 2.0s)",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Execute an audible siren frequency sweep (1 kHz to 3.5 kHz)",
    )
    parser.add_argument(
        "--alarm",
        action="store_true",
        help="Run a 3-second rapid pest deterrent alarm burst",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuous deterrent alarm pattern indefinitely until Ctrl+C",
    )

    args = parser.parse_args()

    # Determine mode description
    if args.loop:
        mode_desc = "Continuous Deterrent Alarm Loop (--loop)"
    elif args.alarm:
        mode_desc = "3-Second Deterrent Alarm Burst (--alarm)"
    elif args.on is not None:
        mode_desc = f"Continuous DC ON for {args.on:.1f}s (--on)"
    elif args.tone is not None:
        mode_desc = f"Audible PWM Tone @ {args.tone} Hz for {args.duration:.1f}s (--tone)"
    elif args.sweep:
        mode_desc = "Audible Siren Sweep 1 kHz -> 3.5 kHz (--sweep)"
    elif args.beep is not None:
        mode_desc = f"{args.beep} Alert Beep Pulses (--beep)"
    else:
        mode_desc = "Default Quick Verification (3 Audible Beeps)"

    print_banner(args.pin, mode_desc)

    device = PiezoBuzzer(pin=args.pin)
    print(f"[*] Initialized Buzzer Driver (Backend: {device.backend}, Synthetic: {device.is_synthetic})")

    try:
        if args.loop:
            run_alarm_loop(device)
        elif args.alarm:
            print("[*] Emitting rapid deterrent alarm pattern for 3.0s...")
            device.alarm(duration=3.0, pattern="fast")
            print("[*] Alarm completed.")
        elif args.on is not None:
            run_buzzer_continuous_on(device, duration=args.on)
        elif args.tone is not None:
            run_piezo_tone(device, frequency=args.tone, duration=args.duration)
        elif args.sweep:
            run_piezo_sweep(device, start_hz=1000, end_hz=3500, step=250, delay=0.03)
        elif args.beep is not None:
            run_buzzer_beeps(device, count=args.beep)
        else:
            # Default action: 3 quick beeps
            run_buzzer_beeps(device, count=3)

    except KeyboardInterrupt:
        print("\n[*] Interrupted by user. Shutting down safely...")
    finally:
        device.close()
        print("[*] Diagnostic finished. Pin pulled LOW.\n")


if __name__ == "__main__":
    main()
