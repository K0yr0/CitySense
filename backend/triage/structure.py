"""Complaint triage: free text (mostly Polish 19115 style) -> `TriageResult`.

Claude path: one Messages API call constrained by structured outputs
(`output_config.format` = JSON schema of `_TriageOut`), validated with pydantic and
then with `TriageResult`; retried once. Department routing is enforced in code.
No API key / any failure -> deterministic keyword heuristic. `structure` never raises.

`call_claude` is also used by `vision.py` and `scripts/gen_complaints.py`.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from backend.config import settings
from backend.models import Department, IssueType, TriageResult

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)

ROUTING: dict[IssueType, Department] = {
    IssueType.ROAD_DAMAGE: Department.ZDM,
    IssueType.STREETLIGHT: Department.ZDM,
    IssueType.TRAM_TRACK: Department.TRAMWAJE,
    IssueType.FLOODING: Department.MPWIK,
    IssueType.WASTE: Department.STRAZ_MIEJSKA,
    IssueType.OTHER: Department.OTHER,
}

SYSTEM_PROMPT = """You are the triage assistant for Warsaw's 19115 city hotline. You receive one citizen \
complaint, usually in Polish (often informal, with slang, typos and missing diacritics, e.g. \
"dziura na ulicy", "znowu to samo przy Biedronce", "latarnia nie świeci"), sometimes in English.

Return ONLY the JSON object described by the schema, no other text.

