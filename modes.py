"""Definitions for every way home RYDESAVYR knows how to compare.

Prices, speeds, and impact numbers below are reasonable NYC approximations,
not live quotes, except Uber/Lyft (see their entries below, fit against real
historical trip data). Curb has no public API at all (see README), so Taxi
is computed from the published NYC TLC rate card instead of a live quote.

For the driving-based modes (Uber, Lyft, Taxi), app.py prefers
`estimate_from_route` with a real road-network distance/time from
routing.py over `estimate`'s straight-line x route_factor guess -- see
routing.py's docstring for why only those modes get that treatment. This is
separate from `route_profile` below, which only controls which travel mode
draws this mode's line on the results-page map.
"""

from dataclasses import dataclass, field


@dataclass
class Mode:
    key: str
    label: str
    avg_speed_mph: float
    route_factor: float  # actual route distance vs. straight-line distance
    base_fare: float
    cost_per_mile: float
    cost_per_minute: float
    wait_minutes: float
    energy_cost: float       # 0-10, higher = more personal effort/battery drain
    nature_vibez: float      # 0-10, higher = more pleasant/scenic
    carbon_g_per_mile: float
    notes: str = field(default="")
    # Which routing engine (see templates/index.html) draws this mode's
    # line on the results map: "driving", "cycling", "walking", or
    # "transit" (the default, for subway/bus/commuter rail, which has no
    # live routing available and falls back to the straight-line estimate).
    route_profile: str = field(default="transit")

    def _priced(self, route_miles: float, travel_minutes: float) -> dict:
        total_minutes = travel_minutes + self.wait_minutes
        price = self.base_fare + self.cost_per_mile * route_miles + self.cost_per_minute * travel_minutes
        carbon = self.carbon_g_per_mile * route_miles
        return {
            "key": self.key,
            "label": self.label,
            "distance": round(route_miles, 2),
            "time": round(total_minutes, 1),
            "price": round(price, 2),
            "energy": self.energy_cost,
            "nature_vibez": self.nature_vibez,
            "carbon": round(carbon),
            "notes": self.notes,
            "route_profile": self.route_profile,
        }

    def estimate(self, distance_miles: float) -> dict:
        """Straight-line distance x this mode's route_factor fudge --
        used when no real routing data is available."""
        route_miles = distance_miles * self.route_factor
        travel_minutes = (route_miles / self.avg_speed_mph) * 60
        return self._priced(route_miles, travel_minutes)

    def estimate_from_route(self, route_miles: float, travel_minutes: float) -> dict:
        """Real routed distance/time (from routing.py) -- no route_factor
        fudge applied, since this is an actual road-network route already."""
        return self._priced(route_miles, travel_minutes)


