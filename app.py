import os
import secrets
import time

from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from geopy.distance import geodesic

import uber_client
from citibike import get_citibike_option
from geocode import geocode_address, search_addresses
from modes import MODES
from mta_bus import get_bus_option
from mta_subway import get_subway_option
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


def _valid_uber_access_token():
    """Return a usable access token from the session, refreshing it if it
    expired, or None if the user has never connected / refresh failed."""
    token = session.get("uber_token")
    if not token:
        return None
    if token["expires_at"] - 60 < time.time():
        if not token.get("refresh_token"):
            return None
        try:
            token = uber_client.refresh_access_token(token["refresh_token"])
        except Exception:
            session.pop("uber_token", None)
            return None
        session["uber_token"] = token
    return token["access_token"]


_LIVE_MODE_SOURCES = {
    "citibike": get_citibike_option,
    "subway": get_subway_option,
    "bus": get_bus_option,
}


def _compute_results(origin, destination, tiers):
    distance_miles = geodesic(origin, destination).miles

    estimates = [mode.estimate(distance_miles) for mode in MODES if mode.key not in _LIVE_MODE_SOURCES]
    for key, get_live_option in _LIVE_MODE_SOURCES.items():
        fallback_mode = next(mode for mode in MODES if mode.key == key)
        estimates.append(get_live_option(origin, destination) or fallback_mode.estimate(distance_miles))

    access_token = _valid_uber_access_token()
    if access_token:
        live = uber_client.get_live_estimate(access_token, origin, destination)
        if live:
            for estimate in estimates:
                if estimate["key"] == "uber":
                    estimate.update({k: v for k, v in live.items() if v is not None})

    return rank_modes(estimates, tiers)


def _start_uber_login(pending_trip=None):
    if pending_trip is not None:
        session["pending_trip"] = pending_trip
    state = secrets.token_urlsafe(16)
    session["uber_oauth_state"] = state
    redirect_uri = url_for("uber_callback", _external=True)
    return redirect(uber_client.authorize_url(redirect_uri, state))


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
        uber_connected=bool(session.get("uber_token")),
        uber_available=uber_client.is_configured(),
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

            # Auto-connect to Uber the first time it's needed, instead of
            # making the user find a separate "connect account" button —
            # most people will be doing this one-handed on a phone.
            if uber_client.is_configured() and not _valid_uber_access_token():
                return _start_uber_login({
                    "origin": origin,
                    "destination": destination,
                    "tiers": tiers,
                    "origin_address": origin_address,
                    "destination_address": destination_address,
                })

            results = _compute_results(origin, destination, tiers)
        except ValueError as exc:
            flash(str(exc))

    return _render(tiers, results, origin_address, destination_address, origin, destination)


@app.route("/uber/login")
def uber_login():
    if not uber_client.is_configured():
        flash("Uber login isn't set up yet — add UBER_CLIENT_ID/UBER_CLIENT_SECRET to .env first.")
        return redirect(url_for("index"))
    return _start_uber_login()


@app.route("/uber/callback")
def uber_callback():
    pending = session.pop("pending_trip", None)
    expected_state = session.pop("uber_oauth_state", None)
    error = request.args.get("error")
    state = request.args.get("state")

    if error == "access_denied":
        flash("Uber sign-in was cancelled — showing an estimated Uber price instead.")
    elif error:
        flash(f"Uber sign-in failed ({error}) — showing an estimated Uber price instead.")
    elif not state or state != expected_state:
        flash("Uber sign-in couldn't be verified — showing an estimated Uber price instead.")
    else:
        try:
            redirect_uri = url_for("uber_callback", _external=True)
            session["uber_token"] = uber_client.exchange_code(request.args.get("code"), redirect_uri)
        except Exception:
            flash("Couldn't connect to Uber right now — showing an estimated Uber price instead.")

    if pending is None:
        return redirect(url_for("index"))

    results = _compute_results(pending["origin"], pending["destination"], pending["tiers"])
    return _render(
        pending["tiers"], results, pending["origin_address"], pending["destination_address"],
        pending["origin"], pending["destination"],
    )


@app.route("/uber/disconnect")
def uber_disconnect():
    session.pop("uber_token", None)
    return redirect(url_for("index"))


if __name__ == "__main__":
    # 5000 collides with macOS's AirPlay Receiver (Control Center), which
    # also listens on that port and silently swallows browser connections.
    app.run(debug=True, port=5050)
