"""Tests for backend.triage.structure / vision and scripts/gen_complaints.py (no network)."""
from __future__ import annotations

import dataclasses
import importlib.util
import io
import json
from datetime import datetime, timedelta, timezone

import anthropic
import httpx2
import numpy as np
import pytest
from PIL import Image

from backend.config import REPO_ROOT, settings
from backend.models import Department, IssueType, TriageResult
from backend.triage import structure as st
from backend.triage import vision

# ---------------------------------------------------------------------------- keyword fallback
SAMPLES = [  # (text, expected category)
    ("dziura na ulicy", "road_damage"),
    ("Ogromna dziura w jezdni na Puławskiej, auta wpadają kołami", "road_damage"),
    ("wyrwa w asfalcie przy przejsciu, niebezpiecznie", "road_damage"),
    ("Uszkodzony chodnik na Grochowskiej, płyty powyrywane", "road_damage"),
    ("koleiny na jezdni, nie da sie jechac", "road_damage"),
    ("Zapadnięta nawierzchnia przy Rondzie Daszyńskiego", "road_damage"),
    ("Huge pothole on Marszałkowska", "road_damage"),
    ("tory tramwajowe strasznie stukaja na Marszalkowskiej", "tram_track"),
    ("Pęknięta szyna przy przystanku Centrum, tramwaj podskakuje", "tram_track"),
    ("torowisko sie zapada miedzy szynami", "tram_track"),
    ("Zwrotnica na Placu Narutowicza hałasuje całą noc", "tram_track"),
    ("tramwaj szarpie na torach przy Hali Mirowskiej", "tram_track"),
    ("The tram tracks are broken near Plac Zawiszy", "tram_track"),
    ("latarnia nie świeci", "streetlight"),
    ("Latarnia nie swieci od tygodnia przy szkole", "streetlight"),
    ("ciemno jak w lesie, oswietlenie nie dziala", "streetlight"),
    ("Zgasły lampy na przejściu dla pieszych", "streetlight"),
    ("brak oświetlenia na Rakowieckiej", "streetlight"),
    ("Streetlight is out on Słowackiego", "streetlight"),
    ("zalana ulica po deszczu, woda po kostki", "flooding"),
    ("Zatkana studzienka kanalizacyjna na Okopowej", "flooding"),
    ("cofa sie kanalizacja, smierdzi sciekami", "flooding"),
    ("Woda wybija ze studzienki przy Targowej", "flooding"),
    ("Zalane przejście podziemne przy Dworcu Zachodnim", "flooding"),
    ("Flooded street after rain, drains blocked", "flooding"),
    ("śmieci leżą od tygodnia przy kontenerach", "waste"),
    ("Przepełnione kosze na śmieci na Nowym Świecie", "waste"),
    ("dzikie wysypisko, gruz i stare meble w lesie", "waste"),
    ("odpady i butelki wszędzie koło przystanku", "waste"),
    ("Rubbish everywhere, bins overflowing", "waste"),
    ("glośna muzyka w nocy u sąsiada", "other"),
    ("po prostu koszmar, nikt nic nie robi", "other"),
]


def test_keyword_fallback_accuracy():
    results = [st.heuristic_structure(text) for text, _ in SAMPLES]
    cat_ok = sum(r.category.value == want for r, (_, want) in zip(results, SAMPLES))
    dept_ok = sum(r.department == st.ROUTING[IssueType(want)] for r, (_, want) in zip(results, SAMPLES))
    assert cat_ok / len(SAMPLES) >= 0.85, [(t, r.category.value) for r, (t, _) in zip(results, SAMPLES)]
    assert dept_ok / len(SAMPLES) >= 0.85


def test_routing_and_location_extraction():
    r = st.heuristic_structure("Ogromna dziura na Marszałkowskiej 140, niebezpiecznie! Dzieci chodzą tędy do szkoły")
    assert (r.category, r.department, r.location_text) == (IssueType.ROAD_DAMAGE, Department.ZDM, "Marszałkowska 140")
    assert r.urgency >= 4 and r.hazard_to_people and not r.needs_clarification
    assert st.heuristic_structure("znowu to samo przy Biedronce").location_text == "przy Biedronce"
    assert st.heuristic_structure("tory na skrzyzowaniu marszalkowskiej i swietokrzyskiej").location_text == \
        "Marszałkowska / Świętokrzyska"
    assert st.heuristic_structure("smieci przy ul. kwiatowa 5").location_text == "ul. kwiatowa 5"
    vague = st.heuristic_structure("latarnia nie świeci")
    assert vague.location_text is None and vague.needs_clarification
    assert st.heuristic_structure("Zatkana studzienka").department == Department.MPWIK
    assert st.heuristic_structure("śmieci").department == Department.STRAZ_MIEJSKA
    assert st.heuristic_structure("tory").department == Department.TRAMWAJE
    life = st.heuristic_structure("otwarta studzienka bez pokrywy na Grójeckiej")
    assert life.urgency == 5 and life.hazard_to_people
    assert st.fold("Łódź Oświetlenie ŻÓŁĆ") == "lodz oswietlenie zolc"


