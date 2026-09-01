"""Definitions for every way home RYDESAVYR knows how to compare.

Fares and impact numbers below (base fare, cost per mile/minute, carbon,
energy, scenery) are reasonable NYC approximations, not live quotes -- Uber
and Lyft don't offer open self-serve fare APIs and Curb has no public API at
all (see README). Live Uber pricing and live Citibike availability are
layered on in `app.py` when the user connects those services.

Route distance and travel time, however, come from the Google Maps Routes
API when a GOOGLE_MAPS_API_KEY is configured: each mode declares a
``google_mode`` and `Mode.estimate` uses the real route when ``route_info``
is passed in, falling back to the rate-card formula (avg speed + route
factor) otherwise.
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
    nature_vibez: float      # 0-10, higher = more pleasant/scenic (shown as "Scenery")
    carbon_g_per_mile: float
    # One of the keys in directions._TRAVEL_MODE: driving | bicycling | walking |
    # transit_subway | transit_bus | transit_rail.
    google_mode: str = "driving"
    notes: str = field(default="")

    def estimate(self, distance_miles: float, route_info: dict | None = None) -> dict:
        if route_info is not None:
            # Real route from the Google Maps Routes API.
            route_miles = route_info["distance_miles"]
            travel_minutes = route_info["duration_minutes"]
            live = True
        else:
            # Rate-card fallback: scale straight-line distance, apply avg speed.
            route_miles = distance_miles * self.route_factor
            travel_minutes = (route_miles / self.avg_speed_mph) * 60
            live = False

        if live and self.google_mode.startswith("transit"):
            # Transit duration from Google already includes walking + waiting
            # for the vehicle, so don't add the headway estimate on top.
            total_minutes = travel_minutes
        else:
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
            "live": live,
            "notes": self.notes,
        }


MODES = [
    Mode(
        "uber", "Uber (UberX)", avg_speed_mph=18, route_factor=1.3, base_fare=3.00,
        cost_per_mile=1.75, cost_per_minute=0.35, wait_minutes=5,
        energy_cost=1, nature_vibez=2, carbon_g_per_mile=404,
        google_mode="driving",
        notes="Fare estimated from typical NYC UberX rates (unless you connect "
              "Uber for a live price); distance and drive time from Google Maps.",
    ),
    Mode(
        "lyft", "Lyft", avg_speed_mph=18, route_factor=1.3, base_fare=2.75,
        cost_per_mile=1.70, cost_per_minute=0.32, wait_minutes=5,
        energy_cost=1, nature_vibez=2, carbon_g_per_mile=404,
        google_mode="driving",
        notes="Fare estimated from typical NYC Lyft rates; distance and drive "
              "time from Google Maps.",
    ),
    Mode(
        "citibike", "Citibike", avg_speed_mph=8, route_factor=1.2, base_fare=4.79,
        cost_per_mile=0, cost_per_minute=0, wait_minutes=3,
        energy_cost=7, nature_vibez=8, carbon_g_per_mile=0,
        google_mode="bicycling",
        notes="Single-ride classic-bike price; bike route and time from Google Maps. "
              "Assumes the trip fits the 30-minute window.",
    ),
    Mode(
        "subway", "Subway", avg_speed_mph=17, route_factor=1.4, base_fare=2.90,
        cost_per_mile=0, cost_per_minute=0, wait_minutes=6,
        energy_cost=3, nature_vibez=3, carbon_g_per_mile=90,
        google_mode="transit_subway",
        notes="Flat MTA fare; route and door-to-door time (walk + wait + ride) "
              "from Google Maps transit directions (rail only).",
    ),
    Mode(
        "bus", "Bus", avg_speed_mph=8, route_factor=1.3, base_fare=2.90,
        cost_per_mile=0, cost_per_minute=0, wait_minutes=8,
        energy_cost=3, nature_vibez=3, carbon_g_per_mile=150,
        google_mode="transit_bus",
        notes="Flat MTA fare; bus route and door-to-door time from Google Maps "
              "transit directions (buses only).",
    ),
    Mode(
        "train", "Commuter Train (LIRR / Metro-North)", avg_speed_mph=40, route_factor=1.1,
        base_fare=7.00, cost_per_mile=0.25, cost_per_minute=0, wait_minutes=15,
        energy_cost=2, nature_vibez=4, carbon_g_per_mile=120,
        google_mode="transit_rail",
        notes="Fare is a rough zone estimate; route and door-to-door time from "
              "Google Maps transit directions (commuter rail only).",
    ),
    Mode(
        "walk", "Walking", avg_speed_mph=3, route_factor=1.2, base_fare=0,
        cost_per_mile=0, cost_per_minute=0, wait_minutes=0,
        energy_cost=9, nature_vibez=6, carbon_g_per_mile=0,
        google_mode="walking",
        notes="Free and healthy, but slow over long distances; walking route and "
              "time from Google Maps.",
    ),
    Mode(
        "taxi", "Taxi (Curb / yellow cab)", avg_speed_mph=15, route_factor=1.3, base_fare=3.00,
        cost_per_mile=2.80, cost_per_minute=0.50, wait_minutes=5,
        energy_cost=1, nature_vibez=2, carbon_g_per_mile=404,
        google_mode="driving",
        notes="Fare from the NYC TLC rate card (Curb has no public fare API); "
              "distance and drive time from Google Maps.",
    ),
]
