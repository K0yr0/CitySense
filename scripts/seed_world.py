#!/usr/bin/env python
"""Whole-project mock world (S6): one command fills every screen of the mobile app and the web admin with
one consistent, realistic world, through the public HTTP API only (never SQL into other people's tables).

  docker compose --profile mock run --rm mock                      # inside the local Docker stack
  .venv/bin/python scripts/seed_world.py --api http://localhost:8000
  .venv/bin/python scripts/seed_world.py --fast                    # smaller world, ~1 minute
  .venv/bin/python scripts/seed_world.py --check                   # is the world complete? (exit 1 if not)

What it builds (definitions: data/mock/world.json, data/mock/personas.json; accounts: data/mock/README.md):
  1. history, last 14 days, in time order: ~370 citizen complaints (19115 imports, scripts/gen_complaints.py)
     interleaved with simulated bus/tram rides (scripts/simulate_buses.py) streamed to /devices/stream,
     back-dated so road health has fresh corridors (MAR, JER) and a stale one (SWI);
  2. now: demo users sign in (/auth/dev), report with photos (/mobile/reports), answer "is it still there?"
     (/mobile/incidents/{id}/answer), save favourite routes; two false alarms are reported;
  3. the city (admin) moves incidents to in progress / done (/admin/incidents/{id}/work);
  4. final rides: buses drive over the false alarms (-> dismissed) and the repaired pothole (-> healthy).

One world: complaint spots near a simulated line sit on it, at a simulated defect, so vehicles confirm them
instead of counting clean passes against real complaints. The same --seed gives the same world (times are
relative to the run). Idempotent: a seeded database is detected and left alone. ALL DATA IS SYNTHETIC.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import random
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import gen_complaints as gc  # noqa: E402
import simulate_buses as sim  # noqa: E402
import synth_ride as synth  # noqa: E402

MOCK_DIR = REPO_ROOT / "data" / "mock"
WARSAW = ZoneInfo("Europe/Warsaw")
REPORT_BATCH = 50
RIDE_CHUNK_S = 60.0           # seconds of ride data per /devices/stream request
MATCH_M = 40.0                # fusion merges evidence within 40 m (backend/fusion/incidents.py)
ANSWER_ACCURACY_M = 6.0
DETECTABLE = {"road_damage": "road", "tram_track": "tram"}  # what a passing vehicle can confirm or miss
SAMPLE_COLS = ["t", "ax", "ay", "az", "lat", "lon", "speed_kmh", "lux"]


def load(name: str) -> dict:
    return json.loads((MOCK_DIR / name).read_text(encoding="utf-8"))


def dist_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    return float(synth._haversine_m(a[1], a[0], b[1], b[0]))


# --------------------------------------------------------------------------- the plan (pure, deterministic)

@dataclass
class Ride:
    device: str
    mode: str
    line: str
    trip: int
    night: bool
    start: datetime | None          # None = the ride ends "now" (final phase)
    removed: tuple[str, ...] = ()   # defect ids repaired before this ride


@dataclass
class Plan:
    now: datetime
    seed: int
    fast: bool
    defects: list[dict]
    centres: dict[int, tuple[float, float]]
    complaints: list[dict]
    rides: list[Ride]
    final_rides: list[Ride]
    world: dict
    personas: dict
    targets: dict[str, tuple[float, float]] = field(default_factory=dict)


def world_defects(world: dict) -> list[dict]:
    """The simulator's ground truth plus the S6 extra defects."""
    return sim.load_world()["defects"] + [dict(d) for d in world["extra_defects"]]


