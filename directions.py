"""Real route distance and duration from the Google Maps Routes API.

The API key is read from the GOOGLE_MAPS_API_KEY environment variable (see
`.env.example`). When the key is missing or a request fails, callers fall
back to the rate-card estimates in `modes.py`, so the app still works
offline.

Docs: https://developers.google.com/maps/documentation/routes/compute_route_directions
"""

import json
import os
import urllib.error
import urllib.request

_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

# RYDESAVYR travel mode -> (Routes API travelMode, allowed transit sub-modes).
# The transit variants let "Subway" and "Bus" resolve to genuinely different
# routes instead of both getting Google's single best transit itinerary.
_TRAVEL_MODE = {
    "driving": ("DRIVE", None),
    "bicycling": ("BICYCLE", None),
    "walking": ("WALK", None),
    "transit": ("TRANSIT", None),
    "transit_subway": ("TRANSIT", ["SUBWAY", "LIGHT_RAIL"]),
    "transit_bus": ("TRANSIT", ["BUS"]),
    "transit_rail": ("TRANSIT", ["TRAIN", "RAIL"]),
}

METERS_PER_MILE = 1609.344


class DirectionsError(RuntimeError):
    """Raised for any failure so the caller can fall back to an estimate."""


def api_key() -> str:
    return os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()


def _waypoint(place):
    """Accept either an (lat, lng) pair or a plain address string."""
    if isinstance(place, (tuple, list)) and len(place) == 2:
        lat, lng = place
        return {"location": {"latLng": {"latitude": float(lat), "longitude": float(lng)}}}
    return {"address": str(place)}


def route(origin, destination, travel_mode: str) -> dict:
    """Return {"distance_miles": float, "duration_minutes": float} for one mode.

    Raises DirectionsError on any problem (no key, network error, no route).
    """
    key = api_key()
    if not key:
        raise DirectionsError("GOOGLE_MAPS_API_KEY is not set.")

    mode_spec = _TRAVEL_MODE.get(travel_mode)
    if mode_spec is None:
        raise DirectionsError(f"Unknown travel mode: {travel_mode!r}")
    google_mode, transit_submodes = mode_spec

    body = {
        "origin": _waypoint(origin),
        "destination": _waypoint(destination),
        "travelMode": google_mode,
    }
    # routingPreference is only valid for DRIVE / TWO_WHEELER.
    if google_mode == "DRIVE":
        body["routingPreference"] = "TRAFFIC_AWARE"
    if transit_submodes:
        body["transitPreferences"] = {"allowedTravelModes": transit_submodes}

    request = urllib.request.Request(
        _ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "routes.distanceMeters,routes.duration",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise DirectionsError(f"Routes API HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise DirectionsError(f"Routes API request failed: {exc}") from exc

    routes = payload.get("routes") or []
    if not routes:
        raise DirectionsError(f"No {travel_mode} route found for this trip.")

    leg = routes[0]
    meters = leg.get("distanceMeters")
    duration = str(leg.get("duration", ""))  # e.g. "1234s"
    if meters is None or not duration.endswith("s"):
        raise DirectionsError("Routes API response was missing distance or duration.")

    return {
        "distance_miles": meters / METERS_PER_MILE,
        "duration_minutes": float(duration[:-1]) / 60,
    }
