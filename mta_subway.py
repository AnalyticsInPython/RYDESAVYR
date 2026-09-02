"""Live NYC subway integration — standalone, no dependency on the rest of
RYDESAVYR (modes.py, scoring.py, app.py).

Dependencies: requests, gtfs-realtime-bindings, geopy (requests/geopy are
already in requirements.txt; gtfs-realtime-bindings decodes MTA's Protocol
Buffer feeds).

Pulls real station locations from MTA's static GTFS feed and live "next
train" arrival predictions from MTA's GTFS-Realtime feeds — both are
completely free with no API key, no registration, no account. Replaces
only the *wait time* half of a subway estimate with a real number; the
ride portion (distance/time between stations) still uses the same
straight-line x detour-factor formula modes.py uses for every other mode,
since real routing between two arbitrary stations would need a full
transit-routing graph, out of scope here.

Known simplification: GTFS-RT's stop_ids are direction-suffixed (e.g.
"101N"/"101S" for uptown/downtown), and picking the right one for "toward
the destination" is genuinely a routing problem. This uses a cheap
latitude-based heuristic instead (destination north of origin -> "N",
else "S") — reasonable for Manhattan's largely north-south lines, weaker
for lines that run mostly east-west. This is the same kind of acknowledged
approximation as modes.py's route_factor, not a hard blocker.

Can be copied into any other project as-is: call get_subway_option() with
(lat, lon) tuples. Returns None (never raises) if the feeds are
unreachable or no live arrival data is found, so callers can skip it the
same way they'd skip any other unavailable travel mode.

Run `python mta_subway.py` directly for a standalone sanity check.
"""

import csv
import io
import time
import zipfile

import requests
from geopy.distance import geodesic
from google.transit import gtfs_realtime_pb2

STATIC_GTFS_URL = "http://web.mta.info/developers/data/nyct/subway/google_transit.zip"
REQUEST_TIMEOUT_SECONDS = 10

# The 8 keyless GTFS-Realtime feeds, one per line grouping. No API key.
REALTIME_FEED_URLS = {
    "123456S": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs",
    "ACE": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
    "BDFM": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
    "G": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
    "JZ": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
    "L": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
    "NQRW": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
    "SIR": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-si",
}

# Flat MTA fare, matched to modes.py's static Subway entry.
SUBWAY_FARE = 2.90

# Route-estimation assumptions for the ride portion, matched to modes.py's
# static Subway entry for consistency.
ROUTE_FACTOR = 1.4
AVG_SPEED_MPH = 17

STATION_INFO_CACHE_TTL_SECONDS = 86400  # station locations barely change

_station_info_cache = {"stations": None, "children_by_parent": None, "fetched_at": 0.0}


