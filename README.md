# RYDESAVYR

A small Flask web app that estimates every way home (rideshare, taxi, transit,
biking, walking, car share) for a trip and ranks them by whatever the user
cares about most — price, time, distance, personal energy, scenery
("nature-vibez"), carbon footprint, and morality. See `proposal.md` for the
full project background.

## Running it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then paste your Google Maps key into .env
python app.py
```

Then open http://127.0.0.1:5000.

The app runs without a key — it just falls back to rate-card estimates for
distance and time (see below).

## Google Maps setup

Distance and travel time come from the Google Maps **Routes API**
(`directions.py`). To enable it:

1. In the [Google Cloud console](https://console.cloud.google.com/), create a
   project and enable **Routes API** under *APIs & Services*.
2. Turn on billing for the project (the Routes API has a monthly free tier but
   requires a billing account).
3. Create an API key under *Credentials* and put it in `.env`:
   `GOOGLE_MAPS_API_KEY=...`

Each ranked trip makes one Routes API request per travel mode (driving,
bicycling, walking, and one transit request each for subway, bus, and
commuter rail).

## How estimates are computed

- **Distance and travel time**: the Google Maps Routes API when a key is set.
  Every mode in `modes.py` declares a `google_mode`
  (`driving` → Uber/Lyft/Taxi, `bicycling` → Citibike,
  `walking` → Walking, and `transit_subway` / `transit_bus` / `transit_rail`
  for the three transit modes — the transit variants use the Routes API's
  `transitPreferences.allowedTravelModes` so "Subway" and "Bus" resolve to
  genuinely different routes). Rows using live data are marked **live** in
  the results table. Without a key, each mode falls back to a formula: an
  average NYC speed and a route-directness factor applied to the straight-line
  distance between the two geocoded addresses.
- **Price**: still a rate card per mode (base fare + cost per mile/minute),
  applied to the real route distance and time. No provider offers an open
  fare API (see below).
- **Energy, nature-vibez, carbon, morality**: fixed per-mode scores, easy to
  tune in `modes.py`.

`scoring.py` normalizes every factor 0-1 across the candidate modes and
combines them using the user's slider weights. Geocoding for the fallback
distance uses OpenStreetMap's free Nominatim service (`geocode.py`).

## Why rate cards for pricing

- **Uber, Lyft**: fare-estimate APIs exist but require Uber/Lyft business
  approval, not self-serve signup.
- **Curb**: no public API at all; folded into the "Taxi" line item using the
  published NYC TLC rate card instead.
- **MTA / Citibike**: flat published fares, so no API needed for price.
- **Empower**: intentionally excluded — the NYC TLC has publicly declared it
  an unlicensed rideshare app, so it's left out rather than integrated.

## Next steps

- Swap in MTA GTFS-realtime for live subway/bus arrival times.
- Swap in Citibike's GBFS feed for live station/bike availability.
- Cache Routes API responses so re-ranking the same trip (e.g. after moving a
  slider) doesn't re-hit the API.
- Persist a saved "home" address per user instead of typing it every time.
- Apply for Uber/Lyft partner API access if live fare quotes become worth
  the integration cost.
