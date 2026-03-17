#!/usr/bin/env bash
# PiAssistant Pi 5 setup script
# Run on a fresh Raspberry Pi OS Lite (64-bit, Bookworm)
# Usage: bash setup.sh

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/akshayballal/PiAssistant.git}"
INSTALL_DIR="$HOME/PiAssistant"
SERVICE_NAME="piassistant"

echo "=== PiAssistant Pi 5 Setup ==="

# --- System packages ---
echo ">> Updating system..."
sudo apt update && sudo apt full-upgrade -y

echo ">> Installing dependencies..."
sudo apt install -y git python3-venv python3-pip mosquitto mosquitto-clients cage chromium

# --- Mosquitto ---
echo ">> Configuring Mosquitto..."
sudo cp "$INSTALL_DIR/deploy/mosquitto.conf" /etc/mosquitto/conf.d/piassistant.conf 2>/dev/null || true
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto

# --- Clone repo ---
if [ -d "$INSTALL_DIR" ]; then
    echo ">> $INSTALL_DIR already exists, pulling latest..."
    cd "$INSTALL_DIR"
    git pull
else
    echo ">> Cloning PiAssistant..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# --- Python venv ---
echo ">> Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

# --- .env file ---
if [ ! -f .env ]; then
    cp .env.example .env
    echo ">> Created .env from template — edit it with your API keys:"
    echo "   nano $INSTALL_DIR/.env"
else
    echo ">> .env already exists, skipping."
fi

# --- systemd services ---
echo ">> Installing systemd services..."
# Replace %i with actual username and %U with UID in service files
sed "s/%i/$USER/g" deploy/piassistant.service | sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null
sed "s/%i/$USER/g; s/%U/$(id -u)/g" deploy/piassistant-kiosk.service | sudo tee /etc/systemd/system/${SERVICE_NAME}-kiosk.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl enable "${SERVICE_NAME}-kiosk"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit API keys:  nano $INSTALL_DIR/.env"
echo "  2. Start service:  sudo systemctl start $SERVICE_NAME"
echo "  3. Check status:   sudo systemctl status $SERVICE_NAME"
echo "  4. View logs:      journalctl -u $SERVICE_NAME -f"
echo ""
echo "Optional — install Tailscale for remote access:"
echo "  curl -fsSL https://tailscale.com/install.sh | sh"
echo "  sudo tailscale up"
