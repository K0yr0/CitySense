"""Tests for triage geocoding, de-duplication, the report pipeline and the eval script.

No network, no PostGIS: httpx is mocked with MockTransport, DB and LLM deps are monkeypatched.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

from backend.config import REPO_ROOT, settings
from backend.models import Department, EvidenceIn, IssueType, Source, TriageResult
from backend.triage import dedup, geocode

T0 = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
MARSZ = (21.0122, 52.2297)  # Marszałkowska / Złota


# ---------------------------------------------------------------- geocode

@pytest.fixture
def geo(tmp_path, monkeypatch):
    """Isolated cache dir, no real waiting, and a programmable Nominatim mock."""
    monkeypatch.setattr(geocode, "settings", dataclasses.replace(settings, cache_dir=tmp_path, demo_mode=False))
    monkeypatch.setattr(geocode, "_limiter", geocode.RateLimiter(0.0))
    state = SimpleNamespace(requests=[], reply=None, tmp=tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        state.requests.append(request)
        reply = state.reply(request) if callable(state.reply) else state.reply
        return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=reply)

    monkeypatch.setattr(geocode, "_transport", httpx.MockTransport(handler))
    return state


def _hit(lon=21.0122, lat=52.2297, cls="highway", typ="residential", rank=26, importance=0.2,
         name="Marszałkowska, Warszawa"):
    return [{"lon": str(lon), "lat": str(lat), "class": cls, "type": typ, "place_rank": rank,
             "importance": importance, "display_name": name}]


def test_geocode_query_and_cache_hit(geo):
    geo.reply = _hit()
    lon, lat, conf = geocode.geocode("Marszałkowska")
    assert (lon, lat) == pytest.approx(MARSZ)
    assert 0.5 <= conf < 0.8  # street -> medium
    req = geo.requests[0]
    assert req.url.params["q"] == "Marszałkowska, Warszawa"
    assert req.url.params["viewbox"] == geocode.WARSAW_VIEWBOX and req.url.params["bounded"] == "1"
    assert req.url.params["limit"] == "1" and req.url.params["format"] == "json"
    assert req.headers["user-agent"] == settings.nominatim_user_agent
    # normalized key -> served from cache, no second request; persisted to disk
    assert geocode.geocode("  MARSZAŁKOWSKA. ") == (lon, lat, conf)
    assert len(geo.requests) == 1
    cached = json.loads((geo.tmp / "geocode.json").read_text(encoding="utf-8"))
    assert cached["marszałkowska"]["confidence"] == conf


def test_geocode_negative_result_is_cached(geo):
    geo.reply = []
    assert geocode.geocode("Nieistniejąca 999") is None
    assert geocode.geocode("nieistniejąca 999") is None
    assert len(geo.requests) == 1


def test_geocode_failure_returns_none_and_is_not_cached(geo):
    def boom(request):
        raise httpx.ConnectError("offline", request=request)
    geo.reply = boom
    assert geocode.geocode("Puławska 120") is None
    geo.reply = httpx.Response(503, text="busy")
    assert geocode.geocode("Puławska 120") is None
    geo.reply = httpx.Response(200, text="<html>not json</html>")
    assert geocode.geocode("Puławska 120") is None
    geo.reply = {"error": "Unable to geocode"}
    assert geocode.geocode("Puławska 120") is None
    assert len(geo.requests) == 4  # every attempt retried, nothing cached
    geo.reply = _hit(cls="place", typ="house", rank=30, name="120, Puławska, Mokotów, Warszawa")
    assert geocode.geocode("Puławska 120")[2] >= 0.85


def test_geocode_demo_mode_uses_cache_only(geo, monkeypatch):
    geo.reply = _hit()
    assert geocode.geocode("Marszałkowska") is not None
    monkeypatch.setattr(geocode, "settings", dataclasses.replace(geocode.settings, demo_mode=True))
    assert geocode.geocode("marszałkowska") is not None
    assert geocode.geocode("Złota 44") is None
    assert len(geo.requests) == 1
    assert geocode.geocode("") is None and geocode.geocode(None) is None


def test_geocode_rate_limit_spacing(geo, monkeypatch):
    clock = SimpleNamespace(now=100.0)

    def sleep(dt):
        clock.now += dt

    monkeypatch.setattr(geocode, "_limiter", geocode.RateLimiter(1.0, clock=lambda: clock.now, sleep=sleep))
    stamps = []
    geo.reply = lambda request: stamps.append(clock.now) or _hit()
    for text in ("Złota", "Krucza 15", "Grójecka", "Złota"):  # last one is a cache hit
        geocode.geocode(text)
    assert len(stamps) == 3
    assert all(b - a >= 1.0 for a, b in zip(stamps, stamps[1:]))


def test_rate_limiter_is_thread_safe():
    limiter, stamps, lock = geocode.RateLimiter(0.05), [], threading.Lock()

    def worker():
        limiter.wait()
        with lock:
            stamps.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stamps.sort()
    assert all(b - a >= 0.045 for a, b in zip(stamps, stamps[1:]))


def test_confidence_mapping():
    def conf(cls, typ, rank, text, name):
        return geocode._confidence({"class": cls, "type": typ, "place_rank": rank, "display_name": name}, text)

    assert conf("railway", "tram_stop", 30, "przystanek Plac Narutowicza", "Plac Narutowicza, Ochota") >= 0.85
    assert conf("place", "house", 30, "Krucza 15", "15, Krucza, Śródmieście") >= 0.85
    assert 0.5 <= conf("highway", "primary", 26, "na Puławskiej", "Puławska, Mokotów") < 0.8  # Polish case ok
    assert 0.5 <= conf("place", "square", 25, "Plac Narutowicza", "Plac Narutowicza, Ochota") < 0.8
    assert 0.5 <= conf("amenity", "cafe", 30, "róg Złotej i Emilii Plater", "Cafe, Złota, Emilii Plater") <= 0.65
    assert conf("boundary", "administrative", 16, "Mokotów", "Mokotów, Warszawa") < 0.5
    # junk name matches and unrelated hits never beat a user's pin
    assert conf("tourism", "information", 30, "Puławska", "Ulica Puławska, Puławska") < 0.5
    assert conf("tourism", "museum", 30, "przystanek Centrum", "Przystanek Historia, Marszałkowska") < 0.5


def test_geocode_strips_street_prefix(geo):
    geo.reply = _hit(name="Puławska, Mokotów, Warszawa")
    assert geocode.geocode("ul. Puławska")[2] >= 0.5
    assert geocode.geocode("ulica Puławska") is not None
    assert [r.url.params["q"] for r in geo.requests] == ["Puławska, Warszawa"] * 2


def test_geocode_retries_nominative_street_name(geo):
    geo.reply = lambda request: _hit(cls="place", typ="house", rank=30, name="15, Krucza, Warszawa") \
        if request.url.params["q"].startswith("Krucza") else []
    lon, lat, conf = geocode.geocode("ul. Kruczej 15")
    assert conf >= 0.85
    assert [r.url.params["q"] for r in geo.requests] == ["Kruczej 15, Warszawa", "Krucza 15, Warszawa"]
    assert geocode._variants("przy ul. Puławskiej 120") == ["Puławskiej 120", "Puławska 120"]
    assert geocode._variants("Długiej / Nowej") == ["Długiej / Nowej", "Długa / Nowa"]
    assert geocode._variants("Aleje Jerozolimskie 54") == ["Aleje Jerozolimskie 54"]


# ---------------------------------------------------------------- dedup

@pytest.fixture
def hashing(monkeypatch):
    """Force the sklearn hashing backend (the default here: no sentence-transformers)."""
    monkeypatch.setattr(dedup, "_model", False)
    monkeypatch.setattr(dedup, "BACKEND", "hashing")
    monkeypatch.setattr(dedup, "SIMILARITY_THRESHOLD", dedup.HASH_THRESHOLD)


PARAPHRASES = [
    "Ogromna dziura w jezdni na Marszałkowskiej przy Złotej, auta w nią wjeżdżają.",
    "Na ul. Marszałkowskiej koło Złotej jest wielka dziura w asfalcie.",
    "dziura w jezdni marszalkowska / zlota, uszkodzilem opone",
]
UNRELATED = "Zalana Wisłostrada po burzy, studzienki zatkane."
WASTE = ["Przepełnione kosze na śmieci przy przystanku Centrum, odpady leżą na chodniku.",
         "Kosze przy przystanku Centrum są pełne, śmieci na chodniku."]


def test_embed_fallback_shape_and_similarity(hashing):
    emb = dedup.embed(PARAPHRASES + [UNRELATED])
    assert emb.shape == (4, dedup.HASH_FEATURES) and emb.dtype == np.float32
    assert np.allclose(np.linalg.norm(emb, axis=1), 1.0, atol=1e-5)
    sim = emb @ emb.T
    para = [sim[0, 1], sim[0, 2], sim[1, 2]]
    unrel = sim[:3, 3]
    assert min(para) > max(unrel)
    assert min(para) > dedup.threshold() > max(unrel)
    assert dedup.embed([]).shape == (0, dedup.HASH_FEATURES)
    # diacritic folding: typing without Polish letters gives the same vector
    a, b = dedup.embed(["Zapadnięta studzienka, ulica Złota", "zapadnieta studzienka, ulica zlota"])
    assert float(a @ b) == pytest.approx(1.0)


def _rec(category="road_damage", lon=MARSZ[0], lat=MARSZ[1], created_at=T0, emb=(1.0, 0.0)):
    return {"category": category, "lon": lon, "lat": lat, "created_at": created_at,
            "emb": np.asarray(emb, dtype=np.float32)}


def test_same_incident_rules(hashing):
    base = _rec()
    assert dedup.same_incident(base, _rec(lat=MARSZ[1] + 0.0003, created_at=T0 + timedelta(hours=48)))  # ~33 m
    assert not dedup.same_incident(base, _rec(category="streetlight"))
    assert not dedup.same_incident(base, _rec(lat=MARSZ[1] + 0.0008))  # ~89 m
    assert not dedup.same_incident(base, _rec(created_at=T0 + timedelta(hours=80)))
    assert not dedup.same_incident(base, _rec(emb=(0.0, 1.0)))
    assert not dedup.same_incident(base, _rec(lon=None, lat=None))
    assert dedup.same_incident(base, _rec(created_at=(T0 - timedelta(hours=1)).isoformat()))  # ISO strings ok


def test_greedy_cluster_fixture(hashing):
    texts = PARAPHRASES + [
        "Nie świeci latarnia na Marszałkowskiej przy Złotej, kompletnie ciemno.",  # same spot, other category
        "Latarnia przy Marszałkowskiej / Złotej nie działa od tygodnia.",
        "Ogromna dziura w jezdni na Marszałkowskiej przy Złotej, auta w nią wjeżdżają.",  # same text, 300 m away
        "Na ul. Marszałkowskiej koło Złotej jest wielka dziura w asfalcie.",  # same spot, 5 days later
    ]
    emb = dedup.embed(texts)
    cats = ["road_damage"] * 3 + ["streetlight"] * 2 + ["road_damage"] * 2
    lats = [MARSZ[1], MARSZ[1] + 0.0001, MARSZ[1] - 0.0001, MARSZ[1], MARSZ[1], MARSZ[1] + 0.0027, MARSZ[1]]
    times = [T0 + timedelta(hours=h) for h in (5, 1, 30, 2, 20, 3, 5 + 24 * 5)]  # deliberately unsorted
    recs = [{"category": c, "lon": MARSZ[0], "lat": la, "created_at": t, "emb": e}
            for c, la, t, e in zip(cats, lats, times, emb)]
    labels = dedup.greedy_cluster(recs)
    assert labels[0] == labels[1] == labels[2]
    assert labels[3] == labels[4] != labels[0]
    assert len({labels[0], labels[3], labels[5], labels[6]}) == 4
    assert dedup.greedy_cluster([]) == []
    assert len(set(dedup.greedy_cluster(recs, threshold_=0.99))) == len(recs)


def test_find_duplicate_returns_canonical_id(hashing, monkeypatch):
    emb = dedup.embed(PARAPHRASES + [UNRELATED])
    rows = [{"id": 11, "duplicate_of": None, "embedding": emb[3].tolist()},
            {"id": 12, "duplicate_of": 7, "embedding": emb[1].tolist()},
            {"id": 13, "duplicate_of": None, "embedding": [1.0, 0.0]}]  # other backend dimension: ignored
    calls = []
    monkeypatch.setattr(dedup.db, "fetch_all", lambda conn, sql, params: calls.append((sql, params)) or rows)
    dup = dedup.find_duplicate("conn", category=IssueType.ROAD_DAMAGE, lon=MARSZ[0], lat=MARSZ[1],
                               created_at=T0, embedding=emb[0])
    assert dup == 7
    sql, params = calls[0]
    assert "ST_DWithin" in sql and "embedding is not null" in sql
    assert params["radius"] == 50 and params["category"] == "road_damage"
    assert params["t_to"] - params["t_from"] == timedelta(hours=144)
    # nothing similar enough -> None
    monkeypatch.setattr(dedup.db, "fetch_all", lambda conn, sql, params: rows[:1])
    assert dedup.find_duplicate("conn", category="road_damage", lon=MARSZ[0], lat=MARSZ[1],
                                created_at=T0, embedding=emb[0]) is None


# ---------------------------------------------------------------- pipeline

@pytest.fixture
def deps(monkeypatch, tmp_path):
    from backend.triage import pipeline

    s = SimpleNamespace(
        triage=TriageResult(category=IssueType.ROAD_DAMAGE, location_text="Marszałkowska przy Złotej",
                            urgency=4, hazard_to_people=True, department=Department.ZDM,
                            summary_en="Large pothole"),
        geo=None, duplicate=None, reports=[], evidence=[], segments=[], dup_calls=[], structure_calls=0,
        anonymized=[], checked=[], tmp=tmp_path, pipeline=pipeline)

    def fake_structure(text):
        s.structure_calls += 1
        return s.triage

    monkeypatch.setattr(pipeline, "settings", dataclasses.replace(settings, cache_dir=tmp_path))
    monkeypatch.setattr(pipeline.structure, "structure", fake_structure)
    monkeypatch.setattr(pipeline.vision, "anonymize", lambda b: s.anonymized.append(b) or b"ANON-JPEG")
    monkeypatch.setattr(pipeline.vision, "check_photo", lambda b, claimed=None: s.checked.append((b, claimed))
                        or {"category": "road_damage", "severity": 0.7, "matches_claim": True, "notes": "pothole"})
    monkeypatch.setattr(pipeline.geocode, "geocode", lambda text: s.geo)
    monkeypatch.setattr(pipeline.dedup, "embed", lambda texts: np.ones((len(texts), 4), np.float32) / 2)
    monkeypatch.setattr(pipeline.dedup, "find_duplicate", lambda conn, **kw: s.dup_calls.append(kw) or s.duplicate)
    monkeypatch.setattr(pipeline.db, "insert_report", lambda conn, **kw: s.reports.append(kw) or 100 + len(s.reports))
    monkeypatch.setattr(pipeline.db, "nearest_segment", lambda conn, lon, lat, mode=None, max_dist_m=20:
                        s.segments.append((lon, lat, mode, max_dist_m)) or 7)
    monkeypatch.setattr(pipeline.db, "insert_evidence", lambda conn, ev: s.evidence.append(ev) or 500 + len(s.evidence))
    return s


def test_process_report_located_via_pin(deps):
    res = deps.pipeline.process_report("conn", "Dziura!", pin=(21.0, 52.23), created_at=T0)
    assert set(res) == {"report_id", "evidence_id", "structured", "duplicate_of", "lon", "lat", "photo_url"}
    assert (res["lon"], res["lat"], res["report_id"], res["evidence_id"]) == (21.0, 52.23, 101, 501)
    assert res["structured"]["category"] == "road_damage" and res["duplicate_of"] is None
    rep = deps.reports[0]
    assert rep["location_confidence"] == 0.9 and rep["embedding"] == [0.5] * 4
    assert rep["created_at"] == T0 and rep["source"] == "web" and rep["duplicate_of"] is None
    assert deps.segments == [(21.0, 52.23, "road", 60)]
    ev: EvidenceIn = deps.evidence[0]
    assert ev.source == Source.REPORT and ev.type == IssueType.ROAD_DAMAGE
    assert ev.severity == pytest.approx(0.8) and ev.ts == T0 and ev.report_id == 101 and ev.segment_id == 7
    assert ev.details == {"kind": "report", "urgency": 4, "summary_en": "Large pothole", "hazard_to_people": True,
                          "location_confidence": 0.9, "location_text": "Marszałkowska przy Złotej"}
    assert deps.dup_calls[0]["category"] == "road_damage" and deps.dup_calls[0]["lon"] == 21.0


def test_process_report_located_via_geocode(deps):
    deps.triage = deps.triage.model_copy(update={"category": IssueType.TRAM_TRACK})
    deps.geo = (21.01, 52.22, 0.85)
    res = deps.pipeline.process_report("conn", "Tory stukają", pin=(21.5, 52.5), source="19115")
    assert (res["lon"], res["lat"]) == (21.01, 52.22)
    assert deps.reports[0]["location_confidence"] == 0.85 and deps.reports[0]["source"] == "19115"
    assert deps.segments[0][2:] == ("tram", 60)
    assert deps.evidence[0].ts.tzinfo is not None
    # a low-confidence geocode loses to the pin
    deps.geo = (21.01, 52.22, 0.3)
    res = deps.pipeline.process_report("conn", "Tory stukają", pin=(21.5, 52.5))
    assert (res["lon"], res["lat"]) == (21.5, 52.5)
    # a street-level geocode near the pin: the pin is the precise spot on that street
    deps.geo = (21.01, 52.22, 0.64)
    res = deps.pipeline.process_report("conn", "Tory stukają", pin=(21.012, 52.224))
    assert (res["lon"], res["lat"]) == (21.012, 52.224) and deps.reports[-1]["location_confidence"] == 0.9


def test_process_report_unlocated_creates_no_evidence(deps):
    deps.triage = deps.triage.model_copy(update={"location_text": None})
    res = deps.pipeline.process_report("conn", "Coś jest zepsute")
    assert res["evidence_id"] is None and res["lon"] is None and res["report_id"] == 101
    assert deps.reports[0]["lon"] is None and deps.reports[0]["location_confidence"] is None
    assert deps.evidence == [] and deps.segments == [] and deps.dup_calls == []


def test_process_report_duplicate_and_given_structure(deps):
    deps.duplicate = 42
    res = deps.pipeline.process_report("conn", "Znowu ta dziura", pin=MARSZ, structured=deps.triage)
    assert res["duplicate_of"] == 42 and deps.reports[0]["duplicate_of"] == 42
    assert res["evidence_id"] == 501  # duplicates still become evidence for fusion
    assert deps.structure_calls == 0


def test_process_report_photo(deps, monkeypatch):
    res = deps.pipeline.process_report("conn", "Dziura", pin=MARSZ, photo_bytes=b"RAW")
    assert deps.anonymized == [b"RAW"] and deps.checked == [(b"ANON-JPEG", IssueType.ROAD_DAMAGE)]
    assert res["photo_url"].startswith("/photos/") and res["photo_url"].endswith(".jpg")
    assert (deps.tmp / res["photo_url"].lstrip("/")).read_bytes() == b"ANON-JPEG"
    assert res["structured"]["photo_check"]["matches_claim"] is True
    assert deps.reports[0]["photo_url"] == res["photo_url"]

    def broken(b):
        raise ValueError("not an image")
    monkeypatch.setattr(deps.pipeline.vision, "anonymize", broken)
    res = deps.pipeline.process_report("conn", "Dziura", pin=MARSZ, photo_bytes=b"garbage")
    assert res["photo_url"] is None and "rejected" in res["structured"]["photo_check"]["notes"]


# ---------------------------------------------------------------- eval script

def test_eval_triage_on_fixture(hashing, monkeypatch, tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("eval_triage", REPO_ROOT / "scripts" / "eval_triage.py")
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    issues = [("road_damage", MARSZ, PARAPHRASES),
              ("waste", (21.0045, 52.2310), WASTE)]
    data = [{"text": t, "created_at": (T0 + timedelta(hours=i)).isoformat(), "true_issue_id": k,
             "true_category": cat, "lon": lon, "lat": lat, "street": "x"}
            for k, (cat, (lon, lat), texts) in enumerate(issues) for i, t in enumerate(texts)]
    path = tmp_path / "complaints.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    dept = {"road_damage": Department.ZDM, "waste": Department.STRAZ_MIEJSKA}
    monkeypatch.setattr(ev.structure, "structure", lambda text: TriageResult(
        category="waste" if "kosz" in text.lower() else "road_damage",
        department=dept["waste" if "kosz" in text.lower() else "road_damage"]))
    res = ev.main(["--data", str(path), "--json", "--workers", "2"])
    assert res["n"] == 5 and res["category_accuracy"] == 1.0 and res["routing_accuracy"] == 1.0
    assert res["dedup"]["ari"] == 1.0 and res["dedup"]["clusters"] == 2 and res["dedup"]["compression"] == 2.5
    assert json.loads(capsys.readouterr().out)["dedup"]["purity"] == 1.0
