# Deploying PiAssistant to Raspberry Pi 5

## Prerequisites

- Raspberry Pi 5 (16GB)
- microSD card (32GB+)
- Raspberry Pi OS Lite 64-bit (Bookworm) flashed via Raspberry Pi Imager

### Imager Settings (gear icon)

- Hostname: `PiAssistant-Mothership`
- Enable SSH
- Set username/password
- Configure WiFi
- Set locale/timezone

## Quick Setup

SSH into the Pi, clone the repo, then run the setup script:

```bash
ssh <username>@piassistant-mothership.local

# Clone first (setup script expects the repo)
git clone https://github.com/<username>/PiAssistant.git
cd PiAssistant

# Run setup
bash deploy/setup.sh
```

Then edit your API keys and start:

```bash
nano ~/PiAssistant/.env
sudo systemctl start piassistant
```

## Manual Setup

If you prefer step-by-step:

### 1. System packages

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git python3-venv python3-pip mosquitto mosquitto-clients
```

### 2. Mosquitto

```bash
sudo cp deploy/mosquitto.conf /etc/mosquitto/conf.d/piassistant.conf
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto
```

### 3. Python environment

```bash
cd ~/PiAssistant
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
nano .env   # add ANTHROPIC_API_KEY and NEWSAPI_KEY
```

### 4. Test manually

```bash
source .venv/bin/activate
python -m piassistant
# In another terminal:
curl http://piassistant-mothership.local:8000/api/health
```

### 5. systemd service

```bash
# Replace <username> with your Pi username
sed "s/%i/<username>/g" deploy/piassistant.service | sudo tee /etc/systemd/system/piassistant.service
sudo systemctl daemon-reload
sudo systemctl enable piassistant
sudo systemctl start piassistant
```

### 6. Tailscale (optional, for remote access)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# Follow auth URL, then disable key expiry in admin console
```

## Managing the Service

```bash
sudo systemctl status piassistant    # Check status
sudo systemctl restart piassistant   # Restart
journalctl -u piassistant -f         # Live logs
journalctl -u piassistant --since "10 min ago"  # Recent logs
```

## Using CLI from Mac

The CLI can connect to the Pi server remotely:

```bash
# On Mac
cd /path/to/PiAssistant
source .venv/bin/activate
PIASSISTANT_URL=http://piassistant-mothership.local:8000 python -m piassistant cli

# Or via Tailscale
PIASSISTANT_URL=http://<tailscale-ip>:8000 python -m piassistant cli
```

## Verification Checklist

- [ ] `ssh <user>@piassistant-mothership.local` works
- [ ] `systemctl status piassistant` shows active/running
- [ ] `curl http://piassistant-mothership.local:8000/api/health` returns healthy
- [ ] `curl http://piassistant-mothership.local:8000/api/pico/weather` returns weather
- [ ] Chat endpoint returns Claude response
- [ ] Mosquitto accepts connections on port 1883
- [ ] Service auto-restarts after kill
- [ ] Service starts on boot after reboot
