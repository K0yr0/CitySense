"""Replay a saved ride through the API, e.g. to show the verification loop on stage.

    python scripts/replay_ride.py --file data/demo/tram17_ride1.csv --line 17
    python scripts/replay_ride.py --incident 12 --line 17 --wait 5   # "waiting for tram 17..." -> verified

With --incident the script first shows the incident (requesting a verification
vehicle if none is assigned yet), then uploads the ride and prints whether the
incident was confirmed by the ride's sensors.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "data" / "demo"


def _default_file() -> Path | None:
    rides = sorted(p for p in DEMO_DIR.glob("tram17_*.csv") if not p.stem.endswith("_truth"))
    return rides[0] if rides else None


def _get(client: httpx.Client, path: str) -> dict:
    r = client.get(path)
    r.raise_for_status()
    return r.json()


def describe(inc: dict) -> str:
    where = inc.get("address") or f"{inc.get('lat'):.5f}, {inc.get('lon'):.5f}"
    return (f"incident #{inc['id']} [{inc['type']}] at {where}: status={inc['status']}, "
            f"reports={inc['report_count']}, sensor rides={inc['sensor_rides']}, score={inc['score']:.2f}")


def upload(client: httpx.Client, path: Path, line: str | None, mode: str) -> dict:
    with path.open("rb") as fh:
        r = client.post("/rides/upload", files={"file": (path.name, fh, "text/csv" if path.suffix == ".csv" else "application/zip")},
                        data={"vehicle_line": line or "", "mode": mode})
    if r.status_code >= 400:
        sys.exit(f"upload failed ({r.status_code}): {r.text}")
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000", help="API base URL")
    ap.add_argument("--file", type=Path, default=None, help="ride CSV or Sensor Logger .zip (default: first data/demo/tram17_*.csv)")
    ap.add_argument("--line", default="17", help="vehicle line, e.g. 17")
    ap.add_argument("--mode", default="tram", choices=["tram", "road"])
    ap.add_argument("--incident", type=int, default=None, help="incident id to verify with this ride")
    ap.add_argument("--wait", type=float, default=0, help="seconds to pause before uploading (stage drama)")
    args = ap.parse_args()

    path = args.file or _default_file()
    if path is None or not path.exists():
        sys.exit(f"ride file not found: {path or 'data/demo/tram17_*.csv'} (generate one with scripts/synth_ride.py)")

    with httpx.Client(base_url=args.api.rstrip("/"), timeout=600) as client:
        try:
            _get(client, "/health")
        except httpx.HTTPError as exc:
            sys.exit(f"API not reachable at {args.api}: {exc}")

        if args.incident is not None:
            try:
                inc = _get(client, f"/incidents/{args.incident}")
            except httpx.HTTPStatusError as exc:
                sys.exit(f"incident {args.incident}: {exc.response.status_code} {exc.response.text}")
            print(describe(inc))
            vehicle = inc.get("verify_vehicle")
            if not vehicle and not inc.get("has_sensor"):
                req = client.post(f"/incidents/{args.incident}/verify").json()
                vehicle, eta = req.get("vehicle"), req.get("eta_min")
                print(f"verification requested: {vehicle or 'next vehicle'}" + (f", ETA ~{eta} min" if eta is not None else ""))
            print(f"waiting for {vehicle or f'{args.mode} {args.line}'}…", flush=True)
            if args.wait > 0:
                time.sleep(args.wait)

        print(f"uploading {path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path} "
              f"as {args.mode} {args.line} …", flush=True)
        t0 = time.monotonic()
        res = upload(client, path, args.line, args.mode)
        print(f"ride #{res['ride_id']} processed in {time.monotonic() - t0:.1f}s: {res['bumps']} bumps, "
              f"{res['dark_gaps']} dark gaps, {res['segments_covered']} segments, "
              f"{len(res['evidence_ids'])} evidence -> incidents {res['incident_ids']}")
        if res["verified_incident_ids"]:
            print(f"verification checks updated incidents {res['verified_incident_ids']}")

        if args.incident is not None:
            inc = _get(client, f"/incidents/{args.incident}")
            print(describe(inc))
            status = inc["status"]
            if status == "confirmed" or (inc.get("sensor_confirmed") and args.incident in res["incident_ids"]):
                print(f"VERIFIED: {inc.get('verify_vehicle') or f'{args.mode} {args.line}'} sensors confirmed incident #{args.incident}.")
            elif status == "no_anomaly":
                print(f"NO ANOMALY: the ride passed incident #{args.incident} without detecting anything.")
            else:
                print(f"not verified yet (status={status}); did the ride pass the incident's segment?")


if __name__ == "__main__":
    main()
