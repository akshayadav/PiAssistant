# Jetson Camera Service

MJPEG streaming service for the IMX219 CSI camera on Jetson Orin Nano Super. Runs on the Jetson, LAN-only. PiAssistant (Bunty) on the Pi proxies it publicly and handles auth.

## Prerequisites

1. IMX219 physically installed on CAM0.
2. Device-tree overlay enabled (one-time):
   ```bash
   sudo /opt/nvidia/jetson-io/config-by-hardware.py -n 2="Camera IMX219-A"
   sudo reboot
   ```
3. Verify `/dev/video0` exists after reboot:
   ```bash
   ls /dev/video0 && v4l2-ctl --list-devices
   ```

## Install

From the Jetson:

```bash
git clone <repo-url> ~/PiAssistant
cd ~/PiAssistant/deploy/jetson-camera
bash install.sh
```

## Config

Optional `.env` at `/opt/jetson-camera/.env`:

```
CAMERA_WIDTH=1280
CAMERA_HEIGHT=720
CAMERA_FRAMERATE=30
CAMERA_QUALITY=80
CAMERA_FLIP=0     # nvvidconv flip-method: 0=none, 2=180 (upside-down mount)
CAMERA_PORT=8001
```

Restart after editing: `sudo systemctl restart jetson-camera`.

## Endpoints

| Path | Purpose |
|---|---|
| `GET /health` | JSON — frame counter, resolution |
| `GET /snapshot.jpg` | Latest single JPEG frame |
| `GET /stream.mjpg` | `multipart/x-mixed-replace` MJPEG stream |

## Test

```bash
curl -s http://10.0.0.7:8001/health
# -> {"ok":true,"has_frame":true,...}

# In a browser: http://10.0.0.7:8001/snapshot.jpg
```

## Manage

```bash
sudo systemctl status jetson-camera
sudo journalctl -u jetson-camera -f
sudo systemctl restart jetson-camera
```
