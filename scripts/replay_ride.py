"""Replay a saved ride through the API, e.g. to show the verification loop on stage.

    python scripts/replay_ride.py --file data/demo/tram17_ride1.csv --line 17
    python scripts/replay_ride.py --incident 12 --line 17 --wait 5   # "waiting for tram 17..." -> verified

With --incident the script first shows the incident (requesting a verification
vehicle if none is assigned yet), then uploads the ride and prints how the ride
moved the incident's confidence (candidate -> likely -> verified, or down on a clean pass).
The incident endpoints are admin-only: pass --token (or CITYECHO_API_TOKEN), or the script signs in
through dev sign-in (local stack) as the first ADMIN_EMAILS entry.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "data" / "demo"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _default_file() -> Path | None:
    rides = sorted(p for p in DEMO_DIR.glob("tram17_*.csv") if not p.stem.endswith("_truth"))
    return rides[0] if rides else None


def _get(client: httpx.Client, path: str) -> dict:
    r = client.get(path)
    r.raise_for_status()
    return r.json()


def admin_token(client: httpx.Client) -> str | None:
    """Dev sign-in (local stack, AUTH_DEV_LOGIN) as the first ADMIN_EMAILS entry -> bearer token, or None."""
    from backend.config import settings

    if not settings.admin_emails:
        return None
    try:
        r = client.post("/auth/dev", json={"email": settings.admin_emails[0]})
        return r.json()["token"] if r.status_code == 200 else None
    except httpx.HTTPError:
        return None


def describe(inc: dict) -> str:
    where = inc.get("address") or f"{inc.get('lat'):.5f}, {inc.get('lon'):.5f}"
    return (f"incident #{inc['id']} [{inc['type']}] at {where}: status={inc['status']} "
            f"(confidence {100 * float(inc.get('confidence') or 0):.0f}%), "
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
    ap.add_argument("--token", default=os.getenv("CITYECHO_API_TOKEN"),
                    help="admin bearer token for the incident endpoints (default: dev sign-in as the admin)")
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
            token = args.token or admin_token(client)
            if not token:
                sys.exit("the incident endpoints are admin-only: pass --token, or enable dev sign-in "
                         "(AUTH_DEV_LOGIN=1) with an ADMIN_EMAILS entry in .env")
            client.headers["Authorization"] = f"Bearer {token}"
            try:
                inc = _get(client, f"/incidents/{args.incident}")
            except httpx.HTTPStatusError as exc:
                sys.exit(f"incident {args.incident}: {exc.response.status_code} {exc.response.text}")
            print(describe(inc))
            vehicle = inc.get("verify_vehicle")
            if not vehicle and not inc.get("has_sensor"):
                r = client.post(f"/incidents/{args.incident}/verify")
                if r.status_code >= 400:
                    sys.exit(f"verification request failed ({r.status_code}): {r.text}")
                req = r.json()
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
            print(f"this ride verified incidents {res['verified_incident_ids']}")

        if args.incident is not None:
            inc = _get(client, f"/incidents/{args.incident}")
            print(describe(inc))
            status = inc["status"]
            if status == "verified":
                print(f"VERIFIED: {inc.get('verify_vehicle') or f'{args.mode} {args.line}'} sensors confirmed incident #{args.incident}.")
            elif args.incident in res["incident_ids"]:
                print(f"DETECTED: the ride saw it; status={status}, more evidence needed to verify.")
            elif inc.get("sensor_misses"):
                print(f"NO ANOMALY: the ride passed incident #{args.incident} without detecting anything "
                      f"({inc['sensor_misses']} clean passes); confidence went down.")
            else:
                print(f"not verified yet (status={status}); did the ride pass the incident's segment?")


if __name__ == "__main__":
    main()
