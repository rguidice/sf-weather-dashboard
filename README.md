# SF Microclimate Weather Dashboard

**Written using Claude Code running Opus 4.6**

Scrapes San Francisco neighborhood-level weather data from the [SF Microclimates API](https://microclimates.solofounders.com/sf-weather) and serves a local dashboard. Designed to run on a Raspberry Pi on your home network.

## What it does

- **Scrapes** temp and humidity for ~50 SF neighborhoods every 4 hours via cron
- **Stores** readings in a local SQLite database (`sf-weather.db` in the project directory)
- **Serves** a dark-themed dashboard accessible at `http://weather.local` with:
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
  mdns_alias.py   # Publishes weather.local mDNS CNAME via Avahi D-Bus API
```

## How the data works

The scraper runs every 4 hours via cron and inserts one row per neighborhood into the `readings` table. This is the actual weather data that powers the dashboard and charts. Over time, readings accumulate — after a day you'll have ~6 data points per neighborhood, after a week ~42, etc.

There's also a `scrape_log` table that records metadata about each scrape run (how many neighborhoods reported, which were skipped). This is for operational debugging, not displayed on the dashboard.

## API endpoints

| Endpoint | Description |
|---|---|
| `GET /api/latest` | Latest reading for every active neighborhood |
| `GET /api/history?neighborhood=noe_valley&days=7` | Historical readings for one neighborhood |
| `GET /api/status` | Last scrape metadata and total scrape count |
| `GET /api/config` | Server-side config (favorite neighborhood) |
| `GET /api/city-summary?days=7` | Daily city-wide averages |

## Favorite neighborhood

You can configure a "home" neighborhood that gets highlighted on the dashboard for every device on your network. Edit `config.json` in the project directory:

```json
{
  "favorite_neighborhood": "mission"
}
```

The value must be a valid neighborhood key (snake_case, matching the API — e.g. `mission`, `noe_valley`, `pacific_heights`). When set:

- A **"My Neighborhood" card** appears at the top of the dashboard showing current temp, humidity, and sensor count
- The neighborhood row is **highlighted** in the table with a blue accent border
- The **history chart** defaults to the favorite neighborhood

`setup.sh` creates `config.json` from `config.example.json` automatically (default: `mission`). The file is gitignored since it's a per-installation preference. Edits take effect on the next page refresh (no server restart needed).

To disable, set `favorite_neighborhood` to `""`, delete `config.json`, or remove the key entirely.

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

SSH into the Pi, then run:

```bash
git clone <repo-url> ~/sf-weather-dashboard
cd ~/sf-weather-dashboard
./setup.sh
```

The setup script requires sudo for the systemd steps and will prompt for your password. Do **not** run it as `sudo ./setup.sh` — that changes `$HOME` and breaks all the paths.

The script will:
- Install `uv` if not already present
- Create a virtualenv and install Flask
- Initialize the SQLite database
- Set up a **cron job** to scrape every 4 hours
- Create and start a **systemd service** (Flask on port 8080)
- **Redirect port 80 → 8080** via iptables so no port suffix is needed in URLs (see options below)
- Set up an **mDNS alias** so `http://weather.local` works from any device on your network (see options below)
- Run an initial scrape so the dashboard has data immediately

#### Setup options

By default the setup script modifies your Pi's networking config to make the dashboard easy to access. **If you're already using port 80 or have custom iptables rules, use the flags below to skip those steps.**

| Flag | What it skips | When to use it |
|---|---|---|
| `--skip-redirect` | Skips the iptables rule that redirects port 80 → 8080, and skips installing `iptables-persistent`. **Your existing iptables rules will not be touched.** Dashboard will only be available on port 8080. | You already have something on port 80, or you manage iptables yourself |
| `--skip-mdns` | Skips installing `python3-dbus` and the weather-mdns systemd service. `weather.local` will not resolve. | You don't want mDNS, or you manage DNS another way |

Example with both skipped:

```bash
./setup.sh --skip-redirect --skip-mdns
```

### Verify it's running

```bash
systemctl status sf-weather-dashboard
```

Then open `http://weather.local` (or `http://<pi-ip>` if you used `--skip-mdns`) from any browser on your network. If you used `--skip-redirect`, add `:8080` to the URL.

### Updating

SSH into the Pi, then:

```bash
cd ~/sf-weather-dashboard
git pull
sudo systemctl restart sf-weather-dashboard
```

### Useful commands

Run these on the Pi:

```bash
# Check dashboard logs
journalctl -u sf-weather-dashboard -f

# Manually trigger a scrape
cd ~/sf-weather-dashboard && uv run python scrape.py

# Check cron is set up
crontab -l | grep scrape

# Restart the dashboard
sudo systemctl restart sf-weather-dashboard

# Check scrape_log (did scrapes run? any skipped neighborhoods?)
cd ~/sf-weather-dashboard && uv run python -c "from db import get_db; [print(dict(r)) for r in get_db().execute('SELECT * FROM scrape_log ORDER BY id DESC LIMIT 10')]"

# View raw cron output
cat ~/sf-weather-dashboard/scrape.log
```
