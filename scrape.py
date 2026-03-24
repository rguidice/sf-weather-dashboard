#!/usr/bin/env python3
"""Scrape PurpleAir sensor data for SF neighborhoods and store in SQLite."""

import json
import os
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from db import get_db, init_db

PURPLEAIR_URL = "https://api.purpleair.com/v1/sensors"
TIMEOUT = 30
TEMP_CORRECTION = -8  # PurpleAir housing offset in °F

# SF bounding box
NWLAT = 37.812
NWLNG = -122.52
SELAT = 37.708
SELNG = -122.355

# 51 SF neighborhood center coordinates (from map.html)
NEIGHBORHOODS = {
    "financial_district": (37.7946, -122.3999),
    "chinatown": (37.7941, -122.4078),
    "union_square": (37.7880, -122.4075),
    "tenderloin": (37.7847, -122.4141),
    "civic_center": (37.7793, -122.4193),
    "embarcadero": (37.7936, -122.3880),
    "rincon_hill": (37.7862, -122.3906),
    "south_beach": (37.7864, -122.3886),
    "north_beach": (37.8005, -122.4082),
    "telegraph_hill": (37.8024, -122.4058),
    "russian_hill": (37.8011, -122.4197),
    "nob_hill": (37.7930, -122.4161),
    "marina": (37.8017, -122.4367),
    "pacific_heights": (37.7925, -122.4382),
    "japantown": (37.7854, -122.4294),
    "presidio": (37.7989, -122.4662),
    "sea_cliff": (37.7876, -122.4910),
    "lands_end": (37.7878, -122.5048),
    "inner_richmond": (37.7793, -122.4637),
    "outer_richmond": (37.7766, -122.4943),
    "inner_sunset": (37.7601, -122.4658),
    "outer_sunset": (37.7558, -122.4960),
    "parkside": (37.7440, -122.4870),
    "haight": (37.7692, -122.4481),
    "lower_haight": (37.7720, -122.4305),
    "hayes_valley": (37.7764, -122.4260),
    "cole_valley": (37.7658, -122.4500),
    "castro": (37.7609, -122.4350),
    "noe_valley": (37.7502, -122.4337),
    "mission": (37.7599, -122.4148),
    "soma": (37.7785, -122.3950),
    "mission_bay": (37.7706, -122.3930),
    "twin_peaks": (37.7544, -122.4477),
    "diamond_heights": (37.7434, -122.4438),
    "glen_park": (37.7350, -122.4332),
    "forest_hill": (37.7478, -122.4596),
    "west_portal": (37.7406, -122.4658),
    "st_francis_wood": (37.7345, -122.4622),
    "bernal_heights": (37.7390, -122.4153),
    "potrero_hill": (37.7562, -122.3927),
    "dogpatch": (37.7614, -122.3878),
    "bayview": (37.7295, -122.3905),
    "hunters_point": (37.7247, -122.3786),
    "excelsior": (37.7253, -122.4250),
    "visitacion_valley": (37.7147, -122.4052),
    "ingleside": (37.7235, -122.4476),
    "oceanview": (37.7179, -122.4569),
    "merced_heights": (37.7170, -122.4470),
    "lakeside": (37.7271, -122.4780),
    "stonestown": (37.7285, -122.4750),
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SENSOR_CACHE_PATH = os.path.join(BASE_DIR, "sensor_cache.json")
SENSOR_CACHE_MAX_AGE_DAYS = 30


def load_api_key():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    key = config.get("purpleair_api_key", "").strip()
    if not key:
        raise ValueError("purpleair_api_key not set in config.json")
    return key


def load_sensor_cache():
    """Load cached sensor_index -> neighborhood mapping, or None if stale/missing."""
    if not os.path.exists(SENSOR_CACHE_PATH):
        return None
    with open(SENSOR_CACHE_PATH) as f:
        cache = json.load(f)
    cached_at = datetime.fromisoformat(cache["cached_at"])
    age = datetime.now(ZoneInfo("America/Los_Angeles")) - cached_at
    if age.days > SENSOR_CACHE_MAX_AGE_DAYS:
        return None
    return cache["sensors"]  # dict of sensor_index -> neighborhood


def save_sensor_cache(sensor_map):
    """Save sensor_index -> neighborhood mapping to disk."""
    cache = {
        "cached_at": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
        "sensor_count": len(sensor_map),
        "sensors": sensor_map,
    }
    with open(SENSOR_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def fetch_sensor_locations(api_key):
    """Fetch sensor locations (one-time/monthly) and build sensor_index -> neighborhood map."""
    params = (
        f"?fields=latitude,longitude"
        f"&location_type=0"
        f"&nwlat={NWLAT}&nwlng={NWLNG}&selat={SELAT}&selng={SELNG}"
    )
    url = PURPLEAIR_URL + params
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode())

    fields = data["fields"]
    fi = {name: i for i, name in enumerate(fields)}
    sensor_map = {}
    for row in data["data"]:
        idx = row[fi["sensor_index"]]
        lat = row[fi["latitude"]]
        lng = row[fi["longitude"]]
        if lat is not None and lng is not None:
            sensor_map[str(idx)] = assign_neighborhood(lat, lng)
    return sensor_map


def dist_sq(lat1, lng1, lat2, lng2):
    """Squared Euclidean distance (sufficient for nearest-neighbor at SF scale)."""
    return (lat1 - lat2) ** 2 + (lng1 - lng2) ** 2


def assign_neighborhood(lat, lng):
    """Return the nearest neighborhood key for a given lat/lng."""
    best = None
    best_d = float("inf")
    for name, (nlat, nlng) in NEIGHBORHOODS.items():
        d = dist_sq(lat, lng, nlat, nlng)
        if d < best_d:
            best_d = d
            best = name
    return best


def fetch_sensors(api_key, sensor_map):
    """Fetch weather data for outdoor sensors in SF bounding box from PurpleAir."""
    params = (
        f"?fields=temperature,humidity"
        f"&location_type=0"
        f"&nwlat={NWLAT}&nwlng={NWLNG}&selat={SELAT}&selng={SELNG}"
    )
    url = PURPLEAIR_URL + params
    req = urllib.request.Request(url, headers={"X-API-Key": api_key})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode())

    fields = data["fields"]
    fi = {name: i for i, name in enumerate(fields)}
    sensors = []
    for row in data["data"]:
        idx = str(row[fi["sensor_index"]])
        temp = row[fi["temperature"]]
        hum = row[fi["humidity"]]
        hood = sensor_map.get(idx)
        if temp is not None and hum is not None and hood is not None:
            sensors.append({"temp": temp, "humidity": hum, "neighborhood": hood})
    return sensors


