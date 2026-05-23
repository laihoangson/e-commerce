"""One-time download of Australian postcode data.

Fetches the Matthew Proctor community postcode database and writes a trimmed
CSV (postcode, lat, lng, city, state) to data/raw/au_postcodes.csv.

Usage:
    python scripts/download_au_postcodes.py
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import requests

# Matthew Proctor publishes the dataset publicly; this is the raw CSV endpoint.
SOURCE_URL = "https://raw.githubusercontent.com/matthewproctor/australianpostcodes/master/australian_postcodes.csv"
OUT_PATH = Path("data/raw/au_postcodes.csv")
SAMPLE_SIZE = 2500


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading postcodes from {SOURCE_URL} ...")
    try:
        resp = requests.get(SOURCE_URL, timeout=60)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] download error: {exc}")
        print("Falling back: master_generator will synthesize postcodes instead.")
        return 1

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = []
    for r in reader:
        pc = (r.get("postcode") or "").strip()
        lat = (r.get("lat") or r.get("latitude") or "").strip()
        lng = (r.get("long") or r.get("lng") or r.get("longitude") or "").strip()
        city = (r.get("locality") or r.get("city") or "").strip()
        state = (r.get("state") or "").strip()
        if pc and lat and lng:
            rows.append(
                {
                    "postcode": pc.zfill(4),
                    "lat": lat,
                    "lng": lng,
                    "city": city.title(),
                    "state": state,
                }
            )

    # Trim to a manageable sample, keeping variety across states.
    if len(rows) > SAMPLE_SIZE:
        step = len(rows) // SAMPLE_SIZE
        rows = rows[::step][:SAMPLE_SIZE]

    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["postcode", "lat", "lng", "city", "state"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] wrote {len(rows)} postcodes to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
