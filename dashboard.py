#!/usr/bin/env python3
"""Flask dashboard for SF microclimate weather data."""

import json
import os

from flask import Flask, jsonify, request, send_from_directory

from db import get_db, init_db

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

app = Flask(__name__, static_folder="static")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/map")
def map_page():
    return send_from_directory("static", "map.html")


@app.route("/api/latest")
def api_latest():
    conn = get_db()
    rows = conn.execute("""
        SELECT r.neighborhood, r.temp_f, r.humidity, r.sensor_count,
               r.outlier_corrected, r.scraped_at
        FROM readings r
        INNER JOIN (
            SELECT neighborhood, MAX(scraped_at) AS max_at
            FROM readings
            GROUP BY neighborhood
        ) latest ON r.neighborhood = latest.neighborhood
                 AND r.scraped_at = latest.max_at
        ORDER BY r.temp_f DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/history")
def api_history():
    neighborhood = request.args.get("neighborhood", "noe_valley")
    days = int(request.args.get("days", 7))
    conn = get_db()
    rows = conn.execute("""
        SELECT neighborhood, temp_f, humidity, sensor_count,
               outlier_corrected, scraped_at
        FROM readings
        WHERE neighborhood = ?
          AND scraped_at >= datetime('now', ?)
        ORDER BY scraped_at ASC
    """, (neighborhood, f"-{days} days")).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/status")
def api_status():
    conn = get_db()
    last = conn.execute(
        "SELECT * FROM scrape_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    total = conn.execute("SELECT COUNT(*) AS cnt FROM scrape_log").fetchone()
    conn.close()
    return jsonify({
        "last_scrape": dict(last) if last else None,
        "total_scrapes": total["cnt"] if total else 0,
    })


@app.route("/api/config")
def api_config():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        return jsonify({"favorite_neighborhood": cfg.get("favorite_neighborhood", "")})
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return jsonify({})


@app.route("/api/city-summary")
def api_city_summary():
    days = int(request.args.get("days", 7))
    conn = get_db()
    rows = conn.execute("""
        SELECT date(scraped_at) AS day,
               ROUND(AVG(temp_f), 1) AS avg_temp,
               ROUND(AVG(humidity), 1) AS avg_humidity,
               COUNT(DISTINCT neighborhood) AS neighborhood_count
        FROM readings
        WHERE scraped_at >= datetime('now', ?)
        GROUP BY date(scraped_at)
        ORDER BY day ASC
    """, (f"-{days} days",)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8080, debug=True)
