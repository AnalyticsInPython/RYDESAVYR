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

## How estimates are computed

There's no live-quote API available for most of these services (see below),
so each mode in `modes.py` is a simple formula: a rate card (base fare + cost
per mile/minute), an average NYC speed, and a route-directness factor applied
to the straight-line distance between the two geocoded addresses. Energy,
scenery, and carbon are fixed per-mode scores that are easy to
tune in `modes.py`. `scoring.py` normalizes every factor 0-1 across the
candidate modes and combines them using the user's slider weights.

Geocoding uses OpenStreetMap's free Nominatim service (`geocode.py`) — no API
key required.

## Why formulas instead of live APIs

- **Subway, bus, commuter rail, Citibike**: real free/open APIs exist (MTA
  GTFS-realtime, Citibike GBFS) and are the natural next upgrade — swap the
  relevant `Mode.estimate()` call for a real API request.
- **Uber, Lyft**: fare-estimate APIs exist but require Uber/Lyft business
  approval, not self-serve signup.
- **Zipcar**: has a partner API, gated behind an approval email.
- **Curb**: no public API at all; folded into the "Taxi" line item using the
  published NYC TLC rate card instead.
- **Empower**: intentionally excluded — the NYC TLC has publicly declared it
  an unlicensed rideshare app, so it's left out rather than integrated.

## Next steps

- Swap in MTA GTFS-realtime for live subway/bus arrival times.
- Swap in Citibike's GBFS feed for live station/bike availability.
- Persist a saved "home" address per user instead of typing it every time.
- Apply for Uber/Lyft/Zipcar partner API access if live quotes become worth
  the integration cost.
