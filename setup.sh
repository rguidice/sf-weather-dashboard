#!/usr/bin/env bash
# One-time setup on Raspberry Pi. SSH in first, then run: ./setup.sh
set -euo pipefail

die() { echo "FATAL: $*" >&2; exit 1; }

PROJECT_DIR="$HOME/sf-weather-dashboard"
[ -d "$PROJECT_DIR" ] || die "Project directory not found: $PROJECT_DIR"

# --- Sudo check ---
echo "==> Checking sudo access (you may be prompted for your password)"
sudo -v || die "sudo access required. Run this script as a user with sudo privileges."

# --- Install uv ---
echo "==> Installing uv (if not present)"
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh || die "uv installer failed"
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv &>/dev/null || die "uv not found in PATH after install. Check ~/.local/bin/"

# --- Install Python dependencies ---
echo "==> Setting up venv and installing dependencies"
cd "$PROJECT_DIR"
uv sync || die "uv sync failed"

# --- Initialize database ---
echo "==> Initializing database"
uv run python db.py || die "Database initialization failed"

# --- Cron job ---
echo "==> Installing cron job (every 4 hours)"
UV_PATH="$(command -v uv)"
CRON_CMD="0 */4 * * * cd $PROJECT_DIR && $UV_PATH run python scrape.py >> scrape.log 2>&1"
EXISTING=$(crontab -l 2>/dev/null || true)
FILTERED=$(echo "$EXISTING" | grep -v 'scrape.py' || true)
echo "${FILTERED:+$FILTERED
}$CRON_CMD" | crontab - || die "Failed to install cron job"

# --- Systemd service ---
echo "==> Installing systemd service"
SERVICE_FILE="/etc/systemd/system/sf-weather-dashboard.service"
cat <<EOF | sudo tee "$SERVICE_FILE" > /dev/null || die "Failed to write service file"
[Unit]
Description=SF Weather Dashboard
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$UV_PATH run python dashboard.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
[ -f "$SERVICE_FILE" ] || die "Service file was not created at $SERVICE_FILE"

sudo systemctl daemon-reload || die "Failed to reload systemd"
sudo systemctl enable sf-weather-dashboard || die "Failed to enable service"
sudo systemctl start sf-weather-dashboard || die "Failed to start service"

# --- Initial scrape ---
echo "==> Running initial scrape"
uv run python scrape.py || die "Initial scrape failed"

echo "==> Done! Dashboard running on port 8080"
echo "    View at http://$(hostname -I | awk '{print $1}'):8080"