def precompute_neighbors(k=3):
    """For each neighborhood, find the k nearest other neighborhoods."""
    names = list(NEIGHBORHOODS.keys())
    neighbors = {}
    for name in names:
        lat, lng = NEIGHBORHOODS[name]
        dists = []
        for other in names:
            if other == name:
                continue
            olat, olng = NEIGHBORHOODS[other]
            dists.append((dist_sq(lat, lng, olat, olng), other))
        dists.sort()
        neighbors[name] = [n for _, n in dists[:k]]
    return neighbors


def aggregate_and_correct(sensors):
    """Group sensors by neighborhood, average, apply corrections, detect outliers."""
    # Group sensors by neighborhood
    groups = {}
    for s in sensors:
        groups.setdefault(s["neighborhood"], []).append(s)

    # Compute raw averages with temp correction
    results = {}
    for hood, readings in groups.items():
        avg_temp = sum(r["temp"] for r in readings) / len(readings) + TEMP_CORRECTION
        avg_hum = sum(r["humidity"] for r in readings) / len(readings)
        results[hood] = {
            "temp_f": round(avg_temp),
            "humidity": round(avg_hum),
            "sensor_count": len(readings),
            "outlier_corrected": False,
        }

    # Outlier detection: compare against 3 nearest neighbor neighborhoods
    neighbor_map = precompute_neighbors(k=3)
    for hood, info in results.items():
        if info["sensor_count"] > 2:
            continue
        neighbor_vals = []
        for nb in neighbor_map.get(hood, []):
            if nb in results:
                neighbor_vals.append(results[nb])
        if len(neighbor_vals) < 2:
            continue
        temp_avg = sum(n["temp_f"] for n in neighbor_vals) / len(neighbor_vals)
        if abs(info["temp_f"] - temp_avg) > 10:
            info["temp_f"] = round(temp_avg)
            info["outlier_corrected"] = True
        hum_avg = sum(n["humidity"] for n in neighbor_vals) / len(neighbor_vals)
        if abs(info["humidity"] - hum_avg) > 20:
            info["humidity"] = round(hum_avg)
            info["outlier_corrected"] = True

    return results


def scrape():
    api_key = load_api_key()

    # Load or refresh sensor location cache (costs 2 extra fields only once/month)
    sensor_map = load_sensor_cache()
    if sensor_map is None:
        print("Refreshing sensor location cache...")
        sensor_map = fetch_sensor_locations(api_key)
        save_sensor_cache(sensor_map)
        print(f"Cached {len(sensor_map)} sensor locations")

    sensors = fetch_sensors(api_key, sensor_map)
    if not sensors:
        raise RuntimeError("No sensors returned from PurpleAir API")

    results = aggregate_and_correct(sensors)

    scraped_at = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%dT%H:%M:%S%z")

    valid = []
    for hood, info in results.items():
        valid.append((
            hood,
            info["temp_f"],
            info["humidity"],
            info["sensor_count"],
            1 if info["outlier_corrected"] else 0,
            scraped_at,
        ))

    skipped = [h for h in NEIGHBORHOODS if h not in results]

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
    print(f"[{now}] Scraped {len(sensors)} sensors -> {len(valid)} neighborhoods, "
          f"skipped {len(skipped)} ({', '.join(skipped) if skipped else 'none'})")
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