MODES = [
    Mode(
        # Fit by linear regression against NYC TLC's official historical High
        # Volume For-Hire Vehicle trip data (fhvhv_tripdata_2026-05.parquet,
        # hvfhs_license_num=HV0003 -- see nyc.gov/site/tlc/about/
        # tlc-trip-record-data.page), not guessed. Target = rider-mandatory
        # total (base_passenger_fare + tolls + bcf + sales_tax +
        # congestion_surcharge + airport_fee + cbd_congestion_fee, tips
        # excluded -- same convention as Taxi below), regressed against
        # trip_miles and trip_time. Solo (non-shared) rides only,
        # 0.3-30 miles, 1-90 minutes: n=133,475 sampled trips, then a second
        # pass dropping the ~3% with the largest residuals (surge-priced
        # outliers a 2-feature linear model can't explain) -> n=129,287,
        # R^2=0.81, MAE=$7.65 against an average $31.69 fare -- the
        # remaining error is real demand-based surge pricing this model has
        # no signal for, not sloppiness. avg_speed_mph is this same trimmed
        # sample's actual average speed (miles / trip_time), used only when
        # live routing (routing.py) is unavailable.
        "uber", "Uber (UberX)", avg_speed_mph=12.7, route_factor=1.3, base_fare=3.03,
        cost_per_mile=2.59, cost_per_minute=0.90, wait_minutes=5,
        energy_cost=1, nature_vibez=2, carbon_g_per_mile=404,
        notes="Fit to NYC TLC's official historical Uber trip data (2026-05), not a live quote.",
        route_profile="driving",
    ),
    Mode(
        # Same methodology as Uber above, same source file, hvfhs_license_num
        # =HV0005: n=60,321 sampled trips -> n=58,667 after trimming, R^2=0.90,
        # MAE=$4.96 against an average $29.73 fare.
        "lyft", "Lyft", avg_speed_mph=12.8, route_factor=1.3, base_fare=3.06,
        cost_per_mile=2.62, cost_per_minute=0.78, wait_minutes=5,
        energy_cost=1, nature_vibez=2, carbon_g_per_mile=404,
        notes="Fit to NYC TLC's official historical Lyft trip data (2026-05), not a live quote.",
        route_profile="driving",
    ),
    Mode(
        "citibike", "Citibike", avg_speed_mph=8, route_factor=1.2, base_fare=4.79,
        cost_per_mile=0, cost_per_minute=0, wait_minutes=3,
        energy_cost=7, nature_vibez=8, carbon_g_per_mile=0,
        notes="Single-ride classic-bike price; assumes the trip fits the 30-minute window.",
        route_profile="cycling",
    ),
    Mode(
        "subway", "Subway", avg_speed_mph=17, route_factor=1.4, base_fare=2.90,
        cost_per_mile=0, cost_per_minute=0, wait_minutes=6,
        energy_cost=3, nature_vibez=3, carbon_g_per_mile=90,
        notes="Flat MTA fare; wait time approximates average headway.",
    ),
    Mode(
        "bus", "Bus", avg_speed_mph=8, route_factor=1.3, base_fare=2.90,
        cost_per_mile=0, cost_per_minute=0, wait_minutes=8,
        energy_cost=3, nature_vibez=3, carbon_g_per_mile=150,
        notes="Flat MTA fare; slower average speed due to street traffic.",
    ),
    Mode(
        "train", "Commuter Train (LIRR / Metro-North)", avg_speed_mph=40, route_factor=1.1,
        base_fare=7.00, cost_per_mile=0.25, cost_per_minute=0, wait_minutes=15,
        energy_cost=2, nature_vibez=4, carbon_g_per_mile=120,
        notes="Rough estimate for trips beyond the subway network; fares vary a lot by zone.",
    ),
    Mode(
        "walk", "Walking", avg_speed_mph=3, route_factor=1.2, base_fare=0,
        cost_per_mile=0, cost_per_minute=0, wait_minutes=0,
        energy_cost=9, nature_vibez=6, carbon_g_per_mile=0,
        notes="Free and healthy, but slow and physically demanding over long distances.",
        route_profile="walking",
    ),
    Mode(
        # Verified against the official rate card (nyc.gov/site/tlc/passengers/taxi-fare.page)
        # on 2026-09-02: $3.00 initial charge, $0.70/(1/5 mile) while moving above 12mph
        # (= $3.50/mile -- billed by distance OR by time when slow/stopped, never both, hence
        # cost_per_minute=0 below), plus two surcharges that apply to essentially every ride
        # regardless of distance: $0.50 MTA State Surcharge + $1.00 Improvement Surcharge,
        # folded into base_fare as 3.00 + 0.50 + 1.00 = 4.50.
        #
        # NOT modeled here, since Mode.estimate() only takes a distance and has no notion of
        # time-of-day or route geography: the $1.00 overnight surcharge (8pm-6am), $2.50 rush
        # hour surcharge (4-8pm weekdays), NY State Congestion Surcharge ($2.50 for any trip
        # touching Manhattan), tolls, and tip. Real fares can run $1-$6+ above this estimate
        # depending on when/where you're riding -- see the notes string below.
        "taxi", "Taxi", avg_speed_mph=15, route_factor=1.3, base_fare=4.50,
        cost_per_mile=3.50, cost_per_minute=0, wait_minutes=5,
        energy_cost=1, nature_vibez=2, carbon_g_per_mile=404,
        notes="Approximated from the NYC TLC rate card (base fare + mandatory surcharges); "
              "doesn't include time-of-day surcharges, tolls, or tip, which can add $1-$6+. "
              "Curb has no public fare API.",
        route_profile="driving",
    ),
]