def test_structure_never_raises_and_falls_back(monkeypatch):
    monkeypatch.setattr(st, "_client", lambda: None)
    for text in ["", "   ", "dziura", "x" * 5000, "🙂🙂🙂"]:
        assert isinstance(st.structure(text), TriageResult)
    assert st.structure("latarnia nie świeci").category == IssueType.STREETLIGHT


# ---------------------------------------------------------------------------- mocked Claude
def _message(text: str, stop_reason: str = "end_turn") -> dict:
    return {"id": "msg_test", "type": "message", "role": "assistant", "model": "test",
            "content": [{"type": "text", "text": text}], "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 20}}


class FakeAPI:
    """Real anthropic.Anthropic client wired to an httpx2.MockTransport that replays canned responses."""

    def __init__(self, responses: list[tuple[int, dict]]):
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []
        self.client = anthropic.Anthropic(
            api_key="test-key", max_retries=0,
            http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(self._handle)))

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        status, body = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return httpx2.Response(status, json=body)

    def body(self, i: int = 0) -> dict:
        return json.loads(self.requests[i].content)


@pytest.fixture
def fake_claude(monkeypatch):
    def install(responses, model="claude-opus-5-5"):
        api = FakeAPI(responses)
        monkeypatch.setattr(st, "_client", lambda: api.client)
        monkeypatch.setattr(st, "settings", dataclasses.replace(settings, anthropic_api_key="test-key",
                                                                anthropic_model=model))
        return api
    return install


GOOD = {"category": "tram_track", "location_text": "Marszałkowska róg Świętokrzyskiej", "urgency": 4,
        "hazard_to_people": True, "department": "ZDM",  # wrong on purpose: routing is enforced in code
        "summary_en": "Broken tram rail at Marszałkowska / Świętokrzyska.",
        "needs_clarification": False}


def test_llm_structured_output_path(fake_claude):
    api = fake_claude([(200, _message(json.dumps(GOOD, ensure_ascii=False)))])
    r = st.structure("szyna pęknięta na Marszałkowskiej przy Świętokrzyskiej!!")
    assert r.category == IssueType.TRAM_TRACK and r.urgency == 4 and r.hazard_to_people
    assert r.department == Department.TRAMWAJE
    assert r.location_text == GOOD["location_text"] and r.summary_tr == ""  # no Turkish output any more
    body, req = api.body(), api.requests[0]
    assert body["model"] == "claude-opus-5-5" and "temperature" not in body  # sampling params 400 on Opus 5.5
    assert body["output_config"]["effort"] == "low"
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["additionalProperties"] is False
    assert set(fmt["schema"]["required"]) == set(TriageResult.model_fields) - {"summary_tr"}
    assert body["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in req.headers["anthropic-beta"]
    assert "19115" in body["system"] and "Tramwaje Warszawskie" in body["system"]


def test_llm_retry_once_then_success(fake_claude):
    bad = dict(GOOD, urgency=9)  # violates 1..5 -> pydantic validation error
    api = fake_claude([(200, _message(json.dumps(bad))), (200, _message(json.dumps(GOOD)))])
    assert st.structure("tory").summary_en.startswith("Broken tram rail")
    assert len(api.requests) == 2


@pytest.mark.parametrize("responses", [
    [(200, _message("not json at all"))],
    [(500, {"type": "error", "error": {"type": "api_error", "message": "boom"}})],
    [(200, _message("", stop_reason="refusal"))],
])
def test_llm_failures_fall_back_to_keywords(fake_claude, responses):
    api = fake_claude(responses)
    r = st.structure("Zatkana studzienka kanalizacyjna na Okopowej")
    assert r.category == IssueType.FLOODING and r.department == Department.MPWIK
    assert r.location_text == "Okopowa"
    assert len(api.requests) == 2  # first try + one retry


def test_temperature_zero_on_models_that_support_it(fake_claude):
    api = fake_claude([(200, _message(json.dumps(GOOD)))], model="claude-haiku-4-5")
    st.structure("tory")
    body = api.body()
    assert body["temperature"] == 0 and "fallbacks" not in body and "effort" not in body["output_config"]
    assert "anthropic-beta" not in api.requests[0].headers


def test_summarize_reports(monkeypatch, fake_claude):
    monkeypatch.setattr(st, "_client", lambda: None)
    assert st.summarize_reports([]) == ""
    long = "dziura " * 100
    assert st.summarize_reports([long, "b"]).endswith("...") and len(st.summarize_reports([long])) <= 200
    api = fake_claude([(200, _message("Twelve residents report a deep pothole on Puławska."))])
    assert st.summarize_reports(["dziura na Puławskiej"] * 12) == "Twelve residents report a deep pothole on Puławska."
    assert "12 reports" in api.body()["messages"][0]["content"]


# ---------------------------------------------------------------------------- vision
def _jpeg_with_exif(size=(60, 40)) -> bytes:
    rng = np.random.default_rng(0)
    img = Image.fromarray(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8))
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90° CW on display
    exif[0x010F] = "PhoneMaker"
    exif[0x8825] = {1: "N", 2: (52.0, 13.0, 50.0)}  # GPS IFD
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def test_anonymize_strips_exif_and_applies_orientation(tmp_path):
    raw = _jpeg_with_exif()
    path = tmp_path / "in.jpg"
    path.write_bytes(raw)
    assert len(Image.open(path).getexif()) > 0
    out = vision.anonymize(raw)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG" and img.size == (40, 60)  # rotated upright
    assert len(img.getexif()) == 0 and "exif" not in img.info
    assert b"PhoneMaker" not in out