def spot_centres(defects: list[dict], snap_m: float) -> dict[int, tuple[float, float]]:
    """Complaint spot -> where its complaints are pinned. A spot a vehicle could confirm (pothole / track
    defect) that lies near a simulated defect is moved onto it, so passing vehicles confirm the citizens."""
    centres = {}
    for issue_id, (_, lon, lat, cat, *_rest) in enumerate(gc.SPOTS, start=1):
        centres[issue_id] = (lon, lat)
        mode = DETECTABLE.get(cat)
        near = [d for d in defects if mode and d["mode"] == mode and d["kind"] == "bump"
                and dist_m((d["lon"], d["lat"]), (lon, lat)) <= snap_m]
        if near:
            d = min(near, key=lambda d: dist_m((d["lon"], d["lat"]), (lon, lat)))
            centres[issue_id] = (d["lon"], d["lat"])
    return centres


def complaints(world: dict, centres: dict, *, now: datetime, seed: int, fast: bool) -> list[dict]:
    """History complaints (19115 imports), time-sorted; stable place phrases keep geocoding fast."""
    ids = world["fast_spots"] if fast else range(1, len(gc.SPOTS) + 1)
    spots = {}
    for i in ids:
        street, _, _, cat, n, places, marks = gc.SPOTS[i - 1]
        n = min(n, world["fast_max_reports_per_spot"]) if fast else n
        spots[i] = (street, *centres[i], cat, n, places, marks)
    return gc.generate(seed, now - timedelta(hours=1), spots=spots, window_days=world["history_days"],
                       stable_places=True)


def ride_schedule(world: dict, *, now: datetime, seed: int, fast: bool) -> list[Ride]:
    """Back-dated history rides: daytime rides per line and day, a few night rides (lux sees dark lamps)."""
    cfg, devices = world["rides"]["fast" if fast else "full"], world["rides"]["devices"]
    rng = random.Random(seed)
    rides = []
    for night in (False, True):
        for line, days in cfg["night" if night else "day"].items():
            mode = "tram" if line in synth.ROUTES else "road"
            for days_ago in days:
                for k, dev in enumerate(devices[line][:1] if night else devices[line]):
                    if days_ago >= 1:  # a whole day ago: a plausible local time on that day
                        hour = rng.uniform(21.5, 23.0) if night else rng.uniform(7.0, 18.5)
                        day = (now - timedelta(days=days_ago)).astimezone(WARSAW)
                        start = day.replace(hour=int(hour), minute=int(hour % 1 * 60), second=0, microsecond=0)
                    else:
                        start = now - timedelta(days=days_ago, minutes=rng.uniform(0, 30))
                    start = min(start + timedelta(minutes=25 * k), now - timedelta(minutes=45))
                    rides.append(Ride(dev, mode, line, 0, night, start.astimezone(timezone.utc)))
    rides.sort(key=lambda r: r.start)
    trips: dict[str, int] = defaultdict(int)
    for r in rides:  # each vehicle's trips in time order: outbound, return, outbound, ...
        r.trip, trips[r.device] = trips[r.device], trips[r.device] + 1
    return rides


def final_rides(world: dict, last_trip: dict[str, int]) -> list[Ride]:
    """Rides that end now, after the city's work: over the false alarms and the repaired defects."""
    repaired = tuple(w["repairs_defect"] for w in world["work"]["done"] if w.get("repairs_defect"))
    out = []
    for line, n in world["rides"]["final_passes"].items():
        devs = world["rides"]["devices"][line]
        for k in range(n):
            dev = devs[k % len(devs)]
            last_trip[dev] = last_trip.get(dev, -1) + 1
            out.append(Ride(dev, "tram" if line in synth.ROUTES else "road", line, last_trip[dev], False, None,
                            removed=repaired))
    return out


def build_plan(*, now: datetime, seed: int, fast: bool, world: dict | None = None,
               personas: dict | None = None) -> Plan:
    world = world or load("world.json")
    personas = personas or load("personas.json")
    defects = world_defects(world)
    centres = spot_centres(defects, world["snap_to_route_m"])
    rides = ride_schedule(world, now=now, seed=seed, fast=fast)
    last_trip: dict[str, int] = {}
    for r in rides:
        last_trip[r.device] = max(last_trip.get(r.device, -1), r.trip)
    plan = Plan(now, seed, fast, defects, centres, complaints(world, centres, now=now, seed=seed, fast=fast),
                rides, final_rides(world, last_trip), world, personas)
    plan.targets = {f"spot:{i}": c for i, c in centres.items()}
    plan.targets.update({f"defect:{d['id']}": (d["lon"], d["lat"]) for d in defects})
    plan.targets.update({f"false_alarm:{f['id']}": (f["lon"], f["lat"]) for f in world["false_alarms"]})
    return plan