Fields:
- category: road_damage (potholes, broken asphalt, sidewalk or curb damage), tram_track (tram rails, \
switches, tram track bed, tram overhead line), streetlight (street lamp out, dark street, flickering \
light), flooding (water on the street, blocked drains, sewer, manholes, burst pipes), waste (rubbish, \
overflowing bins, illegal dumping), other (anything else).
- department, by these routing rules: road / sidewalk / streetlight -> "ZDM"; tram tracks -> \
"Tramwaje Warszawskie"; water / sewer / flooding -> "MPWiK"; public order / waste -> "Straż Miejska"; \
everything else -> "inne".
- urgency: integer 1-5. 5 = risk to human life (e.g. open manhole, live wire, deep hole on a busy \
road at night), 4 = likely injury or accident, 3 = clear functional problem, 2 = nuisance, 1 = cosmetic.
- hazard_to_people: true when people (pedestrians, cyclists, drivers, children) could get hurt.
- location_text: the most specific place description, copied in the original language (street names \
with house numbers, intersections, landmarks such as "przy Biedronce" or "przystanek Centrum"). \
null when the complaint gives no usable place.
- summary_en: one short English sentence describing the problem and place.
- needs_clarification: true when the location or the problem is too vague to dispatch a crew."""


class _TriageOut(BaseModel):
    """What Claude must return (all fields required, unlike `TriageResult`)."""

    category: IssueType
    location_text: str | None
    urgency: int = Field(ge=1, le=5)
    hazard_to_people: bool
    department: Department
    summary_en: str
    needs_clarification: bool


# --------------------------------------------------------------------------- Claude client
@lru_cache(maxsize=1)
def _client() -> Any | None:
    """Anthropic client, or None without an API key / SDK."""
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic

        return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0, max_retries=2)
    except Exception as exc:  # pragma: no cover - SDK import problems
        log.warning("anthropic client unavailable: %s", exc)
        return None


def llm_available() -> bool:
    return _client() is not None


def _model_options(model: str) -> dict[str, Any]:
    """Model-dependent request knobs.

    * temperature 0 only where sampling params still exist (Opus 4.7+, Sonnet 5+, Fable/Mythos
      reject them with a 400; determinism there comes from the schema + prompt).
    * effort "low": classification-style work; Haiku 4.5 / Sonnet 4.5 don't accept effort.
    * server-side refusal fallbacks ("default" routing) on the 5.x models that support them.
    """
    opts: dict[str, Any] = {}
    if not re.search(r"opus-(4-[78]|5)|sonnet-5|fable|mythos", model):
        opts["extra_body"] = {"temperature": 0}
    if re.search(r"opus-(4-[5-8]|5)|sonnet-(4-6|5)|fable|mythos", model):
        opts["output_config"] = {"effort": "low"}
    if re.fullmatch(r"claude-(opus-5(-5)?|sonnet-5-5|fable-5-1)", model):
        opts["betas"] = ["server-side-fallback-2026-07-01"]
        opts["fallbacks"] = "default"
    return opts


def call_claude(system: str, content: str | list[dict], *, schema: type[M] | None = None,
                max_tokens: int = 4096) -> M | str:
    """One Claude call. With `schema`: structured JSON output validated into `schema`;
    otherwise the plain response text. Raises on any failure (callers own the fallback)."""
    client = _client()
    if client is None:
        raise RuntimeError("Claude unavailable (no ANTHROPIC_API_KEY)")
    import anthropic

    model = settings.anthropic_model
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": content}],
        **_model_options(model),
    }
    if schema is not None:
        kwargs["output_config"] = {
            **kwargs.get("output_config", {}),
            "format": {"type": "json_schema", "schema": anthropic.transform_schema(schema)},
        }
    api = client.beta.messages if "betas" in kwargs else client.messages
    resp = api.create(**kwargs)
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"Claude stopped with {resp.stop_reason}")
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    if not text:
        raise RuntimeError("empty Claude response")
    return schema.model_validate_json(text) if schema is not None else text


# --------------------------------------------------------------------------- public API
def structure(text: str) -> TriageResult:
    """Structure one complaint. Claude (validated, one retry) -> keyword heuristic. Never raises."""
    text = (text or "").strip()
    if not text:
        return heuristic_structure(text)
    if llm_available():
        for attempt in (1, 2):
            try:
                out = call_claude(SYSTEM_PROMPT, f"Complaint:\n{text}", schema=_TriageOut, max_tokens=4096)
                result = TriageResult.model_validate(out.model_dump())
                return _enforce_routing(result)
            except Exception as exc:
                log.warning("triage LLM attempt %d failed: %s", attempt, exc)
    return heuristic_structure(text)


def summarize_reports(texts: list[str]) -> str:
    """1–2 sentence English summary of merged reports; fallback: first text truncated."""
    texts = [t.strip() for t in texts if t and t.strip()]
    if not texts:
        return ""
    if llm_available():
        numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(texts[:60], 1))
        try:
            return str(call_claude(
                "You summarize citizen complaints (mostly Polish) that were merged into one city "
                "incident in Warsaw. Reply with 1-2 plain English sentences: what the problem is, "
                "where, how many people reported it, and any danger mentioned. No preamble.",
                f"{len(texts)} reports:\n{numbered}", max_tokens=2048))
        except Exception as exc:
            log.warning("summary LLM failed: %s", exc)
    first = re.sub(r"\s+", " ", texts[0])
    return first if len(first) <= 200 else first[:197].rstrip() + "..."


def _enforce_routing(result: TriageResult) -> TriageResult:
    """Department follows the category (§5.6); for `other` keep Claude's choice (e.g. public order)."""
    if result.category != IssueType.OTHER:
        result.department = ROUTING[result.category]
    return result


