"""Config tests: the Warsaw open data (ZTM) API key used for live vehicle positions."""
from __future__ import annotations

import httpx
import pytest

from backend.config import settings

ZTM_KEY_MIN_LENGTH = 20
ZTM_VEHICLES_URL = "https://dane.um.warszawa.pl/api/action/get_ztm_lokalizacja_pojazdow"

needs_ztm_key = pytest.mark.skipif(
    not settings.warsaw_api_key, reason="WARSAW_API_KEY not set; ZTM uses the sample snapshot"
)


@needs_ztm_key
def test_ztm_api_key_is_well_formed():
    key = settings.warsaw_api_key
    assert key == key.strip(), "WARSAW_API_KEY has leading/trailing whitespace"
    assert len(key) > ZTM_KEY_MIN_LENGTH, (
        f"WARSAW_API_KEY is {len(key)} chars; expected more than {ZTM_KEY_MIN_LENGTH}"
    )


@needs_ztm_key
def test_ztm_api_key_is_accepted_by_api():
    """Live call: the API answers a bad key with HTTP 500, a good one with a list of vehicles."""
    resp = httpx.post(ZTM_VEHICLES_URL, headers={"Authorization": settings.warsaw_api_key},
                      json={"type": 1}, timeout=15)
    assert resp.status_code == 200, f"ZTM API rejected the key: HTTP {resp.status_code} {resp.text[:200]}"
    vehicles = resp.json()
    assert isinstance(vehicles, list) and vehicles, "ZTM API returned no bus positions"
    assert {"Lines", "Lat", "Lon", "Time", "VehicleNumber"} <= vehicles[0].keys()
