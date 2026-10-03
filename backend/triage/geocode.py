"""Free-text Warsaw location -> (lon, lat, confidence) via Nominatim.

* Bounded to Warsaw (`WARSAW_VIEWBOX`, `bounded=1`), `", Warszawa"` appended to the query.
  "ul."/leading prepositions are dropped; on no hit we retry once with Polish case endings made
  nominative ("Puławskiej 120" -> "Puławska 120").
* Confidence: POI/address ≈ 0.85+, street/square/intersection ≈ 0.6, district ≤ 0.4; hits whose
  name does not contain the query's place words are capped at 0.3.
* Nominatim usage policy: identifying User-Agent and at most 1 request/second
  (thread-safe `RateLimiter`).
* JSON file cache `data/cache/geocode.json` keyed by normalized text; misses
  (`null`) are cached too so we never ask twice. Transient errors are not cached.
* `settings.demo_mode` or any network error -> cache only. Never raises.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable

import httpx

from backend.config import settings

log = logging.getLogger(__name__)

WARSAW_VIEWBOX = "20.85,52.37,21.27,52.10"
MIN_INTERVAL_S = 1.0
TIMEOUT_S = 10.0

# Precise hits: buildings, house numbers, POIs, stops. Streets/intersections are "medium".
_POI_CLASSES = {"amenity", "shop", "building", "tourism", "leisure", "office", "public_transport",
                "historic", "man_made", "craft", "healthcare", "emergency"}
_POI_TYPES = {("highway", "bus_stop"), ("highway", "traffic_signals"), ("highway", "crossing"),
              ("highway", "platform"), ("railway", "tram_stop"), ("railway", "station"),
              ("railway", "halt"), ("railway", "platform"), ("place", "house")}
_STREET_TYPES = {("place", "square"), ("junction", "roundabout")}
# Name-only matches that say nothing about where the problem is (e.g. a board called "Ulica Puławska").
_JUNK_TYPES = {("tourism", "information"), ("tourism", "artwork"), ("advertising", "board")}
_INTERSECTION_RE = re.compile(r"\bróg\b|\brogu\b|skrzy[żz]owani|\s/\s|\s[x&]\s", re.IGNORECASE)
_STREET_PREFIX_RE = re.compile(r"(?<!\w)(?:ul\.|ulica|ulicy)\s*|^\s*(?:przy|na|obok|koło|kolo|w okolicy|okolice|"
                               r"naprzeciwko|naprzeciw)\s+", re.IGNORECASE)
# Words that carry no place name; the rest must appear in Nominatim's display_name.
_GENERIC = {"ulica", "ulicy", "przy", "obok", "kolo", "okolice", "okolicy", "naprzeciwko", "przed", "skrzyzowanie",
            "skrzyzowaniu", "rog", "rogu", "przystanek", "przystanku", "warszawa", "warszawie", "naprzeciw", "miedzy"}

# Tests swap this for httpx.MockTransport.
_transport: httpx.BaseTransport | None = None


class RateLimiter:
    """Spaces calls at least `min_interval` seconds apart across threads."""

    def __init__(self, min_interval: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.min_interval = min_interval
        self.clock, self.sleep = clock, sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:  # held while sleeping, so concurrent callers queue up
            now = self.clock()
            # Re-check after sleeping: on Windows time.sleep can wake a little before the coarse
            # (~15.6 ms) monotonic clock reaches the target, which would space calls too closely.
            while now < self._next:
                self.sleep(self._next - now)
                now = self.clock()
            self._next = now + self.min_interval


_limiter = RateLimiter(MIN_INTERVAL_S)
_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"path": None, "data": {}}


def normalize(text: str) -> str:
    """Cache key: lowercase, single spaces, no surrounding punctuation."""
    return re.sub(r"\s+", " ", text.lower()).strip(" ,.;:!?\"'")


def _cache_path() -> Path:
    return settings.cache_dir / "geocode.json"


def _load() -> dict[str, Any]:
    """In-memory view of the cache file (reloaded if settings.cache_dir changed). Call under lock."""
    path = _cache_path()
    if _cache["path"] != path:
        data: dict[str, Any] = {}
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("geocode cache unreadable (%s), starting empty", exc)
        _cache.update(path=path, data=data)
    return _cache["data"]


def _store(key: str, value: dict | None) -> None:
    with _cache_lock:
        data = _load()
        data[key] = value
        path = _cache["path"]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=0, sort_keys=True)
            os.replace(tmp, path)
        except OSError as exc:
            log.warning("could not write geocode cache: %s", exc)


def _fold(text: str) -> str:
    text = text.lower().replace("ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _name_match(text: str, display_name: str) -> float:
    """Share of the query's place words (4-char stems, so Polish cases still match) found in the hit."""
    words = [w for w in re.findall(r"[^\W\d_]{3,}", _fold(text)) if w not in _GENERIC]
    if not words:
        return 1.0
    name = _fold(display_name or "")
    return sum(w[:4] in name for w in words) / len(words)


