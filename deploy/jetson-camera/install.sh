#!/usr/bin/env bash
# Install the Jetson MJPEG camera service on the Orin Nano.
# Run on the Jetson itself: bash install.sh
set -euo pipefail

INSTALL_DIR="/opt/jetson-camera"
SERVICE_USER="${SERVICE_USER:-akshay}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ">>> Installing apt deps"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
  python3-pip python3-venv python3-gi gir1.2-gst-plugins-base-1.0

echo ">>> Creating $INSTALL_DIR"
sudo mkdir -p "$INSTALL_DIR"
sudo chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

echo ">>> Copying files"
install -m 0644 "$SCRIPT_DIR/camera_service.py" "$INSTALL_DIR/"
install -m 0644 "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"

echo ">>> Setting up venv (system-site-packages to inherit PyGObject/GStreamer)"
if [ ! -d "$INSTALL_DIR/.venv" ]; then
  python3 -m venv --system-site-packages "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

echo ">>> Installing systemd unit"
sudo cp "$SCRIPT_DIR/jetson-camera.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable jetson-camera
sudo systemctl restart jetson-camera

echo ">>> Done. Checking status:"
sleep 2
sudo systemctl status jetson-camera --no-pager | head -12 || true
echo
echo "Test with:  curl -s http://localhost:8001/health"
