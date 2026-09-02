"""Live NYC bus integration — standalone, no dependency on the rest of
RYDESAVYR (modes.py, scoring.py, app.py).

Dependencies: requests, geopy (both already in requirements.txt).

Pulls real stop locations from MTA's static per-borough GTFS feeds (free,
no key) and live "next bus" arrival predictions from MTA Bus Time's SIRI
Stop Monitoring API. The SIRI feed needs a free API key — register at
https://register.developer.obanyc.com/ (MTA says issued within ~30 min)
and put it in a local .env file as MTA_BUS_API_KEY. Without that key set,
this module quietly skips itself and callers should fall back to the
formula estimate in modes.py — nothing else breaks, same fail-safe pattern
every live data source in this project follows (citibike.py, mta_subway.py,
routing.py).

Replaces only the *wait time* half of a bus estimate with a real number;
the ride portion (distance/time between stops) still uses the same
straight-line x detour-factor formula modes.py uses for every other mode
— real routing along a specific bus route is out of scope here, same
simplification mta_subway.py makes for the subway.

Can be copied into any other project as-is: call get_bus_option() with
(lat, lon) tuples. Returns None (never raises) if the key isn't set, the
feeds are unreachable, or no live arrival data is found, so callers can
skip it the same way they'd skip any other unavailable travel mode.

Run `python mta_bus.py` directly for a standalone sanity check.
"""

import csv
import io
import os
import time
import zipfile
from datetime import datetime, timezone

import requests
from geopy.distance import geodesic

MTA_BUS_API_KEY = os.environ.get("MTA_BUS_API_KEY")

# Per-borough static GTFS feeds — free, no key. Bus stops (unlike subway
# stations) have no parent/child hierarchy; stop_id is what SIRI's
# MonitoringRef expects directly.
STATIC_GTFS_URLS = {
    "bronx": "http://web.mta.info/developers/data/nyct/bus/google_transit_bronx.zip",
    "brooklyn": "http://web.mta.info/developers/data/nyct/bus/google_transit_brooklyn.zip",
    "manhattan": "http://web.mta.info/developers/data/nyct/bus/google_transit_manhattan.zip",
    "queens": "http://web.mta.info/developers/data/nyct/bus/google_transit_queens.zip",
    "staten_island": "http://web.mta.info/developers/data/nyct/bus/google_transit_staten_island.zip",
}

SIRI_STOP_MONITORING_URL = "https://bustime.mta.info/api/siri/stop-monitoring.json"
REQUEST_TIMEOUT_SECONDS = 10

# Flat MTA fare + route-estimation assumptions, matched to modes.py's
# static Bus entry for consistency.
BUS_FARE = 2.90
ROUTE_FACTOR = 1.3
AVG_SPEED_MPH = 8

STOP_INFO_CACHE_TTL_SECONDS = 86400  # stop locations barely change

_stop_info_cache = {"stops": None, "fetched_at": 0.0}


def is_configured() -> bool:
    return bool(MTA_BUS_API_KEY)


def get_stop_information():
    """Return [{stop_id, name, lat, lon}, ...] across all five boroughs,
    cached for 24 hours.
    """
    now = time.monotonic()
    if (
        _stop_info_cache["stops"] is not None
        and now - _stop_info_cache["fetched_at"] < STOP_INFO_CACHE_TTL_SECONDS
    ):
        return _stop_info_cache["stops"]

    stops = []
    for url in STATIC_GTFS_URLS.values():
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            with archive.open("stops.txt") as stops_file:
                reader = csv.DictReader(io.TextIOWrapper(stops_file, encoding="utf-8"))
                for row in reader:
                    stops.append({
                        "stop_id": row["stop_id"],
                        "name": row["stop_name"],
                        "lat": float(row["stop_lat"]),
                        "lon": float(row["stop_lon"]),
                    })

    _stop_info_cache["stops"] = stops
    _stop_info_cache["fetched_at"] = now
    return stops


def find_nearest_stop(lat, lon, stops):
    """Nearest bus stop to (lat, lon). Returns (stop, distance_miles)."""
    best = min(stops, key=lambda s: geodesic((lat, lon), (s["lat"], s["lon"])).miles)
    distance = geodesic((lat, lon), (best["lat"], best["lon"])).miles
    return best, distance


