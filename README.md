# RYDESAVYR

A small Flask web app that estimates every way home (rideshare, taxi, transit,
biking, walking) for a trip and ranks them by whatever the user
cares about most — price, time, distance, personal energy, scenery
("nature-vibez"), and carbon footprint. See `proposal.md` for the
full project background.

## Running it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5050.

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

## How estimates are computed

There's no live-quote API available for most of these services (see below),
so each mode in `modes.py` is a simple formula: a rate card (base fare + cost
per mile/minute), an average NYC speed, and a route-directness factor applied
to the straight-line distance between the two geocoded addresses. Energy,
scenery, and carbon are fixed per-mode scores that are easy to tune in
`modes.py`. `scoring.py` normalizes every factor 0-1 across the candidate
modes and combines them using the user's per-factor importance tiers ("does
not matter" / "neutral" / "critical").

Citibike (`citibike.py`) and Uber (`uber_client.py`) are the two exceptions —
they pull live data instead of using the formula. See below.

Geocoding uses OpenStreetMap's free Nominatim service (`geocode.py`) — no API
key required.

## Live route map

The results page shows a Leaflet map (`templates/index.html`) with the
origin and destination pinned. Clicking a row draws that mode's route:

- **Uber / Lyft / Taxi** — a real driving route from a free, no-API-key OSRM
  instance (`routing.openstreetmap.de/routed-car`).
- **Citibike** — a real cycling route from that same OSRM project's
  bike-profile instance (`routed-bike`).
- **Walking** — a real walking route from its foot-profile instance
  (`routed-foot`).
- **Subway / bus / commuter rail** — no free live transit-routing API exists,
  so these show the straight-line distance they're already estimated from
  (see above), thickened to make clear it's the selected route.

Each mode in `modes.py` (and the live `citibike.py`/`mta_subway.py`/
`mta_bus.py` results) carries a `route_profile` field saying which of these
it uses. Note that the public `router.project-osrm.org` demo server quietly
returns the *car* route no matter which profile name you ask it for — the
map deliberately uses `routing.openstreetmap.de` instead, which runs
genuinely separate car/bike/foot engines.

## Why formulas instead of live APIs

- **Subway, bus, commuter rail**: real free/open MTA GTFS-realtime APIs
  exist and are the natural next upgrade — swap the relevant
  `Mode.estimate()` call for a real API request.
- **Citibike**: live pricing is already wired up via the GBFS feed —
  see `citibike.py`.
- **Uber**: OAuth login is wired up, but Uber currently rejects the
  `request` scope for a freshly-created app — see "Live Uber pricing"
  above. Gated behind Business Development, same as Lyft/Curb.
- **Lyft**: its public developer portal has stopped onboarding new apps, so
  this stays formula-based for now.
- **Curb**: no public API at all; folded into the "Taxi" line item using the
  published NYC TLC rate card instead.
- **Empower**: intentionally excluded — the NYC TLC has publicly declared it
  an unlicensed rideshare app, so it's left out rather than integrated.

## Next steps

- Swap in MTA GTFS-realtime for live subway/bus arrival times.
- Persist a saved "home" address per user instead of typing it every time.
- Contact Uber Business Development to request `request`-scope access for
  live Uber pricing (see "Live Uber pricing" above); apply for a Lyft
  partner API too if live quotes become worth the integration cost.