def target_of(at: dict, plan: Plan) -> tuple[float, float]:
    """A persona report's place: {"spot": n} | {"defect": id} | {"false_alarm": id} | {"lon", "lat"}."""
    if "lon" in at:
        return float(at["lon"]), float(at["lat"])
    (kind, ref), = at.items()
    return plan.targets[f"{kind}:{ref}"]


def timeline(plan: Plan) -> list[tuple[str, object]]:
    """History events in time order: ("reports", [records]) batches between ("ride", Ride) events."""
    events: list[tuple[datetime, int, str, object]] = []
    for r in plan.complaints:
        events.append((datetime.fromisoformat(r["created_at"]), 0, "report", r))
    for ride in plan.rides:
        events.append((ride.start, 1, "ride", ride))
    events.sort(key=lambda e: (e[0], e[1]))
    out: list[tuple[str, object]] = []
    for _, _, kind, item in events:
        if kind == "report":
            if out and out[-1][0] == "reports" and len(out[-1][1]) < REPORT_BATCH:
                out[-1][1].append(item)
            else:
                out.append(("reports", [item]))
        else:
            out.append(("ride", item))
    return out


def jitter(lon: float, lat: float, rng: random.Random, max_m: float = 6.0) -> tuple[float, float]:
    dx, dy = rng.uniform(-max_m, max_m), rng.uniform(-max_m, max_m)
    return round(lon + dx / (111_320 * math.cos(math.radians(lat))), 6), round(lat + dy / 110_540, 6)


# --------------------------------------------------------------------------- generated photos (no real people)

def photo(category: str, seed: int) -> bytes:
    """A small synthetic JPEG that looks roughly like the problem (asphalt with a hole, dark street, water...)."""
    from PIL import Image, ImageDraw, ImageFilter

    rng = np.random.default_rng(seed)
    w, h = 640, 480
    night = category == "streetlight"
    base = 30 if night else 105
    noise = rng.normal(base, 9 if night else 14, size=(h, w)).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(np.stack([noise] * 3, axis=-1)).filter(ImageFilter.GaussianBlur(1.2))
    d = ImageDraw.Draw(img)
    cx, cy = int(rng.integers(220, 420)), int(rng.integers(260, 360))
    if category in ("road_damage", "tram_track"):
        if category == "tram_track":
            for x in (230, 410):
                d.line([(x - 60, h), (x + 40, 0)], fill=(150, 150, 155), width=9)
        pts = [(cx + int(r * math.cos(a)), cy + int(0.55 * r * math.sin(a)))
               for a, r in zip(np.linspace(0, 2 * math.pi, 18, endpoint=False), rng.uniform(55, 95, 18))]
        d.polygon(pts, fill=(38, 34, 30), outline=(70, 65, 60))
    elif category == "streetlight":
        d.line([(cx, h), (cx, 120)], fill=(70, 70, 75), width=10)
        d.line([(cx, 120), (cx + 70, 110)], fill=(70, 70, 75), width=8)
        d.ellipse([cx + 55, 105, cx + 95, 125], fill=(45, 45, 40))  # the dead lamp
    elif category == "flooding":
        d.ellipse([cx - 220, cy - 70, cx + 220, cy + 90], fill=(70, 90, 105))
    elif category == "waste":
        for _ in range(14):
            x, y = int(rng.integers(150, 500)), int(rng.integers(250, 430))
            col = tuple(int(c) for c in rng.integers(20, 230, 3))
            d.rectangle([x, y, x + int(rng.integers(25, 70)), y + int(rng.integers(20, 50))], fill=col)
    out = io.BytesIO()
    img.filter(ImageFilter.GaussianBlur(0.6)).save(out, "JPEG", quality=82)
    return out.getvalue()


