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

## How estimates are computed

There's no live-quote API available for Uber, Lyft, or Taxi (see below), so
each of those is a rate-card formula in `modes.py`: base fare + cost/mile +
cost/minute, applied to a distance and travel time. Energy, scenery, and
carbon are fixed per-mode scores that are easy to tune in `modes.py`.
`scoring.py` normalizes every factor 0-1 across the candidate modes and
combines them using the user's per-factor importance tiers ("does not
matter" / "neutral" / "critical").

For the driving-based modes -- Uber, Lyft, Taxi -- that distance/time comes
from a real road-network route via `routing.py` (OSRM's free public demo
server, no key needed), not a straight-line-distance guess. Every other mode
(Walking, Subway, Bus, Commuter Train) still uses the older straight-line x
route-directness-factor approximation, since OSRM's public demo only
actually routes cars -- see `routing.py`'s docstring for how that was
confirmed. This is separate from the results-page map's routing (see "Live
route map" below), which is purely visual and doesn't feed back into these
numbers.

Citibike (`citibike.py`), Subway (`mta_subway.py`), and Bus (`mta_bus.py`,
once a key is configured) are the exceptions that pull live *pricing* data
instead of using a rate-card formula at all.

Geocoding uses OpenStreetMap's free Nominatim service (`geocode.py`) — no API
key required.

## How the Uber/Lyft rate cards were built

Rather than guess "typical" numbers, `modes.py`'s Uber and Lyft `base_fare`/
`cost_per_mile`/`cost_per_minute` are fit by linear regression against NYC
TLC's official historical **High Volume For-Hire Vehicle trip data**
(`fhvhv_tripdata_2026-05.parquet` from
nyc.gov/site/tlc/about/tlc-trip-record-data.page — the same dataset every
serious NYC-taxi analysis project uses, e.g.
github.com/toddwschneider/nyc-taxi-data).

Method: queried ~130k solo (non-shared) Uber trips and ~60k solo Lyft trips
(0.3-30 miles, 1-90 minutes) directly from the remote Parquet file via
DuckDB's `httpfs` extension (no full-file download needed — Parquet's
columnar format means only the ~10 needed columns get fetched). Regressed
each company's rider-mandatory total (`base_passenger_fare` + tolls + BCF +
sales tax + congestion surcharges, tips excluded — same convention as Taxi
below) against `trip_miles` and `trip_time`, then dropped the ~3% of trips
with the largest residuals (surge-priced outliers a 2-feature linear model
has no way to explain) and refit.

Result: **Uber** R²=0.81, MAE $7.65 against an average $31.69 fare; **Lyft**
R²=0.90, MAE $4.96 against an average $29.73 fare. The remaining error is
real demand-based surge pricing, which this kind of model can't capture
without a live signal — not a bug in the fit. Both companies' `avg_speed_mph`
values are this same sample's actual average speed, used only if live
routing (`routing.py`) is unavailable.

This replaced hand-guessed constants that were meaningfully off — the old
Uber formula estimated **$18.07** for the sample's average trip vs. the
$31.69 riders actually paid.

To refit against a newer month: swap the URL in the query for a more recent
`fhvhv_tripdata_YYYY-MM.parquet`, rerun the regression, and update the four
constants (`base_fare`, `cost_per_mile`, `cost_per_minute`, `avg_speed_mph`)
per company in `modes.py`.

## Why there's no live Uber/Lyft/Taxi pricing

An OAuth "Log in with Uber" flow was built and tested here, but **as of
September 2026, Uber's dashboard blocks it for a freshly-created app**:
requesting the `request` scope returns `invalid_scope`, and the Access
Token tab says plainly:

> Your application currently does not have access to Authorization Code
> scopes. Please contact your Uber business development representative or
> Uber point of contact to request access.

So despite what older docs/SDK fragments suggested, that scope is gated
behind an actual Uber Business Development relationship — the same as Lyft.
Not something a hobby project can get self-serve, so that OAuth code
(`uber_client.py`, the `/uber/*` routes, the "Log in with Uber" button) was
removed rather than left dead in the tree; Uber uses the rate-card formula
described above instead.

