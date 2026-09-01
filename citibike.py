"""Live Citibike GBFS integration — standalone, no dependency on the rest
of RYDESAVYR (modes.py, scoring.py, app.py).

Dependencies: requests, geopy (both already in requirements.txt).

Pulls real-time station/bike/dock data from Citibike's public GBFS feed
(auto-discovered from https://gbfs.citibikenyc.com/gbfs/gbfs.json, so this
keeps working if the sub-feed URLs ever change) and turns it into a single
best pickup/dropoff pairing plus a price and time estimate.

Can be copied into any other project as-is: just call get_citibike_option()
with (lat, lon) tuples. If it can't find an available bike or a free dock,
or the feed is unreachable, it returns None instead of raising, so callers
can skip it the same way they'd skip any other unavailable travel mode.

Run `python citibike.py` directly for a standalone sanity check.
"""

import time

import requests
from geopy.distance import geodesic

GBFS_AUTODISCOVERY_URL = "https://gbfs.citibikenyc.com/gbfs/gbfs.json"
REQUEST_TIMEOUT_SECONDS = 10

# Non-member single-ride pricing, verified against
# https://citibikenyc.com/pricing/single-ride on 2026-09-01.
SINGLE_RIDE_UNLOCK_FEE = 4.99
CLASSIC_BIKE_FREE_MINUTES = 30
CLASSIC_BIKE_OVERAGE_PER_MIN = 0.41   # after the free 30 minutes
EBIKE_PER_MIN = 0.41                  # from minute 1, no free minutes

# Route-estimation assumptions (straight-line distance x detour factor),
# matched to modes.py's static Citibike entry for consistency.
ROUTE_FACTOR = 1.2
AVG_SPEED_MPH = 8

STATION_INFO_CACHE_TTL_SECONDS = 600  # station locations barely change

_feed_urls_cache = None
_station_info_cache = {"data": None, "fetched_at": 0.0}