# --------------------------------------------------------------------------- HTTP

class Client:
    """Small stdlib JSON/form/multipart client; one bearer token per call."""

    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, *, token: str | None = None, body: dict | None = None,
             form: dict | None = None, files: dict | None = None, headers: dict | None = None,
             timeout: float = 900) -> dict:
        hdrs = dict(headers or {})
        data = None
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        if body is not None:
            data, hdrs["Content-Type"] = json.dumps(body).encode(), "application/json"
        elif files:
            boundary = uuid.uuid4().hex
            parts = []
            for k, v in (form or {}).items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
            for k, (name, blob, ctype) in files.items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\n'
                             f"Content-Type: {ctype}\r\n\r\n".encode() + blob + b"\r\n")
            data = b"".join(parts) + f"--{boundary}--\r\n".encode()
            hdrs["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif form is not None:
            from urllib.parse import urlencode
            data, hdrs["Content-Type"] = urlencode(form).encode(), "application/x-www-form-urlencoded"
        req = urllib.request.Request(self.base + path, data, hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, f"{method} {path} -> {e.code}: {e.read().decode(errors='replace')[:300]}") from e

    def get(self, path: str, **kw) -> dict:
        return self.call("GET", path, **kw)

    def post(self, path: str, **kw) -> dict:
        return self.call("POST", path, **kw)


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def sign_in(api: Client, email: str) -> tuple[str, dict]:
    out = api.post("/auth/dev", body={"email": email})
    return out["token"], out["user"]


# --------------------------------------------------------------------------- rides

def render_ride(job: tuple) -> np.ndarray:
    """Worker: one simulated ride -> array of SAMPLE_COLS with relative t."""
    ride, defects, seed = job
    world = [d for d in defects if d["id"] not in ride.removed]
    df, _, _ = sim.build_ride(ride.device, ride.mode, ride.line, ride.trip, seed=seed, night=ride.night,
                              defects=world)
    return df[SAMPLE_COLS].to_numpy(float)


def samples_at(arr: np.ndarray, start_epoch: float) -> list[dict]:
    """Rows -> /devices/stream samples with absolute epoch seconds (back-dated rides keep their time)."""
    out = []
    for t, ax, ay, az, lat, lon, spd, lux in arr.tolist():
        s = {"t": round(start_epoch + t, 3), "ax": ax, "ay": ay, "az": az, "lat": lat, "lon": lon, "speed_kmh": spd}
        if lux == lux:  # not NaN
            s["lux"] = lux
        out.append(s)
    return out


def send_ride(api_base: str, keys: dict[str, str], ride: Ride, arr: np.ndarray) -> dict:
    duration = float(arr[-1, 0]) if len(arr) else 0.0
    start = ride.start or datetime.now(timezone.utc) - timedelta(seconds=duration + 30)
    res = sim.stream_ride(api_base, f"{ride.device}:{keys[ride.device]}", ride.line, ride.mode,
                          samples_at(arr, start.timestamp()), chunk_s=RIDE_CHUNK_S, speed=0, stop=threading.Event())
    return res or {}


# --------------------------------------------------------------------------- phases

def say(text: str) -> None:
    print(text, flush=True)


def history(api: Client, plan: Plan, keys: dict[str, str], pool: ProcessPoolExecutor) -> None:
    events = timeline(plan)
    rides = [e[1] for e in events if e[0] == "ride"]
    futures = {id(r): pool.submit(render_ride, (r, plan.defects, plan.seed)) for r in rides}
    say(f"history: {len(plan.complaints)} complaints and {len(rides)} rides over {plan.world['history_days']} days")
    t0, sent, done_rides = time.monotonic(), 0, 0
    for kind, item in events:
        if kind == "reports":
            api.post("/reports/bulk", body={"reports": [
                {"text": r["text"], "created_at": r["created_at"], "lon": r["lon"], "lat": r["lat"], "source": "19115"}
                for r in item]})
            sent += len(item)
        else:
            send_ride(api.base, keys, item, futures.pop(id(item)).result())
            done_rides += 1
        if kind == "ride" or sent % 100 < len(item if kind == "reports" else []):
            say(f"  {sent} complaints, {done_rides} rides ({time.monotonic() - t0:.0f} s)")


def incident_near(api: Client, at: tuple[float, float], issue_type: str | None = None, *,
                  token: str | None = None, public: bool = True) -> dict | None:
    """Nearest incident (optionally of one type) within MATCH_M of a place."""
    rows = (api.get("/mobile/incidents?limit=5000")["incidents"] if public
            else api.get("/incidents?limit=5000", token=token)["incidents"])
    rows = [r for r in rows if issue_type is None or r["type"] == issue_type]
    best = min(rows, key=lambda r: dist_m((r["lon"], r["lat"]), at), default=None)
    return best if best and dist_m((best["lon"], best["lat"]), at) <= MATCH_M else None


def spot_type(spot: int) -> str:
    return gc.SPOTS[spot - 1][3]


def people(api: Client, plan: Plan) -> dict[str, str]:
    """Sign-ins, persona reports with photos, false alarms, answers, favourite routes. Returns key -> token."""
    rng = random.Random(plan.seed + 7)
    tokens = {p["key"]: sign_in(api, p["email"])[0] for p in plan.personas["personas"]}
    say(f"people: {len(tokens)} demo citizens signed in")
    for fa in plan.world["false_alarm_anonymous_reports"]:
        lon, lat = jitter(*plan.targets[f"false_alarm:{fa['false_alarm']}"], rng)
        api.post("/reports", form={"text": fa["text"], "lon": lon, "lat": lat,
                                   "contributor": f"mock-anonymous-{fa['false_alarm'].lower()}"})
    n_reports = n_photos = 0
    for p in plan.personas["personas"]:
        for k, rep in enumerate(p.get("reports", [])):
            lon, lat = jitter(*target_of(rep["at"], plan), rng)
            form = {"text": rep["text"], "lon": lon, "lat": lat}
            files = None
            if rep.get("photo"):
                files = {"photo": (f"{p['key']}_{k}.jpg", photo(rep["photo"], plan.seed + n_reports), "image/jpeg")}
                n_photos += 1
            api.post("/mobile/reports", token=tokens[p["key"]], form=form, files=files,
                     headers={"Accept-Language": rep.get("lang", "pl")})
            n_reports += 1
    say(f"  {n_reports} reports from the app ({n_photos} with photos), "
        f"{len(plan.world['false_alarm_anonymous_reports'])} anonymous false alarms")
    answers(api, plan, tokens)
    n_routes = 0
    for p in plan.personas["personas"]:
        for r in p.get("routes", []):
            api.post("/mobile/routes", token=tokens[p["key"]], body=r)
            n_routes += 1
    say(f"  {n_routes} favourite routes saved")
    return tokens


def answers(api: Client, plan: Plan, tokens: dict[str, str]) -> None:
    """"Is it still there?" from within 25 m: truthful personas say yes to real problems and no to false
    alarms, the unreliable one the opposite. Settled trust then separates them."""
    policy = {p["key"]: p.get("answers", "none") for p in plan.personas["personas"]}
    given = skipped = 0
    for key, todo in plan.world["answers"].items():
        targets = [(f"spot:{s}", spot_type(s), True) for s in todo.get("spots", [])]
        targets += [(f"false_alarm:{f}", "road_damage", False) for f in todo.get("false_alarms", [])]
        for ref, issue_type, real in targets:
            inc = incident_near(api, plan.targets[ref], issue_type)
            if inc is None or inc["status"] not in ("candidate", "likely"):
                skipped += 1
                continue
            truthful = policy[key] != "wrong"
            yes = real if truthful else not real
            try:
                api.post(f"/mobile/incidents/{inc['id']}/answer", token=tokens[key],
                         body={"answer": "yes" if yes else "no", "lon": inc["lon"], "lat": inc["lat"],
                               "accuracy_m": ANSWER_ACCURACY_M})
                given += 1
            except ApiError as exc:
                if exc.status not in (403, 409):
                    raise
                skipped += 1
    say(f"  {given} answers to 'is it still there?' ({skipped} not askable)")


def city_work(api: Client, plan: Plan, admin_token: str) -> None:
    """The city's work status: in progress, done (done settles the trust of everyone who answered)."""
    moved = 0
    for status in ("in_progress", "done"):
        for item in plan.world["work"][status]:
            inc = incident_near(api, plan.targets[f"spot:{item['spot']}"], spot_type(item["spot"]))
            if inc is None:
                say(f"  ! no incident at spot {item['spot']} for work status {status}")
                continue
            steps = ["in_progress", "done"] if status == "done" else ["in_progress"]
            for step in steps:
                api.post(f"/admin/incidents/{inc['id']}/work", token=admin_token,
                         body={"status": step, "note": item["note"] if step == status else "Crew dispatched."})
            moved += 1
    say(f"city: {moved} incidents moved to in progress / done by the admin")


def final(api: Client, plan: Plan, keys: dict[str, str], pool: ProcessPoolExecutor) -> None:
    futures = [pool.submit(render_ride, (r, plan.defects, plan.seed)) for r in plan.final_rides]
    for ride, fut in zip(plan.final_rides, futures):
        send_ride(api.base, keys, ride, fut.result())
    say(f"final: {len(plan.final_rides)} rides now (false alarms get clean passes, the repaired pothole is gone)")


# --------------------------------------------------------------------------- check

def check(api: Client, plan_personas: dict, *, admin_email: str, fast: bool) -> list[tuple[str, bool, str]]:
    """Is every area of the world there? [(name, ok, detail)]"""
    out: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        out.append((name, bool(ok), detail))

    admin_token, admin = sign_in(api, admin_email)
    add("admin account", admin.get("role") == "admin", f"{admin_email} role={admin.get('role')}")
    stats = api.get("/stats")
    want = 80 if fast else 300
    add("complaints", stats.get("reports_total", 0) >= want, f"{stats.get('reports_total')} reports (want >= {want})")
    for status in ("candidate", "likely", "verified", "dismissed"):
        n = len(api.get(f"/incidents?status={status}&limit=5000")["incidents"])
        add(f"incidents {status}", n > 0, f"{n}")
    add("found before any report", stats.get("found_before_report", 0) > 0, f"{stats.get('found_before_report')}")
    add("awaiting a vehicle", stats.get("awaiting_verification", 0) > 0, f"{stats.get('awaiting_verification')}")
    add("road health measured", stats.get("segments_measured", 0) >= 100, f"{stats.get('segments_measured')} segments")
    lines = {(x["line"], x["mode"]) for x in api.get("/mobile/lines")["lines"]}
    add("bus and tram lines", {("MAR", "road"), ("JER", "road"), ("SWI", "road"), ("17", "tram")} <= lines,
        ", ".join(sorted(f"{a}/{b}" for a, b in lines)))
    adm = api.get("/admin/stats", token=admin_token)
    todo = sum(int(d.get("todo") or 0) for d in adm.get("departments", []))
    add("city work: todo / in progress / done", todo > 0 and adm.get("in_progress_total", 0) > 0
        and adm.get("done_total", 0) > 0, f"{todo} / {adm.get('in_progress_total')} / {adm.get('done_total')}")
    trust, photos, routes = {}, 0, {}
    for p in plan_personas["personas"]:
        tok = sign_in(api, p["email"])[0]
        me = api.get("/mobile/me", token=tok)
        trust[p["key"]] = float(me.get("trust") or 0)
        add(f"persona {p['key']}", me["reports_count"] >= len(p.get("reports", [])),
            f"{me['reports_count']} reports, {me['answers_count']} answers, trust {trust[p['key']]:.2f}")
        photos += sum(1 for r in api.get("/mobile/reports", token=tok)["reports"] if r.get("photo_url"))
        routes[p["key"]] = len(api.get("/mobile/routes", token=tok)["routes"])
    add("trust differs (reliable > newcomer > unreliable)",
        trust.get("anna", 0) > trust.get("olena", 0.5) > trust.get("marek", 1),
        f"anna {trust.get('anna', 0):.2f}, olena {trust.get('olena', 0):.2f}, marek {trust.get('marek', 0):.2f}")
    add("report photos", photos > 0, f"{photos}")
    want_routes = {p["key"]: len(p.get("routes", [])) for p in plan_personas["personas"] if p.get("routes")}
    add("favourite routes", all(routes.get(k, 0) >= n for k, n in want_routes.items()),
        ", ".join(f"{k} {routes.get(k, 0)}" for k in want_routes))
    return out


def admin_email_from_env() -> str | None:
    from backend.config import settings

    return settings.admin_emails[0] if settings.admin_emails else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--seed", type=int, default=None, help="world seed (default: data/mock/world.json)")
    ap.add_argument("--fast", action="store_true", help="smaller world for quick local tests")
    ap.add_argument("--check", action="store_true", help="only check that the world is complete (exit 1 if not)")
    ap.add_argument("--force", action="store_true", help="seed even if the database already has other data")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from backend.config import settings

    api = Client(args.api)
    personas = load("personas.json")
    admin_email = admin_email_from_env() or personas["admin"]["email"]
    if args.check:
        results = check(api, personas, admin_email=admin_email, fast=args.fast)
        for name, ok, detail in results:
            say(f"{'OK  ' if ok else 'MISS'} {name}: {detail}")
        return 0 if all(ok for _, ok, _ in results) else 1

    t0 = time.monotonic()
    try:
        admin_token, admin = sign_in(api, admin_email)
    except ApiError as exc:
        say(f"cannot sign in through /auth/dev ({exc}). The API needs AUTH_DEV_LOGIN=1 (on in the Docker stack).")
        return 2
    if admin.get("role") != "admin":
        say(f"{admin_email} is not an admin: add it to ADMIN_EMAILS in .env (the API and this script read it), "
            f"e.g. ADMIN_EMAILS={personas['admin']['email']}")
        return 2
    marker = personas["personas"][0]
    if api.get("/mobile/me", token=sign_in(api, marker["email"])[0])["reports_count"] > 0:
        say("the mock world is already seeded (nothing to do). Reset with: docker compose down -v")
        return 0
    if api.get("/stats").get("reports_total", 0) > 0 and not args.force:
        say("the database already holds other data (e.g. seed_demo.py). Start clean with `docker compose down -v`, "
            "or pass --force to add the mock world on top.")
        return 2
    world = load("world.json")
    seed = args.seed if args.seed is not None else int(world["seed"])
    plan = build_plan(now=datetime.now(timezone.utc), seed=seed, fast=args.fast, world=world, personas=personas)
    keys = settings.device_keys
    needed = {r.device for r in plan.rides + plan.final_rides}
    if missing := sorted(needed - set(keys)):
        say(f"DEVICE_KEYS in .env lacks {', '.join(missing)} (format: see .env.example)")
        return 2
    say(f"seeding the {'fast' if args.fast else 'full'} mock world (seed {seed}) into {args.api}")
    with ProcessPoolExecutor() as pool:
        history(api, plan, keys, pool)
        people(api, plan)
        city_work(api, plan, admin_token)
        final(api, plan, keys, pool)
    say(f"done in {time.monotonic() - t0:.0f} s. Accounts and what to show: data/mock/README.md")
    results = check(api, personas, admin_email=admin_email, fast=args.fast)
    for name, ok, detail in results:
        say(f"{'OK  ' if ok else 'MISS'} {name}: {detail}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
