#!/usr/bin/env bash
# One-time setup on Raspberry Pi. SSH in first, then run: ./setup.sh
# Options: --skip-mdns (no weather.local alias), --skip-redirect (no port 80 redirect)
set -euo pipefail

die() { echo "FATAL: $*" >&2; exit 1; }

SKIP_MDNS=false
SKIP_REDIRECT=false
for arg in "$@"; do
  case "$arg" in
    --skip-mdns) SKIP_MDNS=true ;;
    --skip-redirect) SKIP_REDIRECT=true ;;
    *) die "Unknown option: $arg" ;;
  esac
done

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

# --- Config file ---
echo "==> Setting up config.json"
if [ ! -f "$PROJECT_DIR/config.json" ]; then
  cp "$PROJECT_DIR/config.example.json" "$PROJECT_DIR/config.json"
  echo "    Copied config.example.json -> config.json"
else
  echo "    config.json already exists, skipping"
fi

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

# --- mDNS alias (weather.local) ---
if [ "$SKIP_MDNS" = false ]; then
  echo "==> Setting up mDNS alias (weather.local)"
  sudo apt-get install -y python3-dbus || die "Failed to install python3-dbus"

  cat <<EOF | sudo tee /etc/systemd/system/weather-mdns.service > /dev/null || die "Failed to write mDNS service"
[Unit]
Description=Publish weather.local mDNS alias
After=avahi-daemon.service
Requires=avahi-daemon.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 $PROJECT_DIR/mdns_alias.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload || die "Failed to reload systemd"
  sudo systemctl enable weather-mdns || die "Failed to enable mDNS service"
  sudo systemctl restart weather-mdns || die "Failed to start mDNS service"
  echo "    weather.local is now available on your network"
else
  echo "==> Skipping mDNS alias setup (--skip-mdns)"
fi

# --- Port 80 redirect ---
if [ "$SKIP_REDIRECT" = false ]; then
  echo "==> Setting up port 80 -> 8080 redirect"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables iptables-persistent || die "Failed to install iptables"
  sudo iptables -t nat -C PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8080 2>/dev/null \
    || sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8080 \
    || die "Failed to add iptables redirect"
  sudo netfilter-persistent save || die "Failed to save iptables rules"
else
  echo "==> Skipping port 80 redirect (--skip-redirect)"
fi

# --- Initial scrape ---
echo "==> Running initial scrape"
uv run python scrape.py || die "Initial scrape failed"

IP_ADDR=$(hostname -I | awk '{print $1}')
PORT=$( [ "$SKIP_REDIRECT" = false ] && echo "80" || echo "8080" )
echo ""
echo "==> Done! Dashboard running on port $PORT"
echo "    http://$IP_ADDR$( [ "$PORT" != "80" ] && echo ":$PORT" )"
if [ "$SKIP_MDNS" = false ]; then
  echo "    http://weather.local$( [ "$PORT" != "80" ] && echo ":$PORT" )"
fi
