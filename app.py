from flask import Flask, flash, render_template, request
from geopy.distance import geodesic

from citibike import get_citibike_option
from geocode import geocode_address
from modes import MODES
from scoring import (
    DEFAULT_TIER,
    FACTOR_LABELS,
    FACTORS,
    TIER_LABELS,
    TIER_ORDER,
    TIER_WEIGHTS,
    rank_modes,
)

app = Flask(__name__)
app.secret_key = "rydesavyr-dev"


@app.route("/", methods=["GET", "POST"])
def index():
    tiers = {factor: DEFAULT_TIER for factor in FACTORS}
    results = None
    origin_address = ""
    destination_address = ""

    if request.method == "POST":
        origin_address = request.form.get("origin_address", "").strip()
        destination_address = request.form.get("destination_address", "").strip()
        origin_lat = request.form.get("origin_lat", "").strip()
        origin_lng = request.form.get("origin_lng", "").strip()

        def tier_for(factor):
            raw = request.form.get(f"weight_{factor}", "")
            if raw.isdigit() and 0 <= int(raw) < len(TIER_ORDER):
                return TIER_ORDER[int(raw)]
            return DEFAULT_TIER

        tiers = {factor: tier_for(factor) for factor in FACTORS}
        weights = {factor: TIER_WEIGHTS[tiers[factor]] for factor in FACTORS}

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

            estimates = [mode.estimate(distance_miles) for mode in MODES if mode.key != "citibike"]
            citibike_mode = next(mode for mode in MODES if mode.key == "citibike")
            estimates.append(get_citibike_option(origin, destination) or citibike_mode.estimate(distance_miles))

            results = rank_modes(estimates, weights)
        except ValueError as exc:
            flash(str(exc))

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
    )


if __name__ == "__main__":
    app.run(debug=True)
