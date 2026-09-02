"""Columbia University On-Demand Evening Shuttle — a free, geofenced,
evening-only shared-van service around the Morningside and Manhattanville
campuses, operated for Columbia by Via.

Standalone, no dependency on the rest of RYDESAVYR (modes.py, scoring.py,
app.py). Call ``get_shuttle_option()`` with (lat, lon) tuples; it returns
a dict shaped like ``modes.py``'s ``Mode.estimate()`` output, or ``None``
when the shuttle can't be used for this trip — either endpoint outside the
coverage area, or the request falls outside tonight's service window.
Callers skip a ``None`` the same way they'd skip any other unavailable
mode.

There is no public Via API and no Columbia shuttle data feed: booking
happens only in the "Evening Shuttle" app (Columbia UNI login) or through
the Via dispatcher at 646-692-0576. ``get_live_estimate()`` below is a
stub for the day Columbia/Via grant API access — the same wired-but-gated
pattern ``uber_client.py`` uses for Uber.

Facts current as of 2026 (transportation.columbia.edu/eveningshuttle and
.../content/evening-shuttle-service-monthly-start-times):

  - Free for anyone with an active UNI and a Columbia ID card.
  - Runs seven nights a week, every day of the year, until 3:00 a.m.
  - Start time shifts by month — earlier in winter, later in summer.
  - Rides must BOTH start and end inside the coverage area, and are never
    provided between the two campuses.

Run ``python columbia_shuttle.py`` for a standalone sanity check.
"""

from datetime import datetime

from geopy.distance import geodesic

# Columbia publishes only a hand-drawn coverage map
# (transportation.columbia.edu/eveningshuttle), so this is a bounding box
# traced around its outer edges: ~W 103rd St to the south, Riverside Drive
# to the west, Adam Clayton Powell Jr Blvd (7th Ave) to the east, ~W 137th
# St to the north. A box is deliberately looser than the real jagged edge,
# but it still keeps a trip to Brooklyn or the East Village from ever
# showing a shuttle option.
COVERAGE_SOUTH_LAT = 40.798   # ~W 103rd St
COVERAGE_NORTH_LAT = 40.822   # ~W 137th St
COVERAGE_WEST_LON = -73.969   # ~Riverside Dr
COVERAGE_EAST_LON = -73.948   # ~Adam Clayton Powell Jr Blvd

# Local clock hour (24h) at which service starts each night, by calendar
# month. Source: transportation.columbia.edu/content/
# evening-shuttle-service-monthly-start-times
SERVICE_START_HOUR_BY_MONTH = {
    1: 16, 2: 16, 3: 18, 4: 19, 5: 20, 6: 20,
    7: 20, 8: 20, 9: 18, 10: 18, 11: 16, 12: 16,
}
SERVICE_END_HOUR = 3  # 3:00 a.m., year-round

# It's a shared van: door-to-door like a car, but with detours to collect
# and drop other riders, plus a dispatch wait. These are estimates in the
# same spirit as modes.py's rate cards, not live figures.
SHARED_RIDE_DISTANCE_FACTOR = 1.15   # extra miles for other riders' stops
SHARED_RIDE_TIME_FACTOR = 1.35       # extra minutes for the same
TYPICAL_WAIT_MINUTES = 12            # app-quoted waits vary; 12 is a fair median
FALLBACK_ROUTE_FACTOR = 1.3          # driving detour vs straight line, no Google route
FALLBACK_AVG_SPEED_MPH = 18

ENERGY_COST = 1        # you just sit in the van
SCENERY = 3            # a van window at night
CARBON_G_PER_MILE = 200  # per-rider share of a shared van; between a bus and a car


def is_within_coverage(lat, lon):
    """True if (lat, lon) falls inside the Evening Shuttle bounding box."""
    return (
        COVERAGE_SOUTH_LAT <= lat <= COVERAGE_NORTH_LAT
        and COVERAGE_WEST_LON <= lon <= COVERAGE_EAST_LON
    )


def is_service_running(now=None):
    """True if the shuttle is operating at ``now`` (a naive local datetime,
    defaulting to the current local time).

    Each night's window runs from that month's start hour until 3:00 a.m.
    the next day, so both tonight's window and last night's (which ran past
    midnight into today) can cover the current moment.
    """
    now = now or datetime.now()
    start_hour = SERVICE_START_HOUR_BY_MONTH[now.month]
    started_tonight = now.hour >= start_hour
    still_running_from_last_night = now.hour < SERVICE_END_HOUR
    return started_tonight or still_running_from_last_night


