import os

from dotenv import load_dotenv
from flask import Flask, flash, render_template, request
from geopy.distance import geodesic

from directions import DirectionsError, api_key, route
from geocode import geocode_address
from modes import MODES
from scoring import FACTOR_LABELS, FACTORS, rank_modes

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "rydesavyr-dev")

DEFAULT_WEIGHT = 5


def fetch_routes(origin, destination):
    """Call the Google Maps Routes API once per distinct travel mode.

    Returns ``(route_infos, errors)`` where ``route_infos`` is keyed by
    ``google_mode``. Any mode that fails is left out and its message added
    to ``errors`` so the rest of the trip still ranks from rate cards.
    """
    route_infos = {}
    errors = []
    for google_mode in sorted({mode.google_mode for mode in MODES}):
        try:
            route_infos[google_mode] = route(origin, destination, google_mode)
        except DirectionsError as exc:
            errors.append(f"{google_mode}: {exc}")
    return route_infos, errors


@app.route("/", methods=["GET", "POST"])
def index():
    weights = {factor: DEFAULT_WEIGHT for factor in FACTORS}
    results = None
    origin_address = ""
    destination_address = ""
    data_source = None

    if request.method == "POST":
        origin_address = request.form.get("origin_address", "").strip()
        destination_address = request.form.get("destination_address", "").strip()
        origin_lat = request.form.get("origin_lat", "").strip()
        origin_lng = request.form.get("origin_lng", "").strip()

        weights = {
            factor: float(request.form.get(f"weight_{factor}", DEFAULT_WEIGHT))
            for factor in FACTORS
        }

        try:
            if origin_lat and origin_lng:
                origin = (float(origin_lat), float(origin_lng))
            elif origin_address:
                origin = geocode_address(origin_address)
            else:
                raise ValueError("Share your location or enter a starting address.")

            if not destination_address:
                raise ValueError("Enter a destination address.")
            destination = geocode_address(destination_address)

            distance_miles = geodesic(origin, destination).miles

            route_infos = {}
            if api_key():
                # Routes API takes the typed destination address directly, which
                # is more precise than the geocoded point.
                route_infos, errors = fetch_routes(origin, destination_address)
                if errors:
                    app.logger.warning("Routes API partial failure: %s", "; ".join(errors))

            results = rank_modes(MODES, distance_miles, weights, route_infos)

            live_count = sum(1 for r in results if r["live"])
            if not api_key():
                data_source = (
                    "Set GOOGLE_MAPS_API_KEY to pull live distance and travel time "
                    "from Google Maps. Showing rate-card estimates for now."
                )
            elif live_count == len(results):
                data_source = "Distance and travel time are live from Google Maps."
            elif live_count:
                data_source = (
                    f"{live_count} of {len(results)} options use live Google Maps "
                    "data; the rest fell back to rate-card estimates."
                )
            else:
                data_source = (
                    "Google Maps returned no routes for this trip — showing "
                    "rate-card estimates."
                )
        except ValueError as exc:
            flash(str(exc))

    return render_template(
        "index.html",
        weights=weights,
        factors=FACTORS,
        factor_labels=FACTOR_LABELS,
        results=results,
        origin_address=origin_address,
        destination_address=destination_address,
        data_source=data_source,
    )


if __name__ == "__main__":
    app.run(debug=True)