def get_station_information():
    """Return (stations, children_by_parent), cached for 24 hours.

    stations: [{stop_id, name, lat, lon}, ...] — one row per station
    complex (GTFS location_type=1).
    children_by_parent: {parent_stop_id: {"N": child_stop_id, "S": child_stop_id}}
    — the direction-suffixed stop_ids GTFS-Realtime actually reports
    arrivals against.
    """
    now = time.monotonic()
    if (
        _station_info_cache["stations"] is not None
        and now - _station_info_cache["fetched_at"] < STATION_INFO_CACHE_TTL_SECONDS
    ):
        return _station_info_cache["stations"], _station_info_cache["children_by_parent"]

    response = requests.get(STATIC_GTFS_URL, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    stations = []
    children_by_parent = {}

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        with archive.open("stops.txt") as stops_file:
            reader = csv.DictReader(io.TextIOWrapper(stops_file, encoding="utf-8"))
            for row in reader:
                if row["location_type"] == "1":
                    stations.append({
                        "stop_id": row["stop_id"],
                        "name": row["stop_name"],
                        "lat": float(row["stop_lat"]),
                        "lon": float(row["stop_lon"]),
                    })
                elif row["parent_station"] and row["stop_id"][-1] in ("N", "S"):
                    children_by_parent.setdefault(row["parent_station"], {})[row["stop_id"][-1]] = row["stop_id"]

    _station_info_cache["stations"] = stations
    _station_info_cache["children_by_parent"] = children_by_parent
    _station_info_cache["fetched_at"] = now
    return stations, children_by_parent


def find_nearest_station(lat, lon, stations):
    """Nearest station complex to (lat, lon). Returns (station, distance_miles)."""
    best = min(stations, key=lambda s: geodesic((lat, lon), (s["lat"], s["lon"])).miles)
    distance = geodesic((lat, lon), (best["lat"], best["lon"])).miles
    return best, distance


def _fetch_feed(url):
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    return feed


def get_next_arrival_minutes(stop_id):
    """Soonest upcoming arrival at this direction-suffixed stop_id, across
    all 8 line-group feeds (we don't index route-to-station mapping, so we
    just check everywhere). Returns minutes from now, or None if nothing
    found.
    """
    now = time.time()
    soonest = None

    for url in REALTIME_FEED_URLS.values():
        try:
            feed = _fetch_feed(url)
        except (requests.RequestException, Exception):
            continue

        for entity in feed.entity:
            if not entity.HasField("trip_update"):
                continue
            for stop_time_update in entity.trip_update.stop_time_update:
                if stop_time_update.stop_id != stop_id:
                    continue
                if not stop_time_update.HasField("arrival"):
                    continue
                arrival_time = stop_time_update.arrival.time
                if arrival_time < now:
                    continue
                if soonest is None or arrival_time < soonest:
                    soonest = arrival_time

    if soonest is None:
        return None
    return (soonest - now) / 60


def estimate_ride_distance_and_time(origin_latlon, destination_latlon):
    """Straight-line distance x detour factor, at an average subway speed.
    Returns (route_miles, minutes).
    """
    straight_line_miles = geodesic(origin_latlon, destination_latlon).miles
    route_miles = straight_line_miles * ROUTE_FACTOR
    minutes = (route_miles / AVG_SPEED_MPH) * 60
    return route_miles, minutes


def build_subway_details(origin, destination):
    """Do the actual work and return every intermediate piece as a plain
    dict: nearest origin/destination stations, chosen direction, live wait
    minutes, computed ride distance/time. No Option/Mode wrapper — useful
    on its own if a caller wants the raw station data.

    Returns None if the static feed can't be reached or no live arrival
    is found at the nearest station.
    """
    stations, children_by_parent = get_station_information()

    origin_station, walk_to_station_mi = find_nearest_station(origin[0], origin[1], stations)
    destination_station, walk_from_station_mi = find_nearest_station(
        destination[0], destination[1], stations
    )

    # Heuristic only — see module docstring. "N" is conventionally
    # uptown/uptown-bound, "S" downtown-bound. If the guessed direction
    # has no upcoming trip in the live feed right now (a real gap, e.g. a
    # shuttle between runs) we fall back to whichever direction actually
    # has data rather than giving up.
    preferred_direction = "N" if destination[0] >= origin[0] else "S"
    directions = children_by_parent.get(origin_station["stop_id"], {})
    direction_order = [preferred_direction] + [d for d in ("N", "S") if d != preferred_direction]

    direction = None
    wait_minutes = None
    for candidate in direction_order:
        stop_id = directions.get(candidate)
        if stop_id is None:
            continue
        candidate_wait = get_next_arrival_minutes(stop_id)
        if candidate_wait is not None:
            direction = candidate
            wait_minutes = candidate_wait
            break

    if wait_minutes is None:
        return None

    route_miles, ride_minutes = estimate_ride_distance_and_time(
        (origin_station["lat"], origin_station["lon"]),
        (destination_station["lat"], destination_station["lon"]),
    )

    return {
        "origin_station": origin_station,
        "walk_to_station_miles": round(walk_to_station_mi, 2),
        "destination_station": destination_station,
        "walk_from_station_miles": round(walk_from_station_mi, 2),
        "direction": direction,
        "direction_was_fallback": direction != preferred_direction,
        "wait_minutes": round(wait_minutes, 1),
        "distance_miles": round(route_miles, 2),
        "ride_minutes": round(ride_minutes, 1),
        "price_usd": SUBWAY_FARE,
    }


def get_subway_option(origin, destination):
    """Public entry point. origin/destination are (lat, lon) tuples.

    Returns a dict shaped like modes.py's Mode.estimate() output (key,
    label, distance, time, price, energy, nature_vibez, carbon, notes) so
    it drops straight into scoring.py's ranking, or None if a live wait
    time isn't available right now (feed down, or nothing found for this
    station/direction) — callers should skip it the same way they'd skip
    any other missing source.
    """
    try:
        details = build_subway_details(origin, destination)
    except (requests.RequestException, KeyError, ValueError):
        return None

    if details is None:
        return None

    notes = (
        f"Live MTA data. Next train from {details['origin_station']['name']} "
        f"in {details['wait_minutes']} min, toward "
        f"{details['destination_station']['name']}."
    )
    if details["direction_was_fallback"]:
        notes += " (Opposite-direction train shown — none scheduled the other way right now.)"

    return {
        "key": "subway",
        "label": "Subway",
        "distance": details["distance_miles"],
        "time": round(details["wait_minutes"] + details["ride_minutes"], 1),
        "price": details["price_usd"],
        "energy": 3,
        "nature_vibez": 3,
        "carbon": round(90 * details["distance_miles"]),
        "notes": notes,
        "route_profile": "transit",
    }


if __name__ == "__main__":
    demo_trips = [
        ("Columbia University", (40.8075, -73.9626), (40.7359, -73.9911)),  # -> Union Square
        ("Times Square", (40.7580, -73.9855), (40.7061, -73.9969)),          # -> Brooklyn Bridge area
    ]

    for label, origin, destination in demo_trips:
        print(f"\n{label}: {origin} -> {destination}")
        result = get_subway_option(origin, destination)
        if result is None:
            print("  No live subway option available right now.")
        else:
            for key, value in result.items():
                print(f"  {key}: {value}")
