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

# Configure the connection profile in NetworkManager so it is remembered
# even if the hotspot is not currently turned on or in range.
if nmcli connection show "$SSID" >/dev/null 2>&1; then
    echo "Updating existing connection profile for $SSID..."
    if [ -n "$PASS" ]; then
        sudo nmcli connection modify "$SSID" 802-11-wireless-security.key-mgmt wpa-psk 802-11-wireless-security.psk "$PASS"
    else
        sudo nmcli connection modify "$SSID" 802-11-wireless-security.key-mgmt ""
    fi
else
    echo "Creating new connection profile for $SSID..."
    if [ -n "$PASS" ]; then
        sudo nmcli connection add type wifi con-name "$SSID" ifname wlan0 ssid "$SSID" \
            wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASS"
    else
        sudo nmcli connection add type wifi con-name "$SSID" ifname wlan0 ssid "$SSID"
    fi
fi

# Set to autoconnect on boot with infinite retries (0 = never give up)
sudo nmcli connection modify "$SSID" connection.autoconnect yes
sudo nmcli connection modify "$SSID" connection.autoconnect-retries 0
echo "Autoconnect enabled with infinite retries for '$SSID'."

# Attempt to connect right now if the network is currently in range
echo "Attempting to activate connection..."
if sudo nmcli connection up "$SSID"; then
    echo "Successfully connected to $SSID."
else
    echo "Network '$SSID' is not currently in range or turned on."
    echo "Profile saved! The Raspberry Pi will automatically connect as soon as the hotspot is turned on."
fi
