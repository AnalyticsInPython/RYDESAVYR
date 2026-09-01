from flask import Flask, flash, render_template, request
from geopy.distance import geodesic

from geocode import geocode_address
from modes import MODES
from scoring import FACTOR_LABELS, FACTORS, rank_modes

app = Flask(__name__)
app.secret_key = "rydesavyr-dev"

DEFAULT_WEIGHT = 5


@app.route("/", methods=["GET", "POST"])
def index():
    weights = {factor: DEFAULT_WEIGHT for factor in FACTORS}
    results = None
    origin_address = ""
    destination_address = ""

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
            results = rank_modes(MODES, distance_miles, weights)
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
    )


if __name__ == "__main__":
    app.run(debug=True)
