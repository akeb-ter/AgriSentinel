#!/bin/bash
# AgriSentinel Hotspot Management Script
# Requires NetworkManager (nmcli)

HOTSPOT_NAME="AgriSentinel-Hotspot"
SSID="AgriSentinel"
PASSWORD="agri1234"
IFACE="wlan0"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function check_nmcli {
    if ! command -v nmcli &> /dev/null; then
        echo -e "${YELLOW}Error: nmcli could not be found. This script requires NetworkManager.${NC}"
        exit 1
    fi
}

function ensure_hotspot_exists {
    if ! nmcli connection show "$HOTSPOT_NAME" &> /dev/null; then
        echo -e "${BLUE}Creating hotspot profile '$HOTSPOT_NAME'...${NC}"
        sudo nmcli connection add type wifi ifname $IFACE con-name "$HOTSPOT_NAME" autoconnect no ssid "$SSID"
        sudo nmcli connection modify "$HOTSPOT_NAME" 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared
        sudo nmcli connection modify "$HOTSPOT_NAME" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASSWORD"
        echo -e "${GREEN}Hotspot profile created.${NC}"
    fi
}

function print_status {
    local ip_addr=$(ip -4 addr show $IFACE | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
    local current_conn=$(nmcli -t -f GENERAL.CONNECTION device show $IFACE 2>/dev/null | cut -d: -f2)

    echo "====================================="
    if [ "$current_conn" == "$HOTSPOT_NAME" ]; then
        echo -e "Status: ${GREEN}HOTSPOT ENABLED${NC}"
        echo "SSID:   $SSID"
        echo "Pass:   $PASSWORD"
        echo -e "IP:     ${BLUE}${ip_addr:-10.42.0.1}${NC}"
        echo -e "Domain: ${BLUE}http://agrisentinel.local:8000${NC}"
    else
        echo -e "Status: ${YELLOW}HOTSPOT DISABLED${NC} (Normal Wi-Fi mode)"
        echo "Current Network: $current_conn"
        echo -e "IP:     ${BLUE}${ip_addr:-Unknown}${NC}"
        echo -e "Domain: ${BLUE}http://agrisentinel.local:8000${NC}"
    fi
    echo "====================================="
}

function enable_hotspot {
    ensure_hotspot_exists
    echo -e "${BLUE}Enabling hotspot and setting to auto-connect on boot...${NC}"
    sudo nmcli connection modify "$HOTSPOT_NAME" autoconnect yes
    sudo nmcli connection up "$HOTSPOT_NAME"
    echo -e "${GREEN}Hotspot activated successfully.${NC}"
    echo ""
    
    # Ensure avahi-daemon is running for .local resolution
    sudo systemctl enable avahi-daemon &>/dev/null
    sudo systemctl start avahi-daemon &>/dev/null

    print_status
}

function disable_hotspot {
    ensure_hotspot_exists
    echo -e "${BLUE}Disabling hotspot and falling back to known Wi-Fi...${NC}"
    sudo nmcli connection modify "$HOTSPOT_NAME" autoconnect no
    sudo nmcli connection down "$HOTSPOT_NAME"
    echo -e "${GREEN}Hotspot disabled.${NC}"
    echo ""
    print_status
}

check_nmcli

case "$1" in
    enable)
        enable_hotspot
        ;;
    disable)
        disable_hotspot
        ;;
    status)
        print_status
        ;;
    *)
        echo "Usage: $0 {enable|disable|status}"
        exit 1
esac
