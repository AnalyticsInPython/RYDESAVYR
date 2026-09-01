"""Weighted ranking across the factors from the proposal: price, time,
distance, energy, nature-vibez, carbon footprint, and morality.
"""

FACTORS = ["price", "time", "distance", "energy", "nature_vibez", "carbon", "morality"]

FACTOR_LABELS = {
    "price": "Price",
    "time": "Time",
    "distance": "Distance",
    "energy": "Energy",
    "nature_vibez": "Nature-vibez",
    "carbon": "Carbon footprint",
    "morality": "Morality",
}

# True where a lower raw value is the better outcome for that factor.
LOWER_IS_BETTER = {
    "price": True,
    "time": True,
    "distance": True,
    "energy": True,
    "carbon": True,
    "nature_vibez": False,
    "morality": False,
}


def _normalize(values, lower_is_better):
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0 for _ in values]
    if lower_is_better:
        return [(hi - v) / (hi - lo) for v in values]
    return [(v - lo) / (hi - lo) for v in values]


def rank_modes(modes, distance_miles, weights, route_infos=None):
    """Estimate every mode for this trip and rank them by weighted score (0-100).

    ``route_infos`` maps a mode's ``google_mode`` to a
    ``{"distance_miles", "duration_minutes"}`` dict from the Google Maps
    Routes API. Modes without an entry fall back to the rate-card formula.
    """
    route_infos = route_infos or {}
    estimates = [
        mode.estimate(distance_miles, route_infos.get(mode.google_mode))
        for mode in modes
    ]

    normalized_by_factor = {
        factor: _normalize([e[factor] for e in estimates], LOWER_IS_BETTER[factor])
        for factor in FACTORS
    }

    total_weight = sum(weights.get(factor, 0) for factor in FACTORS) or 1
    for i, estimate in enumerate(estimates):
        score = sum(
            weights.get(factor, 0) * normalized_by_factor[factor][i]
            for factor in FACTORS
        )
        estimate["score"] = round(100 * score / total_weight, 1)

    return sorted(estimates, key=lambda e: e["score"], reverse=True)
