# SF Microclimate Weather Dashboard

**Written using Claude Code running Opus 4.6**

Scrapes San Francisco neighborhood-level weather data from the [SF Microclimates API](https://microclimates.solofounders.com/sf-weather) and serves a local dashboard. Designed to run on a Raspberry Pi on your home network.

## What it does

- **Scrapes** temp and humidity for ~50 SF neighborhoods every 4 hours via cron
- **Stores** readings in a local SQLite database (`~/sf-weather.db`)
- **Serves** a dark-themed dashboard on port 8080 with:
  - City-wide averages and temperature spread
  - Sortable table of all neighborhoods (click a row to see its history chart)
  - Historical temp/humidity charts (7d / 14d / 30d)
  - Interactive **map** with color-coded labels for each neighborhood

## Project structure

```
sf-weather-dashboard/
  dashboard.py    # Flask app — serves the dashboard and JSON API
  scrape.py       # Fetches data from the microclimates API and writes to SQLite
  db.py           # Database schema and connection helpers
  setup.sh        # One-time Raspberry Pi setup (uv, cron, systemd)
  pyproject.toml  # Python project config (only dependency: Flask)
  static/
    index.html    # Main dashboard page
    map.html      # Interactive neighborhood map (Leaflet.js)
```

## API endpoints

| Endpoint | Description |
|---|---|
| `GET /api/latest` | Latest reading for every active neighborhood |
| `GET /api/history?neighborhood=noe_valley&days=7` | Historical readings for one neighborhood |
| `GET /api/status` | Last scrape time, total scrape count |
| `GET /api/city-summary?days=7` | Daily city-wide averages |

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (installed automatically by `setup.sh`)
- No external API keys needed

## Local development

```bash
uv sync
uv run python db.py         # initialize the database
uv run python scrape.py     # run one scrape
uv run python dashboard.py  # start dashboard at http://localhost:8080
```

## Deploy to Raspberry Pi

### Prerequisites

- A Raspberry Pi on your local network with SSH access
- An SSH config entry (e.g. `Host pi`) or know the Pi's IP address

### First-time setup

1. Clone the repo on the Pi:

```bash
ssh pi 'git clone <repo-url> ~/sf-weather-dashboard'
```

2. Run the setup script:

```bash
ssh pi 'bash ~/sf-weather-dashboard/setup.sh'
```

This will:
- Install `uv` if not already present
- Create a virtualenv and install Flask
- Initialize the SQLite database
- Set up a **cron job** to scrape every 4 hours
- Create and start a **systemd service** (`sf-weather-dashboard`) on port 8080

3. Verify it's running:

```bash
ssh pi 'systemctl status sf-weather-dashboard'
```

Then open `http://<pi-ip>:8080` in your browser.

### Updating

Pull the latest changes and restart:

```bash
ssh pi 'cd ~/sf-weather-dashboard && git pull && sudo systemctl restart sf-weather-dashboard'
```

### Useful commands

```bash
# Check dashboard logs
ssh pi 'journalctl -u sf-weather-dashboard -f'

# Manually trigger a scrape
ssh pi 'cd ~/sf-weather-dashboard && uv run python scrape.py'

# Check cron is set up
ssh pi 'crontab -l | grep scrape'

# Restart the dashboard
ssh pi 'sudo systemctl restart sf-weather-dashboard'
```
