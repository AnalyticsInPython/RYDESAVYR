# RYDESAVYR

A small Flask web app that estimates every way home (rideshare, taxi, transit,
biking, walking, car share) for a trip and ranks them by whatever the user
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

Then open http://127.0.0.1:5000.

## Live Uber pricing (optional)

Uber's Rides API is self-serve for personal use — no business approval
needed until you want to go beyond yourself + 4 other registered
developers. To turn it on:

1. Sign in at https://developer.uber.com with your own Uber account and
   create an application (any API suite works).
2. Under the app's Authentication settings, add this exact redirect URI:
   `http://127.0.0.1:5000/uber/callback`
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

## How estimates are computed

There's no live-quote API available for most of these services (see below),
so each mode in `modes.py` is a simple formula: a rate card (base fare + cost
per mile/minute), an average NYC speed, and a route-directness factor applied
to the straight-line distance between the two geocoded addresses. Energy,
nature-vibez, and carbon are fixed per-mode scores that are easy to tune in
`modes.py`. `scoring.py` normalizes every factor 0-1 across the candidate
modes and combines them using the user's per-factor importance tiers ("does
not matter" / "neutral" / "critical").

Citibike (`citibike.py`) and Uber (`uber_client.py`) are the two exceptions —
they pull live data instead of using the formula. See below.

Geocoding uses OpenStreetMap's free Nominatim service (`geocode.py`) — no API
key required.

## Why formulas instead of live APIs

- **Subway, bus, commuter rail**: real free/open MTA GTFS-realtime APIs
  exist and are the natural next upgrade — swap the relevant
  `Mode.estimate()` call for a real API request.
- **Citibike**: live pricing is already wired up via the GBFS feed —
  see `citibike.py`.
- **Uber**: live pricing is now wired up — see "Live Uber pricing" above.
- **Lyft**: its public developer portal has stopped onboarding new apps, so
  this stays formula-based for now.
- **Zipcar**: has a partner API, gated behind an approval email.
- **Curb**: no public API at all; folded into the "Taxi" line item using the
  published NYC TLC rate card instead.
- **Empower**: intentionally excluded — the NYC TLC has publicly declared it
  an unlicensed rideshare app, so it's left out rather than integrated.

## Next steps

- Swap in MTA GTFS-realtime for live subway/bus arrival times.
- Persist a saved "home" address per user instead of typing it every time.
- Apply for Uber/Lyft/Zipcar partner API access if live quotes become worth
  the integration cost.
