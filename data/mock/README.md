# Mock world (task S6, owner C)

One command fills **every screen** of the mobile app and the web admin with one consistent, realistic
world. **All of it is synthetic**: simulated sensors, generated complaints, generated photos, fictional
people. Say so on stage.

```bash
docker compose up --build -d                       # database + API + web admin
docker compose --profile mock run --rm mock        # the mock world, ~2 minutes (first run)
# or, without Docker:  .venv/bin/python scripts/seed_world.py --api http://localhost:8000
#   --fast   smaller world (~1 minute)   --check   is everything there? (exit 1 if not)
docker compose down -v                             # wipe it, start again
```

Running it twice does nothing the second time. On a database that already holds other data
(e.g. `seed_demo.py`) it refuses; start clean with `docker compose down -v` (or pass `--force`).

**Needs** (in `.env`): `AUTH_DEV_LOGIN=1` (the Docker stack turns it on), `ADMIN_EMAILS` containing the
admin below (the seeder signs in as the first `ADMIN_EMAILS` entry), and `DEVICE_KEYS` for
`bus-MAR-01/02, bus-JER-01/02, bus-SWI-01/02, tram-17-01/02` (format in `.env.example`).

## Demo accounts

Everyone signs in with **demo sign-in** (`POST /auth/dev`, just the email, no password). In the mobile
app: Profile → Sign in → demo sign-in. Personas and their actions: [`personas.json`](personas.json).

| Email | Who | What you see when signed in |
|---|---|---|
| `admin@cityecho.test` | Urszula, ZDM dispatcher (**admin**) | Web admin: the whole queue, work status history, stats |
| `anna.kowalska@cityecho.test` | Reliable reporter | Highest trust (~0.8), 3 reports with photos; one is a pothole the buses had already found |
| `piotr.nowak@cityecho.test` | Commuter | 3 favourite routes (Marszałkowska, tram 17, Jerozolimskie) with "bad road ahead" warnings |
| `marek.zielinski@cityecho.test` | Unreliable | Lowest trust (~0.3): reported a pothole that isn't there (dismissed), answered wrongly |
| `olena.shevchenko@cityecho.test` | Newcomer, writes in Ukrainian | A fresh streetlight report waiting for a vehicle to check it |
| `james.miller@cityecho.test` | Expat, writes in English | Flooding report with photo, a saved bus line |
| `katarzyna.wojcik@cityecho.test` | Night-shift nurse | Streetlight reports (Plac Konstytucji, Rakowiecka) |
| `tomasz.lewandowski@cityecho.test` | Cyclist | Road damage with photos; one pothole the buses had already found |
| `zofia.dabrowska@cityecho.test` | Retiree | Reported subsidence that isn't there (dismissed) |

## What the world contains (full run)

| Area | Content |
|---|---|
| Complaints | ~370 citizen complaints over the last 14 days (19115 imports from `scripts/gen_complaints.py`, Polish with some English) + 13 app reports from the personas (7 with generated photos) |
| Sensors | 50 back-dated simulated bus and tram rides + 6 rides "now" (`scripts/simulate_buses.py`, ground truth `data/demo/sim_world.json`) |
| Road health | Fresh on Marszałkowska and Aleje Jerozolimskie (rides until today), **stale on Świętokrzyska** (last rides 11–12 days ago), tram 17 rails |
| Incidents | Every state: candidate, likely, verified, dismissed (2 false alarms), found before any report (~25), awaiting a vehicle (~8) |
| Citizen answers | ~23 "is it still there?" answers; trust settles when the city closes a job or an incident is dismissed |
| City work | 4 done (one repair is visible to the sensors), 3 in progress, the rest to do |
| Routes | 4 favourite routes |

Incident ids change from run to run; find them by place.

## On stage

**Mobile app**
1. Map, not signed in: road colours along Marszałkowska, Jerozolimskie and Świętokrzyska; pins across the city.
2. Sign in as **Piotr** → Routes: "Home → office (Marszałkowska)" shows the road quality and the problems ahead.
3. Sign in as **Anna** → Profile: high trust, her reports and their status ("the city is on it", "fixed").
4. Sign in as **Olena** → her streetlight report: a vehicle has been asked to check it.

**Web admin** (sign in as `admin@cityecho.test`)
1. Queue: filter by department / status / work status; the top is the **Marszałkowska × Świętokrzyska tram
   track** (40 reports, many sensor rides, verified, in progress).
2. Incident detail of that one: sensor signal, evidence timeline, citizen answers, confidence breakdown.
3. **Marszałkowska at Rondo Dmowskiego** pothole: verified, marked **done**, and the buses no longer feel it.
4. Filter **dismissed**: the two false alarms (Marszałkowska between Królewska and Świętokrzyska, Aleje
   Jerozolimskie west of Dworzec Centralny): citizens reported, buses drove over and felt nothing, truthful
   citizens said no.
5. Stats: funnel report → incident → verified → done, repair times, load per department, 14-day trend.

## How it stays one world

- Complaint spots a vehicle could confirm (potholes, track defects) that lie near a simulated line are pinned
  onto the line, at a simulated defect, so buses and trams confirm the citizens instead of counting clean
  passes against them (`snap_to_route_m`, `extra_defects` in [`world.json`](world.json)).
- The false alarms sit ≥ 200 m from any defect or complaint: there is nothing for the buses to feel.
- Mock complaints use only street / crossing phrases and neutral vague phrases ("pod blokiem"), so the geocoder
  keeps the citizen's pin. Even so, ~14 % of the 19115 complaints are moved by the triage's own geocoding
  (e.g. "na Modlińskiej przy Żeraniu" → the middle of Modlińska, 7 km away: the triage trusts a street-level
  geocode over a pin more than 1 km away). They land away from the simulated lines, so they stay open.

Plan files: [`world.json`](world.json) (rides, false alarms, answers, city work), [`personas.json`](personas.json).
