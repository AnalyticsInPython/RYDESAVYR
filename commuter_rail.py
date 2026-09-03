"""Feasibility check for the Commuter Train (LIRR / Metro-North) mode.

There's no free live-arrival API for LIRR/Metro-North (see README), so
modes.py's "train" entry is a rate-card formula like Uber/Lyft/Taxi. But
unlike those, a commuter train literally isn't an option unless both ends
of the trip are within a reasonable walk of an actual LIRR or Metro-North
station -- most trips inside NYC never come near one, yet the formula
previously ran unconditionally for every trip regardless of distance to a
station, suggesting a nonsensical "take the LIRR" option for e.g. a
two-block walk in the East Village.

This mirrors columbia_shuttle.py's pattern: a standalone feasibility check
(``is_trip_feasible``) that app.py uses to decide whether to include the
mode at all, rather than a live quote.

The station list below is a hand-picked set of major terminals and
representative branch stations for both railroads -- not the full GTFS
station list (LIRR/Metro-North don't publish a free one the way NYCT
subway/bus do), but enough to catch "is there plausibly a station near
here at all" rather than attempting exact walkshed accuracy.
"""

from geopy.distance import geodesic

# A trip only makes sense by commuter rail if both ends are within a
# comfortable walk of *some* station -- matched to modes.py's Walking
# entry's implied willingness to walk roughly 15-20 minutes to transit.
MAX_STATION_WALK_MILES = 1.0

STATIONS = [
    # LIRR: both Manhattan terminals, the Jamaica hub, and a spread of
    # branch-line stations across Queens/Nassau/Suffolk.
    ("Penn Station", 40.7506, -73.9935),
    ("Grand Central Madison", 40.7527, -73.9772),
    ("Atlantic Terminal", 40.6841, -73.9773),
    ("Jamaica", 40.7006, -73.8016),
    ("Flushing-Main St", 40.7595, -73.8301),
    ("Woodside", 40.7453, -73.9028),
    ("Great Neck", 40.7885, -73.7285),
    ("Port Washington", 40.8296, -73.6982),
    ("Hicksville", 40.7684, -73.5251),
    ("Ronkonkoma", 40.8153, -73.1054),
    ("Babylon", 40.6968, -73.3256),
    ("Huntington", 40.8676, -73.4257),
    ("Long Beach", 40.5885, -73.6579),
    ("Far Rockaway", 40.6035, -73.7553),
    # Metro-North: Grand Central plus a spread of Harlem/Hudson/New Haven
    # line stations across the Bronx, Westchester, and Connecticut.
    ("Grand Central Terminal", 40.7527, -73.9772),
    ("Harlem-125th St", 40.8043, -73.9375),
    ("Fordham", 40.8613, -73.9002),
    ("Mount Vernon East", 40.9126, -73.8282),
    ("New Rochelle", 40.9128, -73.7826),
    ("Stamford", 41.0466, -73.5427),
    ("White Plains", 41.0303, -73.7629),
    ("Tarrytown", 41.0765, -73.8592),
    ("Yonkers", 40.9312, -73.8987),
    ("Poughkeepsie", 41.7003, -73.9339),
]


def nearest_station_miles(lat, lon):
    """Straight-line distance in miles to the closest station in `STATIONS`."""
    return min(geodesic((lat, lon), (s[1], s[2])).miles for s in STATIONS)


def is_trip_feasible(origin, destination):
    """True if both `origin` and `destination` ((lat, lon) tuples) are
    within a comfortable walk of some LIRR/Metro-North station."""
    return (
        nearest_station_miles(*origin) <= MAX_STATION_WALK_MILES
        and nearest_station_miles(*destination) <= MAX_STATION_WALK_MILES
    )


if __name__ == "__main__":
    demo_trips = [
        # Both near actual stations: Grand Central area -> White Plains area.
        ("Grand Central -> White Plains", (40.7527, -73.9772), (41.0303, -73.7629)),
        # Neither end near a commuter rail station: East Village -> SoHo.
        ("East Village -> SoHo", (40.7265, -73.9815), (40.7233, -74.0030)),
    ]
    for label, origin, destination in demo_trips:
        feasible = is_trip_feasible(origin, destination)
        print(f"{label}: {'feasible' if feasible else 'not feasible'} "
              f"(origin {nearest_station_miles(*origin):.2f} mi, "
              f"destination {nearest_station_miles(*destination):.2f} mi to nearest station)")
