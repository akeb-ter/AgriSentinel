#!/usr/bin/env python3
"""
AgriSentinel - Standalone GPS Module Diagnostic & Monitoring Tool

Performs continuous live monitoring and hardware debugging for the
GY-NEO6MV2 / GY-GPS6MV2 (u-blox NEO-6M core) GPS module on Raspberry Pi 4.

Runs in a continuous loop until interrupted by the user with Ctrl+C.
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime

# Add repository root to path for direct invocation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from edge.drivers.gps import GPSReader, GPS_SERIAL_PORT, GPS_BAUD_RATE


def print_banner(port: str, baudrate: int, raw_mode: bool):
    """Prints diagnostic connection and wiring instructions banner."""
    print("\n" + "=" * 70)
    print("      AgriSentinel GY-NEO6MV2 / GY-GPS6MV2 GPS Module Diagnostic")
    print("=" * 70)
    print("  Hardware Wiring Reference:")
    print("    GPS VCC -> Raspberry Pi Pin 1 (3.3V Power) or Pin 2 (5V)")
    print("    GPS GND -> Raspberry Pi Pin 6, 9, 14, 20 (Common Ground)")
    print("    GPS TX  -> Raspberry Pi Pin 10 (BCM GPIO 15 / RXD0)  <-- Data from GPS")
    print("    GPS RX  -> Raspberry Pi Pin 8  (BCM GPIO 14 / TXD0)  <-- Data to GPS")
    print("----------------------------------------------------------------------")
    print(f"  Configuration:")
    print(f"    Target Serial Port : {port}")
    print(f"    Baud Rate          : {baudrate} baud")
    print(f"    Raw NMEA Display   : {'ENABLED' if raw_mode else 'DISABLED'}")
    print("----------------------------------------------------------------------")
    print("  Press [Ctrl + C] at any time to cleanly stop monitoring.")
    print("=" * 70 + "\n")


def run_continuous_gps_monitor(
    port: str = GPS_SERIAL_PORT,
    baudrate: int = GPS_BAUD_RATE,
    interval: float = 1.0,
    raw_mode: bool = False,
):
    """
    Executes a continuous, non-stop GPS monitoring loop.
    Exits only upon receiving a KeyboardInterrupt (Ctrl+C).
    """
    print_banner(port, baudrate, raw_mode)

    print(f"[*] Initializing GPS reader on {port} @ {baudrate} baud...")
    reader = GPSReader(port=port, baudrate=baudrate)

    if reader.serial_conn is None or not reader.serial_conn.is_open:
        print("\n[!] WARNING: Physical serial port could not be opened.")
        print(f"    Operating in Mock Fallback Mode.")
        print("    Troubleshooting checklist for Raspberry Pi 4:")
        print("      1. Ensure 'enable_uart=1' is in /boot/config.txt or /boot/firmware/config.txt")
        print("      2. Ensure serial console is disabled in raspi-config: sudo raspi-config -> Interface Options -> Serial")
        print("      3. Check user permissions: sudo usermod -a -G dialout $USER")
        print("      4. Check that 'pyserial' is installed: pip install pyserial")
        print("-" * 70 + "\n")
    else:
        print(f"[OK] Successfully opened serial interface: {port}")
        print("     Listening for incoming NMEA satellite sentences...\n")

    iteration = 0
    fix_acquired_count = 0
    start_time = time.time()

    try:
        while True:
            iteration += 1
            now_str = datetime.now().strftime("%H:%M:%S")

            # Read latest telemetry from GPS stream
            telemetry = reader.read_gps_data()
            lat = telemetry["latitude"]
            lon = telemetry["longitude"]
            alt = telemetry["altitude"]
            sats = telemetry["satellites"]
            has_fix = telemetry["gps_fix"]
            raw_sent = telemetry.get("raw_sentence", "")

            if has_fix:
                fix_acquired_count += 1
                status_tag = "\033[92m[FIX ACQUIRED (3D)]\033[0m"
                maps_url = f"https://maps.google.com/?q={lat:.6f},{lon:.6f}"
            else:
                status_tag = "\033[93m[SEARCHING / NO FIX]\033[0m"
                maps_url = "N/A (Waiting for satellite lock)"

            elapsed = int(time.time() - start_time)
            mins, secs = divmod(elapsed, 60)

            # Dashboard output
            print(f"[{now_str} | Uptime: {mins:02d}m {secs:02d}s | #{iteration:04d}] Status: {status_tag}")
            print(f"   -> Satellites Tracked : {sats}")
            print(f"   -> Latitude           : {lat:11.6f} deg")
            print(f"   -> Longitude          : {lon:11.6f} deg")
            print(f"   -> Altitude           : {alt:8.1f} m")

            if has_fix:
                print(f"   -> Location Pin       : {maps_url}")

            if raw_mode or (raw_sent and not has_fix):
                clean_raw = raw_sent.replace("\r", "").replace("\n", "")
                if clean_raw:
                    print(f"   -> Raw NMEA Line      : {clean_raw}")

            # Helpful diagnostic tips if no fix after 15 seconds
            if iteration == 15 and fix_acquired_count == 0:
                print("\n   [TIP] GPS Antenna Information:")
                print("         - Cold start for u-blox NEO-6M typically requires 1 to 3 minutes under open sky.")
                print("         - The small ceramic patch antenna must face upwards toward the sky.")
                print("         - If indoors or near concrete walls, move the module near a window or outdoors.")
                print("         - The tiny onboard LED will blink once every second when a 3D satellite fix is locked.\n")

            print("-" * 70)
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n" + "=" * 70)
        print("  [!] Continuous monitoring stopped by user (Ctrl+C).")
        print("=" * 70)

    finally:
        total_time = int(time.time() - start_time)
        print(f"  Session Summary:")
        print(f"    Total Duration    : {total_time} seconds")
        print(f"    Total Updates     : {iteration}")
        print(f"    Fix Acquired      : {'YES' if fix_acquired_count > 0 else 'NO'}")
        if fix_acquired_count > 0:
            print(f"    Last Known Lat/Lon: {reader.latitude:.6f}, {reader.longitude:.6f}")
        reader.close()
        print("  [OK] Serial connection closed cleanly. Goodbye!\n")


def main():
    parser = argparse.ArgumentParser(
        description="AgriSentinel Standalone Continuous GPS Module Diagnostic Tool"
    )
    parser.add_argument(
        "--port",
        "-p",
        default=GPS_SERIAL_PORT,
        help=f"Serial port device path (default: {GPS_SERIAL_PORT} or $GPS_SERIAL_PORT)",
    )
    parser.add_argument(
        "--baud",
        "-b",
        type=int,
        default=GPS_BAUD_RATE,
        help=f"Serial baud rate (default: {GPS_BAUD_RATE})",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=float,
        default=1.0,
        help="Telemetry refresh interval in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--raw",
        "-r",
        action="store_true",
        help="Always print raw NMEA sentences from GPS stream",
    )

    args = parser.parse_args()
    run_continuous_gps_monitor(
        port=args.port,
        baudrate=args.baud,
        interval=args.interval,
        raw_mode=args.raw,
    )


if __name__ == "__main__":
    main()

