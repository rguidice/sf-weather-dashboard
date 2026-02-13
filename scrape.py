#!/usr/bin/env python3
"""Scrape SF microclimate weather data and store in SQLite."""

import json
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from db import get_db, init_db

API_URL = "https://microclimates.solofounders.com/sf-weather"
TIMEOUT = 30
USER_AGENT = "sf-weather-dashboard/1.0 (Raspberry Pi; cron job)"


def fetch():
    req = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def scrape():
    data = fetch()
    scraped_at = data["updated"]
    neighborhoods = data["neighborhoods"]

    valid = []
    skipped = []

    for key, info in neighborhoods.items():
        if info.get("sensor_count", 0) == 0 or info.get("temp_f") is None:
            skipped.append(key)
            continue
        valid.append((
            key,
            info["temp_f"],
            info["humidity"],
            info["sensor_count"],
            1 if "outlier_corrected" in info else 0,
            scraped_at,
        ))

    conn = get_db()
    conn.executemany(
        "INSERT OR IGNORE INTO readings "
        "(neighborhood, temp_f, humidity, sensor_count, outlier_corrected, scraped_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        valid,
    )
    now_pacific = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d %I:%M:%S %p")
    conn.execute(
        "INSERT INTO scrape_log (scraped_at, valid_count, skipped_neighborhoods, created_at_pacific) "
        "VALUES (?, ?, ?, ?)",
        (scraped_at, len(valid), ",".join(skipped), now_pacific),
    )
    conn.commit()
    conn.close()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] Scraped {len(valid)} neighborhoods, skipped {len(skipped)} "
          f"({', '.join(skipped)})")
    return len(valid)


if __name__ == "__main__":
    init_db()
    try:
        count = scrape()
        if count == 0:
            print("WARNING: No valid readings found", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
