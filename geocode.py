"""Address -> (lat, lng) lookup using OpenStreetMap's free Nominatim service.

No API key required. Results are biased toward New York City since that's
RYDESAVYR's scope for now.

Nominatim's usage policy caps automated use at ~1 request/second per app —
fine for a single user typing with a debounce, but search_addresses() should
never be called in a tight loop.
"""

from geopy.geocoders import Nominatim

_geolocator = Nominatim(user_agent="rydesavyr-bootcamp-project")

# Rough NYC bounding box (all five boroughs), used to restrict results
# instead of just appending "New York" as text — a plain text suffix still
# lets ambiguous queries like "Columbia" match places anywhere in NY State.
_NYC_VIEWBOX = [(40.4957, -74.2557), (40.9176, -73.7002)]


def geocode_address(address: str):
    location = _geolocator.geocode(address, viewbox=_NYC_VIEWBOX, bounded=True)
    if location is None:
        raise ValueError(f"Couldn't find a location for “{address}”.")
    return (location.latitude, location.longitude)


def search_addresses(query: str, limit: int = 5):
    """Return up to `limit` candidate {label, lat, lon} matches for a
    partial address, for autocomplete. Empty list for a too-short query or
    if Nominatim finds nothing — never raises.
    """
    query = query.strip()
    if len(query) < 3:
        return []

    locations = _geolocator.geocode(
        query, viewbox=_NYC_VIEWBOX, bounded=True, exactly_one=False, limit=limit
    )
    if not locations:
        return []

    return [
        {"label": location.address, "lat": location.latitude, "lon": location.longitude}
        for location in locations
    ]
