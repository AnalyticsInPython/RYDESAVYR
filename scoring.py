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

# Sliders report a continuous float position in [0, len(TIER_ORDER) - 1]
# rather than snapping to one of the three named tiers -- this is that
# position's default (matches DEFAULT_TIER's index, "neutral").
DEFAULT_WEIGHT_POSITION = float(TIER_ORDER.index(DEFAULT_TIER))


def _weight_for_position(position):
    """Continuous generalization of TIER_WEIGHTS: linearly interpolates
    between the three named tiers' weights, so a slider that's resting
    partway between e.g. "neutral" and "critical" gets a proportional
    weight instead of being forced to snap to one or the other.
    """
    position = max(0.0, min(float(len(TIER_ORDER) - 1), position))
    none_weight, neutral_weight, critical_weight = (TIER_WEIGHTS[t] for t in TIER_ORDER)
    if position <= 1:
        return none_weight + position * (neutral_weight - none_weight)
    return neutral_weight + (position - 1) * (critical_weight - neutral_weight)


def _criticality(position):
    """0 at "neutral" or below, ramping linearly up to 1 at fully
    "critical" -- the continuous replacement for membership in a hard
    "which factors are marked critical" list.
    """
    return max(0.0, min(1.0, position - 1.0))


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

    `tiers` maps each factor to a continuous float position in
    [0, len(TIER_ORDER) - 1] rather than one of the three named tiers
    directly — see `_weight_for_position` / `_criticality`. Sliders left
    exactly on "does not matter" / "neutral" / "critical" behave exactly as
    before: a factor pushed toward "critical" increasingly dominates the
    primary sort key (full override once fully critical, matching several
    factors' average the way multiple "critical" tiers used to), while the
    overall weighted blend (used for the displayed score, and to break ties)
    still runs across every factor, continuously weighted by position, with
    "does not matter" excluding a factor entirely.
    """
    normalized_by_factor = {
        factor: _normalize([e[factor] for e in estimates], LOWER_IS_BETTER[factor])
        for factor in FACTORS
    }

    weights = {f: _weight_for_position(tiers.get(f, DEFAULT_WEIGHT_POSITION)) for f in FACTORS}
    total_weight = sum(weights.values()) or 1

    criticality = {f: _criticality(tiers.get(f, DEFAULT_WEIGHT_POSITION)) for f in FACTORS}
    total_criticality = sum(criticality.values())

    for i, estimate in enumerate(estimates):
        overall = sum(weights[f] * normalized_by_factor[f][i] for f in FACTORS)
        estimate["score"] = round(100 * overall / total_weight, 1)
        estimate["_critical_score"] = (
            sum(criticality[f] * normalized_by_factor[f][i] for f in FACTORS) / total_criticality
            if total_criticality > 0
            else 0.0
        )

    ranked = sorted(estimates, key=lambda e: (e["_critical_score"], e["score"]), reverse=True)
    for estimate in ranked:
        del estimate["_critical_score"]
    return ranked