def _format_hour(hour_24):
    suffix = "am" if hour_24 < 12 else "pm"
    return f"{hour_24 % 12 or 12}{suffix}"


def unavailable_reason(origin, destination, now=None):
    """Human-readable reason the shuttle can't serve this trip, or ``None``
    if it can. Useful for logging / an explanatory note."""
    now = now or datetime.now()
    if not is_within_coverage(*origin) or not is_within_coverage(*destination):
        return "both ends of the trip must be inside the Columbia coverage area"
    if not is_service_running(now):
        start_hour = SERVICE_START_HOUR_BY_MONTH[now.month]
        return f"runs {_format_hour(start_hour)}–3am only"
    return None


def get_live_estimate(*args, **kwargs):
    """Placeholder for a real Via API call.

    Columbia's Evening Shuttle is dispatched through Via, but Via's
    developer program is partnership-gated (their API docs aren't public
    yet) and Columbia exposes no feed of its own, so there is nothing to
    call. If Columbia/Via ever grant access, fill this in to return
    ``{"wait_minutes": ..., "price": ...}`` (or whatever the API provides)
    and splice it into ``get_shuttle_option`` — see ``uber_client.py`` for
    the same pattern with Uber's OAuth.
    """
    return None


def get_shuttle_option(origin, destination, route_info=None, now=None):
    """Public entry point. ``origin`` / ``destination`` are (lat, lon)
    tuples; ``route_info`` is an optional ``directions.route`` result for
    the driving mode (``{"distance_miles", "duration_minutes"}``).

    Returns a dict shaped like ``modes.py``'s ``Mode.estimate()`` output,
    or ``None`` when the shuttle isn't usable for this trip (outside the
    coverage area, or outside tonight's service hours).
    """
    now = now or datetime.now()
    if unavailable_reason(origin, destination, now) is not None:
        return None

    if route_info is not None:
        base_miles = route_info["distance_miles"]
        base_minutes = route_info["duration_minutes"]
        live = True
    else:
        straight_miles = geodesic(origin, destination).miles
        base_miles = straight_miles * FALLBACK_ROUTE_FACTOR
        base_minutes = (base_miles / FALLBACK_AVG_SPEED_MPH) * 60
        live = False

    route_miles = base_miles * SHARED_RIDE_DISTANCE_FACTOR
    ride_minutes = base_minutes * SHARED_RIDE_TIME_FACTOR
    total_minutes = ride_minutes + TYPICAL_WAIT_MINUTES

    live_estimate = get_live_estimate(origin, destination)
    if live_estimate and live_estimate.get("wait_minutes") is not None:
        total_minutes = ride_minutes + live_estimate["wait_minutes"]

    return {
        "key": "shuttle",
        "label": "Columbia Evening Shuttle",
        "distance": round(route_miles, 2),
        "time": round(total_minutes, 1),
        "price": 0.0,
        "energy": ENERGY_COST,
        "nature_vibez": SCENERY,
        "carbon": round(CARBON_G_PER_MILE * route_miles),
        "live": live,
        # It's a van on city streets — the map draws it with the driving engine.
        "route_profile": "driving",
        "notes": (
            "Free with an active UNI + Columbia ID. Shared van operated by Via, "
            "runs nightly until 3am within the Morningside/Manhattanville "
            "coverage area. Book in the Evening Shuttle app or call 646-692-0576. "
            + ("Driving distance and time from Google Maps, plus shared-ride and "
               "dispatch-wait estimates." if live else
               "Distance, time and wait are estimates.")
        ),
    }


if __name__ == "__main__":
    demo_trips = [
        # Both inside coverage: Columbia main campus -> Manhattanville.
        ("Campus -> Manhattanville", (40.8075, -73.9626), (40.8188, -73.9601)),
        # Destination well outside coverage: Columbia -> Union Square.
        ("Campus -> Union Square", (40.8075, -73.9626), (40.7359, -73.9911)),
    ]

    now = datetime.now()
    print(f"Local time now: {now:%Y-%m-%d %H:%M} "
          f"(service {'running' if is_service_running(now) else 'not running'})")
    for label, origin, destination in demo_trips:
        print(f"\n{label}: {origin} -> {destination}")
        result = get_shuttle_option(origin, destination, now=now)
        if result is None:
            print(f"  Not available — {unavailable_reason(origin, destination, now)}.")
        else:
            for key, value in result.items():
                print(f"  {key}: {value}")