def _confidence(hit: dict, text: str) -> float:
    """Map Nominatim rank/type/importance to 0–1. POI/address ≈ 0.85+, street ≈ 0.6, area ≤ 0.4."""
    cls, typ = hit.get("class", ""), hit.get("type", "")
    rank = int(hit.get("place_rank") or 0)
    if (cls, typ) in _JUNK_TYPES:
        base = 0.2
    elif (cls, typ) in _STREET_TYPES:
        base = 0.6
    elif (cls, typ) in _POI_TYPES or cls in _POI_CLASSES or rank >= 28:
        base = 0.85
    elif cls == "highway" or rank >= 26:
        base = 0.6
    elif rank >= 20:  # neighbourhood / quarter
        base = 0.35
    else:  # district, city
        base = 0.15
    importance = min(max(float(hit.get("importance") or 0.0), 0.0), 1.0)
    conf = min(1.0, base + 0.1 * importance)
    if _INTERSECTION_RE.search(text):  # Nominatim resolves only one of the streets
        conf = min(conf, 0.65)
    if _name_match(text, hit.get("display_name", "")) < 0.5:  # matched something else entirely
        conf = min(conf, 0.3)
    return round(conf, 2)


def _variants(text: str) -> list[str]:
    """Query strings to try in order: without "ul."/"ulica", then with Polish genitive/locative
    street adjectives turned nominative ("Kruczej 15" -> "Krucza 15"); Nominatim knows only the latter."""
    base = _STREET_PREFIX_RE.sub("", text).strip() or text.strip()
    nominative = re.sub(r"(\w{3,})ej\b", r"\1a", re.sub(r"(\w{2,}[kg])iej\b", r"\1a", base))
    return [base] if nominative == base else [base, nominative]


def _query(text: str) -> list[dict]:
    _limiter.wait()
    params = {"q": f"{text}, Warszawa", "format": "json", "limit": 1, "viewbox": WARSAW_VIEWBOX,
              "bounded": 1, "addressdetails": 0}
    headers = {"User-Agent": settings.nominatim_user_agent, "Accept-Language": "pl"}
    with httpx.Client(transport=_transport, timeout=TIMEOUT_S, headers=headers) as client:
        resp = client.get(settings.nominatim_url, params=params)
        resp.raise_for_status()
        return resp.json()


def _as_tuple(entry: dict | None) -> tuple[float, float, float] | None:
    return None if entry is None else (entry["lon"], entry["lat"], entry["confidence"])


def geocode(location_text: str | None) -> tuple[float, float, float] | None:
    """(lon, lat, confidence 0–1) for a Warsaw location description, or None."""
    if not location_text or not location_text.strip():
        return None
    key = normalize(location_text)
    with _cache_lock:
        data = _load()
        if key in data:
            return _as_tuple(data[key])
    if settings.demo_mode:
        return None
    try:
        for variant in _variants(location_text):
            hits = _query(variant)
            if not isinstance(hits, list):
                raise ValueError(f"unexpected Nominatim payload: {str(hits)[:100]}")
            if hits:
                break
    except (httpx.HTTPError, ValueError) as exc:  # transient: not cached
        log.info("geocode offline/failed for %r: %s", location_text, exc)
        return None
    except Exception as exc:  # never break the report pipeline
        log.warning("geocode unexpected error for %r: %s", location_text, exc)
        return None
    entry = None
    try:
        if hits:
            hit = hits[0]
            entry = {"lon": float(hit["lon"]), "lat": float(hit["lat"]),
                     "confidence": _confidence(hit, location_text),
                     "display_name": hit.get("display_name")}
    except (KeyError, TypeError, ValueError):
        entry = None
    _store(key, entry)
    return _as_tuple(entry)