# --------------------------------------------------------------------------- keyword fallback
def fold(text: str) -> str:
    """Lowercase, strip diacritics (incl. ł), collapse whitespace: 'Oświetlenie' -> 'oswietlenie'."""
    text = unicodedata.normalize("NFKD", (text or "").lower().replace("ł", "l"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


# (pattern on folded text, weight). Stems match word prefixes.
_KEYWORDS: dict[IssueType, list[tuple[str, float]]] = {
    IssueType.TRAM_TRACK: [
        (r"\btor(y|ow|ach|ami|em)?\b", 2), (r"\btorowisk", 3), (r"\btramwaj", 2.5), (r"\bszyn", 2.5),
        (r"\brozjazd", 2), (r"\bzwrotnic", 2.5), (r"\btrakcj", 2), (r"\btram\b", 2),
        (r"\btrams?\b", 2), (r"\b(tram )?tracks?\b", 2), (r"\brails?\b", 2), (r"\bstuka", 1),
    ],
    IssueType.ROAD_DAMAGE: [
        (r"\bdziur", 2.5), (r"\bwyrw", 2.5), (r"\bjezdni", 1), (r"\bchodnik", 1.5), (r"\basfalt", 1.5),
        (r"\bnawierzchni", 1.5), (r"\bkolein", 2), (r"\bkrawezni", 1.5), (r"\bubyt", 1.5),
        (r"\bzapadl", 1), (r"\bpekniet", 1), (r"\bplyt", 1), (r"\bkostk", 1), (r"\blata(ni|nie)\b", 0.5),
        (r"\bpotholes?\b", 2.5), (r"\b(road|sidewalk|pavement|asphalt)\b", 1.5), (r"\bhole\b", 2),
    ],
    IssueType.STREETLIGHT: [
        (r"\blatarn", 3), (r"\bciemn", 2), (r"\boswietleni", 3), (r"\blamp", 2.5),
        (r"\bnie (s|za)?swieci", 2.5), (r"\bmruga", 1.5), (r"\bzgasl", 1.5), (r"\bswiatl", 1),
        (r"\bstreet ?lights?\b", 3), (r"\blights?\b", 1.5), (r"\bdark\b", 2), (r"\blamps?\b", 2.5),
    ],
    IssueType.FLOODING: [
        (r"\bzala(n|l)", 3), (r"\bzalew", 2.5), (r"\bwod(a|y|e|zie|ą|o)\b", 1.5), (r"\bkanaliz", 3),
        (r"\bstudzien", 2.5), (r"\bkaluz", 2), (r"\bpowodz", 3), (r"\bwylew", 1.5), (r"\bzapcha", 1.5),
        (r"\bodplyw", 2), (r"\brur(a|y|e)\b", 1.5), (r"\bhydrant", 2), (r"\bscieki", 2.5),
        (r"\bkratk", 1.5), (r"\bwybil", 1), (r"\bflood", 3), (r"\bwater\b", 1.5), (r"\bsewer", 3),
        (r"\bdrains?\b", 2), (r"\bmanhole", 2),
    ],
    IssueType.WASTE: [
        (r"\bsmiec", 3), (r"\bsmieci", 1), (r"\bodpad", 3), (r"\bkosz(e|a|u|y|ach|em)?\b", 2), (r"\bkontener", 2),
        (r"\bgruz", 2), (r"\bwysypisk", 3), (r"\bzasmieca", 2), (r"\bsmietnik", 3), (r"\bbutelk", 1),
        (r"\bworki? ze", 1.5), (r"\bopony", 1.5), (r"\bmebl", 1), (r"\btrash\b", 3), (r"\bgarbage\b", 3),
        (r"\bwaste\b", 3), (r"\blitter", 3), (r"\bbins?\b", 2), (r"\brubbish\b", 3), (r"\bdump", 2),
    ],
}
_KEYWORDS_RE = {cat: [(re.compile(p), w) for p, w in pats] for cat, pats in _KEYWORDS.items()}

_BASE_URGENCY = {IssueType.ROAD_DAMAGE: 3, IssueType.TRAM_TRACK: 3, IssueType.STREETLIGHT: 2,
                 IssueType.FLOODING: 3, IssueType.WASTE: 2, IssueType.OTHER: 2}
_HAZARD_RE = re.compile(
    r"niebezpiecz|wypad(e|ku|ki)|dzieci|dziecko|szkol|przedszkol|rowerzyst|pieszy|piesi|przewroc|"
    r"wywroc|upad|ranny|ranna|kolizj|potrac|stluczk|zlamal|skrecil|wpadl|urwal|zagraz|zagroz|"
    r"\bglebok|ogromn|olbrzym|dangerous|danger|accident|child|injur|fell|crash")
_LIFE_RE = re.compile(r"zagrozeni\w* zycia|zagraza\w* zyciu|smierteln|porazeni|\bprad|kabel|"
                      r"odkryt\w* studzien|otwart\w* studzien|bez pokrywy|life[- ]threatening|live wire")
_PRIORITY_RE = re.compile(r"\bpilne|\bpilnie|natychmiast|\bszybko\b|\burgent")

# Common Warsaw streets: regex on folded text -> canonical name (for lower-case / no-diacritics texts).
_STREETS: list[tuple[str, str]] = [
    (r"marszalkowsk", "Marszałkowska"), (r"pulawsk", "Puławska"), (r"grojeck", "Grójecka"),
    (r"jerozolimsk", "Aleje Jerozolimskie"), (r"daszynskiego", "Rondo Daszyńskiego"),
    (r"swietokrzysk", "Świętokrzyska"), (r"solidarnosci", "Aleja Solidarności"),
    (r"targow(a|ej|ą)\b", "Targowa"), (r"grochowsk", "Grochowska"), (r"nowy(m)? swi(at|ecie)", "Nowy Świat"),
    (r"krakowski\w* przedmiesc", "Krakowskie Przedmieście"), (r"emilii plater", "Emilii Plater"),
    (r"krolewsk", "Królewska"), (r"zlot(a|ej)\b", "Złota"), (r"chmieln", "Chmielna"), (r"wilcz(a|ej)\b", "Wilcza"),
    (r"hoz(a|ej)\b", "Hoża"), (r"towarow(a|ej)\b", "Towarowa"), (r"wolsk(a|iej)\b", "Wolska"),
    (r"gorczewsk", "Górczewska"), (r"jana pawla", "Jana Pawła II"), (r"andersa", "Andersa"),
    (r"okopow", "Okopowa"), (r"mokotowsk(a|iej)\b", "Mokotowska"), (r"rakowieck", "Rakowiecka"),
    (r"wawelsk", "Wawelska"), (r"banacha", "Banacha"), (r"zwirki i wigury", "Żwirki i Wigury"),
    (r"jagiellonsk", "Jagiellońska"), (r"radzyminsk", "Radzymińska"), (r"modlinsk", "Modlińska"),
    (r"ostrobramsk", "Ostrobramska"), (r"waszyngtona", "Aleja Waszyngtona"),
    (r"niepodleglosci", "Aleja Niepodległości"), (r"koszykow", "Koszykowa"), (r"belwedersk", "Belwederska"),
    (r"sobieskiego", "Sobieskiego"), (r"slowackiego", "Słowackiego"), (r"zbawiciela", "Plac Zbawiciela"),
    (r"konstytucji", "Plac Konstytucji"), (r"unii lubelskiej", "Plac Unii Lubelskiej"),
    (r"bankow(y|ym)\b", "Plac Bankowy"), (r"dmowskiego", "Rondo Dmowskiego"), (r"zabkowsk", "Ząbkowska"),
    (r"wiatraczn", "Wiatraczna"), (r"kasprzaka", "Kasprzaka"), (r"senatorsk", "Senatorska"),
    (r"zelazn(a|ej)\b", "Żelazna"), (r"rondzie onz|rondo onz", "Rondo ONZ"), (r"wislostrad", "Wisłostrada"),
]
_STREETS_RE = [(re.compile(r"\b(?:" + rx + r")\w*"), name) for rx, name in _STREETS]
_UP = "A-ZĄĆĘŁŃÓŚŹŻ"
_NAME = rf"[{_UP}][\w.\-]*(?:\s+(?:[{_UP}0-9][\w.\-]*|i|z|ze|im\.))*"
_STOP = {"jest", "nie", "się", "sie", "w", "na", "i", "a", "od", "do", "to", "ta", "tej", "ten", "koło",
         "kolo", "przy", "obok", "mojej", "naszej", "tutaj", "tu", "gdzie", "znowu", "też", "tez", "juz", "już"}
# Strong prefixes accept any case ("ul. kwiatowa 5"); weak ones need a capitalized name ("przy Biedronce").
_PREFIXED_RE = re.compile(
    r"(?i:\b(?:ul\.|ulic[aeyą]|al\.|alej[aię]|alei|aleje|pl\.|plac[ue]?|rond(?:o|a|zie)|mo[sś]t\w*))"
    r"\s+(?:ul\.\s*)?([\w.\-]+(?:\s+\d+\w?)?)")
_LANDMARK_RE = re.compile(
    r"(?i:\b(?:skrzy[zż]owani\w*|przystan\w*|na|przy|koło|kolo|obok|pod|naprzeciw(?:ko)?|róg|rog|"
    rf"w okolicy|okolice|przed))\s+(?:[a-ząćęłńóśźż]+\s+)?{_NAME}")
_HOUSE_NO_RE = re.compile(r"^\s*(\d{1,3}[a-zA-Z]?)\b")


def extract_location(text: str) -> str | None:
    """Crude place extraction: known street names, 'ul./plac/rondo X', 'przy/na/koło <Name>'."""
    folded = fold(text)
    hits = sorted((m.start(), m.end(), name) for rx, name in _STREETS_RE for m in rx.finditer(folded))
    streets: list[str] = []
    seen: set[str] = set()
    for _, end, name in hits:
        if name not in seen:
            seen.add(name)
            number = _HOUSE_NO_RE.match(folded[end:])
            streets.append(f"{name} {number.group(1)}" if number and not streets else name)
    if streets:
        return " / ".join(streets[:2])
    for m in _PREFIXED_RE.finditer(text):
        if m.group(1).lower().strip(".") not in _STOP and len(m.group(1)) >= 3:
            return m.group(0).strip(" ,.")
    m = _LANDMARK_RE.search(text)
    return m.group(0).strip(" ,.") if m else None


def classify(text: str) -> tuple[IssueType, float]:
    """Best keyword category and its score (0 -> other)."""
    folded = fold(text)
    scores = {cat: sum(w for rx, w in pats if rx.search(folded)) for cat, pats in _KEYWORDS_RE.items()}
    best = max(scores, key=lambda c: scores[c])
    return (best, scores[best]) if scores[best] > 0 else (IssueType.OTHER, 0.0)


_LABELS = {
    IssueType.ROAD_DAMAGE: "Road surface damage (pothole)",
    IssueType.TRAM_TRACK: "Tram track defect",
    IssueType.STREETLIGHT: "Streetlight not working",
    IssueType.FLOODING: "Flooding / drainage problem",
    IssueType.WASTE: "Waste / litter problem",
    IssueType.OTHER: "Citizen complaint",
}


def heuristic_structure(text: str) -> TriageResult:
    """Deterministic keyword triage (Polish + English, diacritic-insensitive). Never raises."""
    try:
        folded = fold(text)
        category, _ = classify(text)
        location = extract_location(text)
        hazard = bool(_HAZARD_RE.search(folded))
        life = bool(_LIFE_RE.search(folded))
        urgency = _BASE_URGENCY[category] + hazard + (2 if life else 0) + bool(_PRIORITY_RE.search(folded))
        urgency = max(1, min(5, urgency))
        en = _LABELS[category]
        return TriageResult(
            category=category,
            location_text=location,
            urgency=urgency,
            hazard_to_people=hazard or life,
            department=ROUTING[category],
            summary_en=f"{en} reported" + (f" at {location}." if location else "."),
            needs_clarification=location is None or category == IssueType.OTHER,
        )
    except Exception as exc:  # pragma: no cover - defensive, the fallback must never fail
        log.error("heuristic triage failed: %s", exc)
        return TriageResult(needs_clarification=True, summary_en="Citizen complaint.")


if __name__ == "__main__":  # quick manual check: python -m backend.triage.structure "dziura na Puławskiej"
    import sys

    print(json.dumps(structure(" ".join(sys.argv[1:])).model_dump(mode="json"), ensure_ascii=False, indent=2))
