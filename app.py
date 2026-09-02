import os

from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

from flask import Flask, flash, jsonify, render_template, request
from geopy.distance import geodesic

from citibike import get_citibike_option
from geocode import geocode_address, search_addresses
from modes import MODES
from mta_bus import get_bus_option
from mta_subway import get_subway_option
from routing import get_driving_route
from scoring import (
    DEFAULT_TIER,
    FACTOR_LABELS,
    FACTORS,
    TIER_LABELS,
    TIER_ORDER,
    rank_modes,
)

app = Flask(__name__)
app.secret_key = "rydesavyr-dev"


_LIVE_MODE_SOURCES = {
    "citibike": get_citibike_option,
    "subway": get_subway_option,
    "bus": get_bus_option,
}

# Modes that actually travel by car -- these prefer a real OSRM driving
# route over the straight-line x route_factor guess every other mode uses.
# Walking/Citibike are deliberately excluded: routing.py's OSRM public demo
# only serves the driving network (see its docstring), so routing them
# through it would silently return a car route, not a walking/biking one.
_DRIVING_MODE_KEYS = {"uber", "lyft", "taxi"}


def _compute_results(origin, destination, tiers):
    distance_miles = geodesic(origin, destination).miles
    driving_route = get_driving_route(origin, destination)

    def estimate_mode(mode):
        if driving_route is not None and mode.key in _DRIVING_MODE_KEYS:
            route_miles, travel_minutes = driving_route
            return mode.estimate_from_route(route_miles, travel_minutes)
        return mode.estimate(distance_miles)

    estimates = [estimate_mode(mode) for mode in MODES if mode.key not in _LIVE_MODE_SOURCES]
    for key, get_live_option in _LIVE_MODE_SOURCES.items():
        fallback_mode = next(mode for mode in MODES if mode.key == key)
        estimates.append(get_live_option(origin, destination) or estimate_mode(fallback_mode))

    return rank_modes(estimates, tiers)


def _render(tiers, results, origin_address, destination_address, origin=None, destination=None):
    return render_template(
        "index.html",
        tiers=tiers,
        tier_order=TIER_ORDER,
        tier_labels=TIER_LABELS,
        factors=FACTORS,
        factor_labels=FACTOR_LABELS,
        results=results,
        origin_address=origin_address,
        destination_address=destination_address,
        origin=origin,
        destination=destination,
        google_maps_api_key=GOOGLE_MAPS_API_KEY,
    )


@app.route("/geocode/search")
def geocode_search():
    return jsonify(search_addresses(request.args.get("q", "")))


@app.route("/", methods=["GET", "POST"])
def index():
    tiers = {factor: DEFAULT_TIER for factor in FACTORS}
    results = None
    origin_address = ""
    destination_address = ""
    origin = None
    destination = None

    if request.method == "POST":
        origin_address = request.form.get("origin_address", "").strip()
        destination_address = request.form.get("destination_address", "").strip()
        origin_lat = request.form.get("origin_lat", "").strip()
        origin_lng = request.form.get("origin_lng", "").strip()
        destination_lat = request.form.get("destination_lat", "").strip()
        destination_lng = request.form.get("destination_lng", "").strip()

        def tier_for(factor):
            raw = request.form.get(f"weight_{factor}", "")
            if raw.isdigit() and 0 <= int(raw) < len(TIER_ORDER):
                return TIER_ORDER[int(raw)]
            return DEFAULT_TIER

        tiers = {factor: tier_for(factor) for factor in FACTORS}

        try:
            if origin_lat and origin_lng:
                origin = (float(origin_lat), float(origin_lng))
            elif origin_address:
                origin = geocode_address(origin_address)
            else:
                raise ValueError("Share your location or enter a starting address.")

            if destination_lat and destination_lng:
                destination = (float(destination_lat), float(destination_lng))
            elif destination_address:
                destination = geocode_address(destination_address)
            else:
                raise ValueError("Enter a destination address.")

            results = _compute_results(origin, destination, tiers)
        except ValueError as exc:
            flash(str(exc))

    return _render(tiers, results, origin_address, destination_address, origin, destination)


if __name__ == "__main__":
    # 5000 collides with macOS's AirPlay Receiver (Control Center), which
    # also listens on that port and silently swallows browser connections.
    app.run(debug=True, port=5050)