A live Taxi integration via the TaxiFareFinder API was also built and then
abandoned on purpose: getting a key requires a manual, human-reviewed
request (`taxifarefinder.com/contactus.php`), and once the Uber/Lyft rate
cards above were empirically fit against real trip data, the accuracy gap
that would have justified waiting on that approval mostly closed. Taxi's
formula (in `modes.py`, verified against the NYC TLC's published rate card:
$3.00 initial charge + $3.50/mile + the $0.50 MTA and $1.00 improvement
surcharges that apply to nearly every ride) is judged good enough on its
own. If a live quote is wanted again later, TaxiFareFinder's API (documented
in earlier project history) is the place to pick that back up.

## Live route map

The results page shows a Google Map (`templates/index.html`, Maps
JavaScript API) with the origin and destination pinned. Clicking a row
calls the newer Routes API (`routes.googleapis.com`, not the older
"Directions API") for that mode's real route and draws it by decoding
the returned polyline with the Maps JavaScript API's `geometry` library:

- **Uber / Lyft / Taxi** — a live `DRIVE` route.
- **Citibike** — a live `BICYCLE` route.
- **Walking** — a live `WALK` route.
- **Subway / bus / commuter rail** — a live `TRANSIT` route, restricted via
  `transitPreferences.allowedTravelModes` to that specific vehicle type
  (`SUBWAY`, `BUS`, or `TRAIN`/`RAIL`) so the three don't just show
  Google's one "best" transit itinerary three times over. That
  restriction is a hint, not a guarantee — Google falls back to its own
  best multimodal route rather than erroring when no matching itinerary
  exists, so the three can still occasionally coincide.

Each mode in `modes.py` (and the live `citibike.py`/`mta_subway.py`/
`mta_bus.py` results) carries a `route_profile` field saying which of these
travel modes it uses. This map is purely visual — it doesn't feed back into
the price/time/distance numbers in the results table (see "How estimates
are computed" above for what does).

Requires `GOOGLE_MAPS_API_KEY` in `.env` with the **Maps JavaScript API**
and **Routes API** enabled on that key's project (see `.env.example`) —
without the key set at all, the map is just hidden and nothing else
breaks; without the Routes API specifically enabled, the map loads but
every route request fails and falls back to the "unavailable" status
message.

## Why formulas instead of live APIs

- **Uber/Lyft**: formula-based, now fit against real historical trip data —
  see "How the Uber/Lyft rate cards were built" above.
- **Curb/Taxi**: no public API at all; the TaxiFareFinder integration was
  tried and abandoned (see above) — formula-based, verified against the
  official TLC rate card.
- **Subway**: live next-train wait times come from MTA's free, keyless
  GTFS-realtime feeds — see `mta_subway.py`.
- **Bus**: live next-bus wait times come from MTA Bus Time's SIRI API (needs
  a free `MTA_BUS_API_KEY`) — see `mta_bus.py`.
- **Commuter rail**: no free live-arrival API found yet for LIRR/Metro-North;
  still formula-based.
- **Citibike**: live pricing is already wired up via the GBFS feed — see
  `citibike.py`.
- **Empower**: intentionally excluded — the NYC TLC has publicly declared it
  an unlicensed rideshare app, so it's left out rather than integrated.

## Next steps

- Find a live-arrival source for commuter rail (LIRR/Metro-North) to match
  Subway and Bus.
- Persist a saved "home" address per user instead of typing it every time.
- Periodically refit the Uber/Lyft constants against a newer month's TLC
  data so they don't go stale the way the old guessed numbers did (see "How
  the Uber/Lyft rate cards were built" above).
- `routing.py` (the server-side price/time calculation for Uber/Lyft/Taxi)
  currently points at OSRM's public demo server, which isn't meant for
  production traffic (no uptime/rate-limit guarantees) -- fine for now, but
  swap in a self-hosted OSRM instance or a keyed provider like
  OpenRouteService if this ever needs to be reliable under real usage.
