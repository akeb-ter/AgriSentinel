import os
import uvicorn
import subprocess
from edge.camera_test import app

def get_network_info():
    """Retrieve current network mode and IP address."""
    mode = "Wi-Fi"
    ip_address = "Unknown"
    
    try:
        # Check if nmcli is available (Raspberry Pi/Linux)
        if subprocess.run(["which", "nmcli"], capture_output=True).returncode == 0:
            # Check the active connection on wlan0
            result = subprocess.run(["nmcli", "-t", "-f", "GENERAL.CONNECTION", "device", "show", "wlan0"], 
                                    capture_output=True, text=True)
            if result.returncode == 0:
                conn_name = result.stdout.strip().split(":")[-1]
                if "AgriSentinel-Hotspot" in conn_name:
                    mode = "HOTSPOT"
            
            # Get IP address
            ip_result = subprocess.run(["ip", "-4", "addr", "show", "wlan0"], capture_output=True, text=True)
            if ip_result.returncode == 0:
                for line in ip_result.stdout.split('\n'):
                    if "inet " in line:
                        ip_address = line.strip().split(' ')[1].split('/')[0]
                        break
    except Exception:
        pass # Silently fail on non-Linux/no-nmcli systems
        
    return mode, ip_address

def main():
    """Main entry point for AgriSentinel."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    net_mode, ip_address = get_network_info()
    display_ip = ip_address if ip_address != "Unknown" else host
    
    print("\n==================================================")
    print(" AgriSentinel Main Loop Starting")
    print(f" Network Mode : {net_mode}")
    print(f" Robot IP     : {ip_address}")
    print(f" Local Domain : http://agrisentinel.local:{port}")
    print(f" Web Interface: http://{display_ip}:{port}")
    print("==================================================\n")
    
    # Start the FastAPI server containing the camera stream and web interface
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()

