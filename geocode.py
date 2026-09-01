"""Address -> (lat, lng) lookup using OpenStreetMap's free Nominatim service.

No API key required. Results are biased toward New York City since that's
RYDESAVYR's scope for now.
"""

from geopy.geocoders import Nominatim

_geolocator = Nominatim(user_agent="rydesavyr-bootcamp-project")


def geocode_address(address: str):
    query = address if "new york" in address.lower() else f"{address}, New York, NY"
    location = _geolocator.geocode(query)
    if location is None:
        raise ValueError(f"Couldn't find a location for “{address}”.")
    return (location.latitude, location.longitude)
