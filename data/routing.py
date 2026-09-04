"""Real road-network routing via OSRM's public demo server -- standalone,
no dependency on modes.py/scoring.py/app.py.

Used for the driving-based modes (Uber, Lyft, and Taxi) instead of the
straight-line-distance x route_factor fudge every mode's static estimate()
still falls back to. Returns None on any failure so callers use that
straight-line fallback the same way they'd skip any other unavailable live
source.

Uses http://router.project-osrm.org, the OSRM project's free public demo
server -- no API key, no signup required. Per the OSRM project's own docs
this server is explicitly "not meant for production use" (no uptime or
rate-limit guarantees) -- acceptable for a small non-commercial student
project, but swap in a self-hosted OSRM instance or a paid routing
provider (e.g. OpenRouteService, which does require a free API key) before
relying on this for anything higher-stakes.

Only the "driving" profile actually works on the public demo -- "foot" and
"bike" silently return the identical car-network route (verified
2026-09-02: both gave the exact same distance/duration as "driving" for a
sample trip), so this is deliberately NOT used for Walking or Citibike,
which keep their existing straight-line estimates.
"""

import requests

OSRM_BASE = "http://router.project-osrm.org"
REQUEST_TIMEOUT_SECONDS = 10
METERS_PER_MILE = 1609.344


def get_driving_route(origin, destination):
    """origin/destination are (lat, lon) tuples. Returns (route_miles,
    travel_minutes) from a real driving route, or None if the request
    fails or no route is found, for any reason.
    """
    try:
        # OSRM wants "lon,lat", the opposite order from every other API
        # this project talks to.
        coords = f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
        response = requests.get(
            f"{OSRM_BASE}/route/v1/driving/{coords}",
            params={"overview": "false"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None

        route = data["routes"][0]
        route_miles = route["distance"] / METERS_PER_MILE
        travel_minutes = route["duration"] / 60
        return route_miles, travel_minutes
    except (requests.RequestException, KeyError, TypeError, ValueError, IndexError):
        return None


if __name__ == "__main__":
    demo_trips = [
        ("Columbia University", (40.8075, -73.9626), (40.7359, -73.9911)),  # -> Union Square
        ("Times Square", (40.7580, -73.9855), (40.7061, -73.9969)),          # -> Brooklyn Bridge area
    ]
    for label, origin, destination in demo_trips:
        print(f"\n{label}: {origin} -> {destination}")
        result = get_driving_route(origin, destination)
        if result is None:
            print("  No route available.")
        else:
            miles, minutes = result
            print(f"  {miles:.2f} mi, {minutes:.1f} min")
