import os

from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from geopy.distance import geodesic

from backend.modes import MODES
from backend.scoring import (
    DEFAULT_WEIGHT_POSITION,
    FACTORS,
    rank_modes,
)
from data.citibike import get_citibike_option
from data.columbia_shuttle import get_shuttle_option
from data.commuter_rail import is_trip_feasible as is_train_trip_feasible
from data.geocode import geocode_address, search_addresses
from data.mta_bus import get_bus_option
from data.mta_subway import get_subway_option
from data.routing import get_driving_route

# Run from the repo root (`python -m backend.app`) so this package-relative
# path to the front end's templates/static assets resolves regardless of
# the current working directory.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(_REPO_ROOT, "frontend", "templates"),
    static_folder=os.path.join(_REPO_ROOT, "frontend", "static"),
)
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

    # Commuter Train is a rate-card formula like Uber/Lyft/Taxi, but unlike
    # those it isn't always a real option: it only makes sense when both
    # ends of the trip are within a comfortable walk of an actual LIRR/
    # Metro-North station (see commuter_rail.py) -- otherwise it's silently
    # dropped instead of formula-estimating a train ride that doesn't exist.
    train_feasible = is_train_trip_feasible(origin, destination)
    estimates = [
        estimate_mode(mode) for mode in MODES
        if mode.key not in _LIVE_MODE_SOURCES
        and (mode.key != "train" or train_feasible)
    ]
    for key, get_live_option in _LIVE_MODE_SOURCES.items():
        fallback_mode = next(mode for mode in MODES if mode.key == key)
        estimates.append(get_live_option(origin, destination) or estimate_mode(fallback_mode))

    # The Columbia Evening Shuttle is a conditional mode, not an always-on
    # one: it only appears when the trip is inside its coverage area and
    # within tonight's service hours, so there is no rate-card fallback. It
    # travels by road, so it reuses the same OSRM driving route.
    shuttle_option = get_shuttle_option(origin, destination, driving_route)
    if shuttle_option is not None:
        estimates.append(shuttle_option)

    return rank_modes(estimates, tiers)


def _spotlights(results):
    """The handful of options worth putting in front of the user, each
    paired with the stat(s) that earn it a spot -- rather than making them
    scan every mode to find these themselves.

    Rather than a single "top pick" blending every factor (price, time,
    carbon, scenery, ...), the cards span the cheap-to-fast spectrum
    directly: the cheapest option, the fastest, and a "best value" pick in
    between that trades the two off against each other, plus the most
    eco-friendly option called out on its own.

    When the same mode wins more than one category (e.g. Citibike is both
    the cheapest and the greenest), it gets a single card carrying every
    badge it earned instead of one repeated card per category.
    """
    def normalized(factor):
        values = [r[factor] for r in results]
        lo, hi = min(values), max(values)
        if hi == lo:
            return {r["key"]: 1.0 for r in results}
        return {r["key"]: (hi - r[factor]) / (hi - lo) for r in results}

    price_score = normalized("price")
    time_score = normalized("time")
    best_value = max(results, key=lambda r: price_score[r["key"]] + time_score[r["key"]])

    candidates = [
        ("Cheapest", ["price"], min(results, key=lambda r: r["price"])),
        ("Best value", ["price", "time"], best_value),
        ("Fastest", ["time"], min(results, key=lambda r: r["time"])),
        ("Most eco-friendly", ["carbon"], min(results, key=lambda r: r["carbon"])),
    ]
    by_mode_key = {}
    order = []
    for title, highlights, mode in candidates:
        card = by_mode_key.setdefault(mode["key"], {"titles": [], "highlights": [], "mode": mode})
        card["titles"].append(title)
        card["highlights"].extend(highlights)
        if mode["key"] not in order:
            order.append(mode["key"])

    cards = [by_mode_key[key] for key in order]
    # Best value leads the lineup regardless of which mode it landed on --
    # it's the one card meant to answer "which should I actually pick?", so
    # it gets top billing over Cheapest/Fastest/Most eco-friendly.
    cards.sort(key=lambda card: "Best value" not in card["titles"])
    return cards


def _render_form(origin_address="", destination_address=""):
    return render_template(
        "index.html",
        origin_address=origin_address,
        destination_address=destination_address,
    )


def _render_results(results, origin_address, destination_address,
                    origin=None, destination=None):
    return render_template(
        "results.html",
        spotlights=_spotlights(results),
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


@app.route("/", methods=["GET"])
def index():
    return _render_form()


@app.route("/results", methods=["GET", "POST"])
def results():
    # A bare GET (refresh, bookmark, back button) has no trip to rank -- send
    # the user to the form instead of a 405.
    if request.method == "GET":
        return redirect(url_for("index"))

    origin_address = request.form.get("origin_address", "").strip()
    destination_address = request.form.get("destination_address", "").strip()
    origin_lat = request.form.get("origin_lat", "").strip()
    origin_lng = request.form.get("origin_lng", "").strip()
    destination_lat = request.form.get("destination_lat", "").strip()
    destination_lng = request.form.get("destination_lng", "").strip()

    # No priority controls on the form -- every factor gets scoring.py's
    # default (neutral) weight position.
    tiers = {factor: DEFAULT_WEIGHT_POSITION for factor in FACTORS}

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

        computed = _compute_results(origin, destination, tiers)
    except ValueError as exc:
        # Send the user back to the form (with what they typed) rather than
        # to an empty results page.
        flash(str(exc))
        return _render_form(origin_address, destination_address)

    return _render_results(
        computed, origin_address, destination_address, origin, destination
    )


if __name__ == "__main__":
    # 5000 collides with macOS's AirPlay Receiver (Control Center), which
    # also listens on that port and silently swallows browser connections.
    app.run(debug=True, port=5050)