def test_anonymize_blurs_detected_regions(monkeypatch):
    rng = np.random.default_rng(1)
    src = Image.fromarray(rng.integers(0, 255, (200, 200, 3), dtype=np.uint8))
    buf = io.BytesIO()
    src.save(buf, format="PNG")
    monkeypatch.setattr(vision, "_detect_regions", lambda rgb: [(50, 50, 80, 80)])
    out = np.asarray(Image.open(io.BytesIO(vision.anonymize(buf.getvalue()))).convert("L"), dtype=float)
    assert out[60:120, 60:120].std() < 0.4 * out[150:200, 150:200].std()


def test_anonymize_rejects_non_images_and_cascades_load():
    with pytest.raises(ValueError):
        vision.anonymize(b"definitely not an image")
    import cv2

    if not hasattr(cv2, "CascadeClassifier"):
        pytest.skip(f"OpenCV {cv2.__version__} has no Haar cascades (pin opencv-python-headless<5)")
    assert len(vision._cascades()) == 2 and vision.blur_available()


def test_check_photo_fallback_without_key(monkeypatch):
    monkeypatch.setattr(st, "_client", lambda: None)
    img = _jpeg_with_exif()
    assert vision.check_photo(img) == {"category": "other", "severity": 0.5, "matches_claim": None,
                                       "notes": "vision unavailable"}
    assert vision.check_photo(img, IssueType.WASTE)["category"] == IssueType.WASTE
    assert vision.check_photo(b"garbage", "not-a-type")["notes"] == "vision unavailable"


def test_check_photo_with_mocked_claude(fake_claude):
    reply = {"category": "road_damage", "severity": 0.8, "notes": "Deep pothole on asphalt."}
    api = fake_claude([(200, _message(json.dumps(reply)))])
    res = vision.check_photo(_jpeg_with_exif(), IssueType.ROAD_DAMAGE)
    assert res == {"category": IssueType.ROAD_DAMAGE, "severity": 0.8, "matches_claim": True,
                   "notes": "Deep pothole on asphalt."}
    image_block = api.body()["messages"][0]["content"][0]
    assert image_block["type"] == "image" and image_block["source"]["media_type"] == "image/jpeg"
    fake_claude([(200, _message(json.dumps(reply)))])
    assert vision.check_photo(_jpeg_with_exif(), IssueType.WASTE)["matches_claim"] is False


# ---------------------------------------------------------------------------- synthetic complaints
def _gen_module():
    spec = importlib.util.spec_from_file_location("gen_complaints", REPO_ROOT / "scripts" / "gen_complaints.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_gen_complaints_shape_and_counts():
    gen = _gen_module()
    now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    stats: dict = {}
    recs = gen.generate(seed=7, now=now, stats=stats)
    assert 300 <= len(recs) <= 500 and stats["spots"] == 40
    keys = {"text", "created_at", "true_issue_id", "true_category", "lon", "lat", "street"}
    assert all(set(r) == keys for r in recs)
    per_spot: dict[int, int] = {}
    for r in recs:
        per_spot[r["true_issue_id"]] = per_spot.get(r["true_issue_id"], 0) + 1
        ts = datetime.fromisoformat(r["created_at"])
        assert ts.tzinfo is not None and now - timedelta(days=10.5) <= ts <= now
        assert 20.85 < r["lon"] < 21.27 and 52.10 < r["lat"] < 52.37 and r["text"].strip()
    assert len(per_spot) == 40 and min(per_spot.values()) >= 1 and max(per_spot.values()) <= 40
    assert {r["true_category"] for r in recs} == {c.value for c in IssueType} - {"other"}
    assert 0.12 <= stats["vague"] / len(recs) <= 0.28
    assert len({r["text"] for r in recs}) / len(recs) > 0.9  # texts really vary
    corridor = {s[:3] for s in gen.SPOTS
                if 52.2105 <= s[2] <= 52.2440 and 21.000 <= s[1] <= 21.024 and "Marsza" in "".join(s[5])}
    assert len(corridor) >= 6
    assert gen.generate(seed=7, now=now) == recs  # deterministic


def test_committed_synthetic_file_matches_contract():
    path = REPO_ROOT / "data" / "complaints_synth.json"
    if not path.exists():
        pytest.skip("run scripts/gen_complaints.py first")
    recs = json.loads(path.read_text(encoding="utf-8"))
    assert 300 <= len(recs) <= 500 and len({r["true_issue_id"] for r in recs}) == 40
    acc = sum(st.heuristic_structure(r["text"]).category.value == r["true_category"] for r in recs) / len(recs)
    assert acc >= 0.85
