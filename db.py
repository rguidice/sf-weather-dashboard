import os
import sqlite3

DB_PATH = os.path.expanduser("~/sf-weather.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    neighborhood TEXT NOT NULL,
    temp_f REAL,
    humidity REAL,
    sensor_count INTEGER,
    outlier_corrected INTEGER DEFAULT 0,
    scraped_at TEXT NOT NULL,
    UNIQUE(neighborhood, scraped_at)
);

CREATE TABLE IF NOT EXISTS scrape_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scraped_at TEXT NOT NULL,
    valid_count INTEGER NOT NULL,
    skipped_neighborhoods TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    created_at_pacific TEXT
);

CREATE INDEX IF NOT EXISTS idx_readings_neighborhood ON readings(neighborhood);
CREATE INDEX IF NOT EXISTS idx_readings_scraped_at ON readings(scraped_at);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
