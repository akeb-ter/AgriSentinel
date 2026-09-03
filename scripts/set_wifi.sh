#!/bin/bash
# set_wifi.sh
# Connects to a target Wi-Fi network using NetworkManager (nmcli)

SSID=""
PASS=""

# Parse arguments
for i in "$@"; do
  case $i in
    --ssid=*)
      SSID="${i#*=}"
      shift
      ;;
    --pass=*)
      PASS="${i#*=}"
      shift
      ;;
    *)
      # unknown option
      ;;
  esac
done

if [ -z "$SSID" ]; then
    echo "Error: --ssid is required."
    exit 1
fi

echo "Setting up Wi-Fi connection for SSID: $SSID"

if [ -z "$PASS" ]; then
    echo "No password provided. Attempting to connect to an open network..."
    sudo nmcli device wifi connect "$SSID"
else
    echo "Password provided. Attempting to connect to a secure network..."
    sudo nmcli device wifi connect "$SSID" password "$PASS"
fi

if [ $? -eq 0 ]; then
    echo "Successfully connected to $SSID."
    
    # Ensure it is set to autoconnect
    sudo nmcli connection modify "$SSID" connection.autoconnect yes
    echo "Autoconnect enabled for $SSID."
else
    echo "Failed to connect to $SSID. Please check the credentials and signal strength."
    exit 1
fi
