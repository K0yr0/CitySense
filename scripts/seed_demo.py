"""Seed a demo database through the HTTP API (the API must be running).

    python scripts/seed_demo.py                       # all complaints + all tram 17 demo rides
    python scripts/seed_demo.py --limit 100 --skip-rides

1. bulk-posts data/complaints_synth.json (chronological, in batches) to /reports/bulk,
   sending each record's lon/lat as the pin;
2. uploads data/demo/tram17_*.csv rides to /rides/upload (line 17, tram);
3. prints /stats.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPLAINTS = REPO_ROOT / "data" / "complaints_synth.json"
DEMO_DIR = REPO_ROOT / "data" / "demo"


def seed_reports(client: httpx.Client, path: Path, limit: int | None, batch: int) -> None:
    if not path.exists():
        print(f"skip complaints: {path} not found (run scripts/gen_complaints.py)")
        return
    records = json.loads(path.read_text(encoding="utf-8"))
    records = sorted(records, key=lambda r: r.get("created_at") or "")[:limit]
    payload = [{k: v for k, v in {"text": r.get("text"), "created_at": r.get("created_at"), "lon": r.get("lon"),
                                   "lat": r.get("lat"), "source": r.get("source") or "synthetic"}.items() if v is not None}
               for r in records]
    print(f"posting {len(payload)} complaints in batches of {batch} …")
    done = failed = 0
    incidents: set[int] = set()
    t0 = time.monotonic()
    for i in range(0, len(payload), batch):
        chunk = payload[i:i + batch]
        r = client.post("/reports/bulk", json={"reports": chunk})
        if r.status_code >= 400:
            print(f"  batch {i // batch + 1} failed ({r.status_code}): {r.text[:200]}")
            failed += len(chunk)
            continue
        res = r.json()
        done += res["processed"]
        failed += len(chunk) - res["processed"]
        incidents.update(res["incident_ids"])
        print(f"  {done + failed}/{len(payload)} sent, {done} processed, {len(incidents)} incidents "
              f"({time.monotonic() - t0:.0f}s)", flush=True)
    print(f"complaints: {done} processed, {failed} failed, {len(incidents)} incidents touched")


def seed_rides(client: httpx.Client) -> None:
    rides = sorted(p for p in DEMO_DIR.glob("tram17_*.csv") if not p.stem.endswith("_truth"))
    if not rides:
        print(f"skip rides: no {DEMO_DIR.relative_to(REPO_ROOT)}/tram17_*.csv (run scripts/synth_ride.py)")
        return
    for path in rides:
        with path.open("rb") as fh:
            r = client.post("/rides/upload", files={"file": (path.name, fh, "text/csv")},
                            data={"vehicle_line": "17", "mode": "tram"})
        if r.status_code >= 400:
            print(f"  {path.name}: failed ({r.status_code}): {r.text[:200]}")
            continue
        res = r.json()
        print(f"  {path.name}: ride #{res['ride_id']}, {res['bumps']} bumps, {res['dark_gaps']} dark gaps, "
              f"{res['segments_covered']} segments, incidents {res['incident_ids']}, verified {res['verified_incident_ids']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000", help="API base URL")
    ap.add_argument("--limit", type=int, default=None, help="max number of complaints to import")
    ap.add_argument("--skip-rides", action="store_true", help="do not upload the demo rides")
    ap.add_argument("--file", type=Path, default=COMPLAINTS, help="complaints JSON (default data/complaints_synth.json)")
    ap.add_argument("--batch", type=int, default=25, help="complaints per /reports/bulk request")
    args = ap.parse_args()

    with httpx.Client(base_url=args.api.rstrip("/"), timeout=900) as client:
        try:
            client.get("/health").raise_for_status()
        except httpx.HTTPError as exc:
            sys.exit(f"API not reachable at {args.api}: {exc}  (start it: uvicorn backend.main:app)")
        seed_reports(client, args.file, args.limit, max(1, args.batch))
        if not args.skip_rides:
            print("uploading demo rides …")
            seed_rides(client)
        stats = client.get("/stats").json()
        print("stats:", json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
