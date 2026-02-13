#!/usr/bin/env bash
# One-time setup on Raspberry Pi. Run via: ssh pi@<ip> 'bash -s' < setup.sh
set -euo pipefail

PROJECT_DIR="$HOME/sf-weather-dashboard"
echo "==> Installing uv (if not present)"
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

echo "==> Setting up venv and installing dependencies"
cd "$PROJECT_DIR"
uv sync

echo "==> Initializing database"
uv run python db.py

echo "==> Installing cron job (every 4 hours)"
CRON_CMD="0 */4 * * * cd $PROJECT_DIR && uv run python scrape.py >> scrape.log 2>&1"
(crontab -l 2>/dev/null | grep -v 'scrape.py' ; echo "$CRON_CMD") | crontab -
echo "Cron installed:"
crontab -l | grep scrape

echo "==> Installing systemd service"
sudo tee /etc/systemd/system/sf-weather-dashboard.service > /dev/null <<EOF
[Unit]
Description=SF Weather Dashboard
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$(command -v uv) run python dashboard.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable sf-weather-dashboard
sudo systemctl start sf-weather-dashboard

echo "==> Done! Dashboard running on port 8080"
echo "    View at http://$(hostname -I | awk '{print $1}'):8080"
