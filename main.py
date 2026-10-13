import os
import uvicorn
import subprocess
import threading
import time
from edge.app import app


def get_network_info():
    """Retrieve current network mode and IP address."""
    mode = "Wi-Fi"
    ip_address = "Unknown"

    try:
        if subprocess.run(["which", "nmcli"], capture_output=True).returncode == 0:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "GENERAL.CONNECTION", "device", "show", "wlan0"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                conn_name = result.stdout.strip().split(":")[-1]
                if "AgriSentinel-Hotspot" in conn_name:
                    mode = "HOTSPOT"

            ip_result = subprocess.run(
                ["ip", "-4", "addr", "show", "wlan0"], capture_output=True, text=True
            )
            if ip_result.returncode == 0:
                for line in ip_result.stdout.split("\n"):
                    if "inet " in line:
                        ip_address = line.strip().split(" ")[1].split("/")[0]
                        break
    except Exception:
        pass

    return mode, ip_address


def wifi_watchdog_loop():
    """Background thread to force Wi-Fi rescan if disconnected, circumventing wpa_supplicant backoff."""
    while True:
        try:
            time.sleep(15)
            if subprocess.run(["which", "nmcli"], capture_output=True).returncode == 0:
                res = subprocess.run(
                    ["nmcli", "-t", "-f", "DEVICE,STATE", "dev"],
                    capture_output=True,
                    text=True,
                )
                if "wlan0:disconnected" in res.stdout:
                    subprocess.run(["nmcli", "device", "wifi", "rescan"], capture_output=True)
        except Exception:
            pass


def main():
    """Main entry point for AgriSentinel Smart Crop Probe."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    net_mode, ip_address = get_network_info()
    display_ip = ip_address if ip_address != "Unknown" else host

    print("\n==================================================")
    print(" AgriSentinel Smart Crop Probe Server Starting")
    print(" An AI-Powered Crop Protection System")
    print(f" Network Mode : {net_mode}")
    print(f" Probe IP     : {ip_address}")
    print(f" Local Domain : http://agrisentinel.local:{port}")
    print(f" Web Dashboard: http://{display_ip}:{port}")
    print("==================================================\n")

    # Start the Wi-Fi watchdog on Linux
    if os.name != "nt":
        watchdog = threading.Thread(target=wifi_watchdog_loop, daemon=True)
        watchdog.start()

    # Start the FastAPI server
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
