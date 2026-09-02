"""Weighted ranking across the factors from the proposal: price, time,
distance, energy, scenery, and carbon footprint.
"""

FACTORS = ["price", "time", "distance", "energy", "nature_vibez", "carbon"]

FACTOR_LABELS = {
    "price": "Price",
    "time": "Time",
    "distance": "Distance",
    "energy": "Energy",
    "nature_vibez": "Scenery",
    "carbon": "Carbon footprint",
}

# True where a lower raw value is the better outcome for that factor.
LOWER_IS_BETTER = {
    "price": True,
    "time": True,
    "distance": True,
    "energy": True,
    "carbon": True,
    "nature_vibez": False,
}

# Three-tier weighting: "does not matter" drops the factor from scoring
# entirely, "critical" counts 3x as much as "neutral".
TIER_ORDER = ["none", "neutral", "critical"]

TIER_LABELS = {
    "none": "Does not matter",
    "neutral": "Neutral",
    "critical": "Critical",
}

TIER_WEIGHTS = {
    "none": 0,
    "neutral": 1,
    "critical": 3,
}

DEFAULT_TIER = "neutral"


def _normalize(values, lower_is_better):
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0 for _ in values]
    if lower_is_better:
        return [(hi - v) / (hi - lo) for v in values]
    return [(v - lo) / (hi - lo) for v in values]


def rank_modes(estimates, tiers):
    """Rank a list of already-computed mode estimates using the user's tiers.

    Estimates are computed upstream (see modes.py / citibike.py / app.py) so
    that a live API quote can be spliced into one mode's dict before ranking.

    Any factor marked "critical" is the primary sort key — e.g. marking time
    critical puts the fastest option first, full stop. With multiple critical
    factors, modes are ranked by their average normalized score across just
    those factors. The overall weighted blend (used for the displayed score,
    and to break ties) still runs across every factor, weighted by tier, with
    "does not matter" factors excluded entirely.
    """
    normalized_by_factor = {
        factor: _normalize([e[factor] for e in estimates], LOWER_IS_BETTER[factor])
        for factor in FACTORS
    }

    critical_factors = [f for f in FACTORS if tiers.get(f) == "critical"]
    weights = {f: TIER_WEIGHTS[tiers.get(f, DEFAULT_TIER)] for f in FACTORS}
    total_weight = sum(weights.values()) or 1

    for i, estimate in enumerate(estimates):
        overall = sum(weights[f] * normalized_by_factor[f][i] for f in FACTORS)
        estimate["score"] = round(100 * overall / total_weight, 1)
        estimate["_critical_score"] = (
            sum(normalized_by_factor[f][i] for f in critical_factors) / len(critical_factors)
            if critical_factors
            else 0.0
        )

    ranked = sorted(estimates, key=lambda e: (e["_critical_score"], e["score"]), reverse=True)
    for estimate in ranked:
        del estimate["_critical_score"]
    return ranked