def _get_feed_urls():
    """Fetch (and cache forever) the GBFS auto-discovery feed's sub-URLs."""
    global _feed_urls_cache
    if _feed_urls_cache is not None:
        return _feed_urls_cache

    response = requests.get(GBFS_AUTODISCOVERY_URL, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    feeds = response.json()["data"]["en"]["feeds"]
    _feed_urls_cache = {feed["name"]: feed["url"] for feed in feeds}
    return _feed_urls_cache


def get_station_information():
    """Return [{station_id, name, lat, lon}, ...], cached for 10 minutes."""
    now = time.monotonic()
    if (
        _station_info_cache["data"] is not None
        and now - _station_info_cache["fetched_at"] < STATION_INFO_CACHE_TTL_SECONDS
    ):
        return _station_info_cache["data"]

    url = _get_feed_urls()["station_information"]
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    stations = [
        {
            "station_id": s["station_id"],
            "name": s["name"],
            "lat": s["lat"],
            "lon": s["lon"],
        }
        for s in response.json()["data"]["stations"]
    ]
    _station_info_cache["data"] = stations
    _station_info_cache["fetched_at"] = now
    return stations


def get_station_status():
    """Return {station_id: {bikes, ebikes, docks}}, fetched fresh every call."""
    url = _get_feed_urls()["station_status"]
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return {
        s["station_id"]: {
            "bikes": s.get("num_bikes_available", 0),
            "ebikes": s.get("num_ebikes_available", 0),
            "docks": s.get("num_docks_available", 0),
        }
        for s in response.json()["data"]["stations"]
    }


def find_nearest_pickup_station(lat, lon, stations, status_by_id):
    """Nearest station with at least one bike (classic or e-bike) available.

    Returns (station, status, distance_miles) or None.
    """
    candidates = []
    for station in stations:
        status = status_by_id.get(station["station_id"])
        if not status or status["bikes"] <= 0:
            continue
        distance = geodesic((lat, lon), (station["lat"], station["lon"])).miles
        candidates.append((station, status, distance))

    if not candidates:
        return None
    return min(candidates, key=lambda c: c[2])


def find_nearest_dropoff_station(lat, lon, stations, status_by_id):
    """Nearest station with at least one free dock. Returns (station, status,
    distance_miles) or None.
    """
    candidates = []
    for station in stations:
        status = status_by_id.get(station["station_id"])
        if not status or status["docks"] <= 0:
            continue
        distance = geodesic((lat, lon), (station["lat"], station["lon"])).miles
        candidates.append((station, status, distance))

    if not candidates:
        return None
    return min(candidates, key=lambda c: c[2])


def estimate_ride_distance_and_time(pickup_latlon, dropoff_latlon):
    """Straight-line distance x detour factor, at an average city cycling
    speed. Returns (route_miles, minutes).
    """
    straight_line_miles = geodesic(pickup_latlon, dropoff_latlon).miles
    route_miles = straight_line_miles * ROUTE_FACTOR
    minutes = (route_miles / AVG_SPEED_MPH) * 60
    return route_miles, minutes


def compute_price(ride_minutes, is_ebike):
    """Single-ride Citibike price for a ride of this length and bike type."""
    if is_ebike:
        return SINGLE_RIDE_UNLOCK_FEE + EBIKE_PER_MIN * ride_minutes

    overage_minutes = max(0.0, ride_minutes - CLASSIC_BIKE_FREE_MINUTES)
    return SINGLE_RIDE_UNLOCK_FEE + CLASSIC_BIKE_OVERAGE_PER_MIN * overage_minutes


def build_citibike_details(origin, destination):
    """Do the actual work and return every intermediate piece as a plain
    dict: pickup/dropoff stations, their live availability, chosen bike
    type, computed distance/time/price. No Option/Mode wrapper — useful on
    its own if a caller wants the raw station data.

    Returns None if the feed can't be reached, no pickup station has a
    bike, or no dropoff station near the destination has a free dock.
    """
    stations = get_station_information()
    status_by_id = get_station_status()

    pickup = find_nearest_pickup_station(origin[0], origin[1], stations, status_by_id)
    if pickup is None:
        return None
    pickup_station, pickup_status, walk_to_pickup_mi = pickup

    dropoff = find_nearest_dropoff_station(
        destination[0], destination[1], stations, status_by_id
    )
    if dropoff is None:
        return None
    dropoff_station, dropoff_status, walk_from_dropoff_mi = dropoff

    # Classic bikes go first; e-bike only if that's all that's left.
    is_ebike = pickup_status["bikes"] <= 0 < pickup_status["ebikes"]

    route_miles, ride_minutes = estimate_ride_distance_and_time(
        (pickup_station["lat"], pickup_station["lon"]),
        (dropoff_station["lat"], dropoff_station["lon"]),
    )
    price = compute_price(ride_minutes, is_ebike)

    return {
        "pickup_station": pickup_station,
        "pickup_status": pickup_status,
        "walk_to_pickup_miles": round(walk_to_pickup_mi, 2),
        "dropoff_station": dropoff_station,
        "dropoff_status": dropoff_status,
        "walk_from_dropoff_miles": round(walk_from_dropoff_mi, 2),
        "is_ebike": is_ebike,
        "distance_miles": round(route_miles, 2),
        "time_minutes": round(ride_minutes, 1),
        "price_usd": round(price, 2),
    }


def get_citibike_option(origin, destination):
    """Public entry point. origin/destination are (lat, lon) tuples.

    Returns a dict shaped like modes.py's Mode.estimate() output (key,
    label, distance, time, price, energy, nature_vibez, carbon, morality,
    notes) so it drops straight into scoring.py's ranking, or None if a
    real Citibike trip isn't currently available (no bikes, no docks, or
    the feed is down) — callers should skip it the same way they'd skip
    any other missing source.
    """
    try:
        details = build_citibike_details(origin, destination)
    except (requests.RequestException, KeyError, ValueError):
        return None

    if details is None:
        return None

    is_ebike = details["is_ebike"]
    notes = (
        "Live Citibike GBFS data. "
        + ("E-bike" if is_ebike else "Classic bike")
        + f" from {details['pickup_station']['name']}, "
        f"docking at {details['dropoff_station']['name']}."
    )

    return {
        "key": "citibike",
        "label": "Citibike",
        "distance": details["distance_miles"],
        "time": details["time_minutes"],
        "price": details["price_usd"],
        "energy": 4 if is_ebike else 7,
        "nature_vibez": 8,
        "carbon": 0,
        "morality": 9,
        "notes": notes,
    }


if __name__ == "__main__":
    demo_trips = [
        ("Columbia University", (40.8075, -73.9626), (40.7359, -73.9911)),  # -> Union Square
        ("Times Square", (40.7580, -73.9855), (40.7061, -73.9969)),          # -> Brooklyn Bridge area
    ]

    for label, origin, destination in demo_trips:
        print(f"\n{label}: {origin} -> {destination}")
        result = get_citibike_option(origin, destination)
        if result is None:
            print("  No Citibike option available right now.")
        else:
            for key, value in result.items():
                print(f"  {key}: {value}")
