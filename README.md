# RYDESAVYR

A small Flask web app that estimates every way home (rideshare, taxi, transit,
biking, walking) for a trip and ranks them by whatever the user cares about
most — price, time, distance, personal energy, scenery ("nature-vibez"), and
carbon footprint. See `proposal.md` for the full project background.

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
matter" / "neutral" / "critical"); any factor marked "critical" becomes the
primary sort key. Geocoding uses OpenStreetMap's free Nominatim service
(`geocode.py`), which also powers the From/To address autocomplete.

**Citibike (`citibike.py`), the subway (`mta_subway.py`), the bus
(`mta_bus.py`), and Uber (`uber_client.py`) are the exceptions** — they pull
live data instead of using the formula. See below.

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

## Live Uber pricing (needs Uber's approval — not actually self-serve)

The OAuth "Log in with Uber" login flow is wired up end-to-end
(`uber_client.py` + the `/uber/*` routes in `app.py`), but **as of testing
this in September 2026, Uber's dashboard blocks it**: a freshly-created app
gets `invalid_scope` when requesting the `request` scope, and the Access
Token tab says plainly:

> Your application currently does not have access to Authorization Code
> scopes. Please contact your Uber business development representative or
> Uber point of contact to request access.

So despite what older docs/SDK fragments suggested, this scope is gated
behind an actual Uber Business Development relationship — the same as
Lyft and Curb (see below). If you get that access in the future:

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

Without `UBER_CLIENT_ID`/`UBER_CLIENT_SECRET` set, or if Uber rejects the
scope, this fails safe and Uber falls back to the same rate-card formula
as every other mode — nothing else breaks.

`uber_client.py` reconstructs the live-estimate response shape from Uber's
official Python SDK and cached doc fragments, since developer.uber.com's
docs are JavaScript-rendered and couldn't be fully verified here — if a
field comes back missing or renamed once real access is granted, adjust
`get_live_estimate` in that file.

## Why rate cards for pricing

There's no live-quote API available for most of these services (see below),
so each mode in `modes.py` is a simple formula: a rate card (base fare + cost
per mile/minute) applied to the real route distance and time (or, without a
Google Maps key, to an average NYC speed and route-directness factor over the
straight-line distance). Energy, scenery, and carbon are fixed per-mode
scores that are easy to tune in `modes.py`. `scoring.py` normalizes every
factor 0-1 across the candidate modes and combines them using the user's
per-factor importance tiers ("does not matter" / "neutral" / "critical").

Citibike (`citibike.py`), the subway (`mta_subway.py`), the bus
(`mta_bus.py`), and Uber (`uber_client.py`) are the exceptions — they pull
live data instead of using the formula. See below.

The **Columbia Evening Shuttle** (`columbia_shuttle.py`) is a further
special case: a free, evening-only shared van that Via operates for
Columbia. It only shows up when the trip both starts and ends inside the
Columbia coverage area *and* falls within that night's service window
(a month-dependent start time until 3 a.m.), so there is no rate-card
fallback — it simply isn't offered otherwise.

## Live route map

The results page shows a Leaflet map (`templates/results.html`) with the
origin and destination pinned. Clicking a row draws that mode's route:

- **Uber / Lyft / Taxi / Columbia Evening Shuttle** — a real driving route
  from a free, no-API-key OSRM instance
  (`routing.openstreetmap.de/routed-car`).
- **Citibike** — a real cycling route from that same OSRM project's
  bike-profile instance (`routed-bike`).
- **Walking** — a real walking route from its foot-profile instance
  (`routed-foot`).
- **Subway / bus / commuter rail** — no free live transit-routing API exists,
  so these show the straight-line distance they're already estimated from
  (see above), thickened to make clear it's the selected route.

Each mode in `modes.py` (and the live `citibike.py` / `mta_subway.py` /
`mta_bus.py` / `columbia_shuttle.py` results) carries a `route_profile`
field saying which of these it uses. Note that the public
`router.project-osrm.org` demo server quietly returns the *car* route no
matter which profile name you ask it for — the map deliberately uses
`routing.openstreetmap.de` instead, which runs genuinely separate
car/bike/foot engines.

## Why formulas instead of live APIs

- **Subway**: live "next train" wait times come from MTA's free
  GTFS-realtime feeds (`mta_subway.py`); the reported time is door-to-door
  (walk to the nearest station + live wait + ride + walk from the
  destination station), with the two walking legs and the between-stations
  ride portion still estimated from the straight-line formula.
- **Bus**: live "next bus" wait times come from MTA Bus Time's SIRI feed
  (`mta_bus.py`, free `MTA_BUS_API_KEY`); the ride portion still uses the
  formula.
- **Commuter rail**: MTA GTFS-realtime feeds exist and are the natural next
  upgrade — swap the relevant `Mode.estimate()` call for a real API request.
- **Citibike**: live pricing and station availability are wired up via the
  GBFS feed — see `citibike.py`.
- **Columbia Evening Shuttle**: there is no public Via API (their developer
  program is partnership-gated and undocumented) and Columbia publishes no
  feed, so the estimate is a formula built on the shuttle's published rules
  — free fare, geofenced coverage area, month-aware hours.
  `columbia_shuttle.py` has a `get_live_estimate` stub for the day access
  is granted, same as `uber_client.py`.
- **Uber**: OAuth login is wired up, but Uber currently rejects the
  `request` scope for a freshly-created app — see "Live Uber pricing"
  above. Gated behind Business Development, same as Lyft/Curb.
- **Lyft**: its public developer portal has stopped onboarding new apps, so
  this stays formula-based for now.
- **Curb**: no public API at all; folded into the "Taxi" line item using the
  published NYC TLC rate card instead.
- **MTA (subway / bus / commuter rail)**: flat published fares, so no API is
  needed for price.
- **Empower**: intentionally excluded — the NYC TLC has publicly declared it
  an unlicensed rideshare app, so it's left out rather than integrated.

## Next steps

- Extend the live MTA GTFS-realtime integration from subway and bus to
  commuter-rail arrival times.
- Cache Routes API responses so re-ranking the same trip (e.g. after moving a
  slider) doesn't re-hit the API.
- Persist a saved "home" address per user instead of typing it every time.
- Contact Uber Business Development to request `request`-scope access for
  live Uber pricing (see "Live Uber pricing" above), and apply for Lyft
  partner API access if live fare quotes become available again.