def get_next_arrival_minutes(stop_id):
    """Soonest upcoming bus at this stop (any route), via SIRI Stop
    Monitoring. Returns minutes from now, or None if nothing found.
    """
    response = requests.get(
        SIRI_STOP_MONITORING_URL,
        params={
            "key": MTA_BUS_API_KEY,
            "MonitoringRef": stop_id,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()

    deliveries = data["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"]
    now = datetime.now(timezone.utc)
    soonest = None

    for delivery in deliveries:
        for visit in delivery.get("MonitoredStopVisit", []):
            call = visit.get("MonitoredVehicleJourney", {}).get("MonitoredCall", {})
            arrival_str = call.get("ExpectedArrivalTime") or call.get("AimedArrivalTime")
            if not arrival_str:
                continue
            arrival_time = datetime.fromisoformat(arrival_str)
            if soonest is None or arrival_time < soonest:
                soonest = arrival_time

    if soonest is None:
        return None
    return (soonest - now).total_seconds() / 60


def estimate_ride_distance_and_time(origin_latlon, destination_latlon):
    """Straight-line distance x detour factor, at an average bus speed.
    Returns (route_miles, minutes).
    """
    straight_line_miles = geodesic(origin_latlon, destination_latlon).miles
    route_miles = straight_line_miles * ROUTE_FACTOR
    minutes = (route_miles / AVG_SPEED_MPH) * 60
    return route_miles, minutes


def build_bus_details(origin, destination):
    """Do the actual work and return every intermediate piece as a plain
    dict: nearest origin/destination stops, live wait minutes, computed
    ride distance/time. No Option/Mode wrapper — useful on its own if a
    caller wants the raw stop data.

    Returns None if the key isn't set, the feeds can't be reached, or no
    live arrival is found at the nearest stop.
    """
    if not is_configured():
        return None

    stops = get_stop_information()

    origin_stop, walk_to_stop_mi = find_nearest_stop(origin[0], origin[1], stops)
    destination_stop, walk_from_stop_mi = find_nearest_stop(destination[0], destination[1], stops)

    wait_minutes = get_next_arrival_minutes(origin_stop["stop_id"])
    if wait_minutes is None:
        return None

    route_miles, ride_minutes = estimate_ride_distance_and_time(
        (origin_stop["lat"], origin_stop["lon"]),
        (destination_stop["lat"], destination_stop["lon"]),
    )

    return {
        "origin_stop": origin_stop,
        "walk_to_stop_miles": round(walk_to_stop_mi, 2),
        "destination_stop": destination_stop,
        "walk_from_stop_miles": round(walk_from_stop_mi, 2),
        "wait_minutes": round(wait_minutes, 1),
        "distance_miles": round(route_miles, 2),
        "ride_minutes": round(ride_minutes, 1),
        "price_usd": BUS_FARE,
    }


def get_bus_option(origin, destination):
    """Public entry point. origin/destination are (lat, lon) tuples.

    Returns a dict shaped like modes.py's Mode.estimate() output (key,
    label, distance, time, price, energy, nature_vibez, carbon, notes) so
    it drops straight into scoring.py's ranking, or None if MTA_BUS_API_KEY
    isn't set, a live wait time isn't available right now, or anything
    about the live call fails — callers should skip it the same way
    they'd skip any other missing source.
    """
    try:
        details = build_bus_details(origin, destination)
    except (requests.RequestException, KeyError, ValueError):
        return None

    if details is None:
        return None

    notes = (
        f"Live MTA data. Next bus from {details['origin_stop']['name']} "
        f"in {details['wait_minutes']} min, toward "
        f"{details['destination_stop']['name']}."
    )

    return {
        "key": "bus",
        "label": "Bus",
        "distance": details["distance_miles"],
        "time": round(details["wait_minutes"] + details["ride_minutes"], 1),
        "price": details["price_usd"],
        "energy": 3,
        "nature_vibez": 3,
        "carbon": round(150 * details["distance_miles"]),
        "notes": notes,
        "route_profile": "transit",
    }


if __name__ == "__main__":
    if not is_configured():
        print("MTA_BUS_API_KEY not set — add it to .env first (see module docstring).")
    else:
        demo_trips = [
            ("Columbia University", (40.8075, -73.9626), (40.7359, -73.9911)),  # -> Union Square
            ("Times Square", (40.7580, -73.9855), (40.7061, -73.9969)),          # -> Brooklyn Bridge area
        ]

        for label, origin, destination in demo_trips:
            print(f"\n{label}: {origin} -> {destination}")
            result = get_bus_option(origin, destination)
            if result is None:
                print("  No live bus option available right now.")
            else:
                for key, value in result.items():
                    print(f"  {key}: {value}")
