"""Definitions for every way home RYDESAVYR knows how to compare.

Prices, speeds, and impact numbers below are reasonable NYC approximations,
not live quotes. Uber, Lyft, and Zipcar don't offer open fare APIs, and
Curb has no public API at all (see README), so estimates here are computed
from typical published rate cards instead of scraping or logging into any
account. Swap in a real API call inside `Mode.estimate` for any mode once
you have access to one.
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
    morality: float          # 0-10, higher = safer/more ethical
    notes: str = field(default="")

    def estimate(self, distance_miles: float) -> dict:
        route_miles = distance_miles * self.route_factor
        travel_minutes = (route_miles / self.avg_speed_mph) * 60
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
            "morality": self.morality,
            "notes": self.notes,
        }


MODES = [
    Mode(
        "uber", "Uber (UberX)", avg_speed_mph=18, route_factor=1.3, base_fare=3.00,
        cost_per_mile=1.75, cost_per_minute=0.35, wait_minutes=5,
        energy_cost=1, nature_vibez=2, carbon_g_per_mile=404, morality=6,
        notes="Estimated from typical NYC UberX rates, not a live quote.",
    ),
    Mode(
        "lyft", "Lyft", avg_speed_mph=18, route_factor=1.3, base_fare=2.75,
        cost_per_mile=1.70, cost_per_minute=0.32, wait_minutes=5,
        energy_cost=1, nature_vibez=2, carbon_g_per_mile=404, morality=6,
        notes="Estimated from typical NYC Lyft rates, not a live quote.",
    ),
    Mode(
        "citibike", "Citibike", avg_speed_mph=8, route_factor=1.2, base_fare=4.79,
        cost_per_mile=0, cost_per_minute=0, wait_minutes=3,
        energy_cost=7, nature_vibez=8, carbon_g_per_mile=0, morality=9,
        notes="Single-ride classic-bike price; assumes the trip fits the 30-minute window.",
    ),
    Mode(
        "subway", "Subway", avg_speed_mph=17, route_factor=1.4, base_fare=2.90,
        cost_per_mile=0, cost_per_minute=0, wait_minutes=6,
        energy_cost=3, nature_vibez=3, carbon_g_per_mile=90, morality=9,
        notes="Flat MTA fare; wait time approximates average headway.",
    ),
    Mode(
        "bus", "Bus", avg_speed_mph=8, route_factor=1.3, base_fare=2.90,
        cost_per_mile=0, cost_per_minute=0, wait_minutes=8,
        energy_cost=3, nature_vibez=3, carbon_g_per_mile=150, morality=9,
        notes="Flat MTA fare; slower average speed due to street traffic.",
    ),
    Mode(
        "train", "Commuter Train (LIRR / Metro-North)", avg_speed_mph=40, route_factor=1.1,
        base_fare=7.00, cost_per_mile=0.25, cost_per_minute=0, wait_minutes=15,
        energy_cost=2, nature_vibez=4, carbon_g_per_mile=120, morality=9,
        notes="Rough estimate for trips beyond the subway network; fares vary a lot by zone.",
    ),
    Mode(
        "walk", "Walking", avg_speed_mph=3, route_factor=1.2, base_fare=0,
        cost_per_mile=0, cost_per_minute=0, wait_minutes=0,
        energy_cost=9, nature_vibez=6, carbon_g_per_mile=0, morality=10,
        notes="Free and healthy, but slow and physically demanding over long distances.",
    ),
    Mode(
        "taxi", "Taxi (Curb / yellow cab)", avg_speed_mph=15, route_factor=1.3, base_fare=3.00,
        cost_per_mile=2.80, cost_per_minute=0.50, wait_minutes=5,
        energy_cost=1, nature_vibez=2, carbon_g_per_mile=404, morality=6,
        notes="Approximated from the NYC TLC rate card; Curb has no public fare API.",
    ),
    Mode(
        "zipcar", "Zipcar", avg_speed_mph=20, route_factor=1.3, base_fare=12.00,
        cost_per_mile=0.45, cost_per_minute=0, wait_minutes=10,
        energy_cost=4, nature_vibez=3, carbon_g_per_mile=350, morality=6,
        notes="Assumes a 1-hour minimum booking; most NYC Zipcars must return to their "
              "home spot, so this is a rough one-way approximation.",
    ),
]
