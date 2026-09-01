# RYDESAVYR

A small Flask web app that estimates every way home (rideshare, taxi, transit,
biking, walking) for a trip and ranks them by whatever the user cares about
most — price, time, distance, personal energy, scenery, and carbon footprint.
See `proposal.md` for the full project background.

## Running it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then paste your Google Maps key into .env
python app.py
```

Then open http://127.0.0.1:5050.

The app runs without any keys — it just falls back to rate-card estimates
for distance and time, and formula pricing for Uber.

## How estimates are computed

- **Distance and travel time**: the Google Maps Routes API when a
  `GOOGLE_MAPS_API_KEY` is set (see below). Each mode in `modes.py` declares a
  `google_mode` (`driving` → Uber/Lyft/Taxi, `bicycling` → Citibike,
  `walking` → Walking, and `transit_subway` / `transit_bus` / `transit_rail`
  for the three transit modes — the transit variants use the Routes API's
  `transitPreferences.allowedTravelModes` so "Subway" and "Bus" resolve to
  genuinely different routes). Rows using live data are marked **live** in the
  results table. Without a key, each mode falls back to a formula: an average
  NYC speed and a route-directness factor applied to the straight-line
  distance between the two geocoded addresses.
- **Price**: a rate card per mode (base fare + cost per mile/minute), applied
  to the real route distance and time. See "Why rate cards for pricing" below.
- **Energy, scenery, carbon**: fixed per-mode scores, easy to tune in
  `modes.py`.

`scoring.py` normalizes every factor 0-1 across the candidate modes and
combines them using the user's per-factor importance tiers ("does not
matter" / "neutral" / "critical"). Geocoding for the fallback distance uses
OpenStreetMap's free Nominatim service (`geocode.py`).

**Citibike (`citibike.py`) and Uber (`uber_client.py`) are the two
exceptions** — they pull live pricing instead of using the formula. See below.

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

## Live Uber pricing (optional)

Uber's Rides API is self-serve for personal use — no business approval
needed until you want to go beyond yourself + 4 other registered
developers. To turn it on:

1. Sign in at https://developer.uber.com with your own Uber account and
   create an application (any API suite works).
2. Under the app's Authentication settings, add this exact redirect URI:
   `http://127.0.0.1:5050/uber/callback`
3. Copy `.env.example` to `.env` and fill in `UBER_CLIENT_ID` /
   `UBER_CLIENT_SECRET` from that app.
4. Restart `python app.py`.

With those set, the first time anyone searches, RYDESAVYR automatically
redirects to Uber's own login page (no separate "connect account" step —
it's part of the same tap that starts the search, since most people will
be doing this one-handed on a phone). After they grant access, it bounces
back and shows a live UberX price/ETA instead of the formula estimate.
Nobody else's search can use it until Uber grants your app full production
access — until then it only works for accounts you've explicitly added as
developers on the app.

Without `UBER_CLIENT_ID`/`UBER_CLIENT_SECRET` set, this is skipped entirely
and Uber falls back to the same rate-card formula as every other mode.

`uber_client.py` reconstructs the live-estimate response shape from Uber's
official Python SDK and cached doc fragments, since developer.uber.com's
docs are JavaScript-rendered and couldn't be fully verified here — if a
field comes back missing or renamed once you test with a real account,
adjust `get_live_estimate` in that file.

## Why rate cards for pricing

- **Citibike**: live pricing is already wired up via the GBFS feed — see
  `citibike.py`.
- **Uber**: live pricing is wired up via OAuth — see "Live Uber pricing" above.
- **Lyft**: its public developer portal has stopped onboarding new apps, so
  this stays formula-based for now.
- **Curb**: no public API at all; folded into the "Taxi" line item using the
  published NYC TLC rate card instead.
- **MTA (subway / bus / commuter rail)**: flat published fares, so no API is
  needed for price.
- **Empower**: intentionally excluded — the NYC TLC has publicly declared it
  an unlicensed rideshare app, so it's left out rather than integrated.

## Next steps

- Swap in MTA GTFS-realtime for live subway/bus arrival times.
- Cache Routes API responses so re-ranking the same trip (e.g. after moving a
  slider) doesn't re-hit the API.
- Persist a saved "home" address per user instead of typing it every time.
- Apply for Lyft partner API access if live fare quotes become available again.
