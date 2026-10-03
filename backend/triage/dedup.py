"""Report de-duplication: text embeddings + "same incident" rule.

Two reports describe the same incident when they share a category AND are
within `RADIUS_M` (haversine) AND arrived within `WINDOW_H` of each other AND
their embedding cosine similarity exceeds `SIMILARITY_THRESHOLD`.

Embeddings: sentence-transformers `settings.embedding_model` (multilingual-e5,
"query: " prefix, normalized) when installed; otherwise a char n-gram hashing
fallback (sklearn) on lowercased, diacritic-folded text. The threshold depends
on the backend — read `dedup.SIMILARITY_THRESHOLD` (or `threshold()`) at call time.
"""
from __future__ import annotations

import importlib.util
import logging
import math
import threading
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

import numpy as np

from backend import db
from backend.config import settings

log = logging.getLogger(__name__)

RADIUS_M = 50.0
WINDOW_H = 72.0
E5_THRESHOLD = 0.80
# Hashing calibration (scripts/eval_triage.py --sweep + 12 hand-written Polish paraphrase groups):
# paraphrase pairs 0.27–0.71, unrelated pairs median ≈ 0.18. After the 50 m / 72 h / category filter
# the text mostly guards against chance matches, and char n-grams cannot separate two different
# problems at the same address anyway (shared street words ≈ 0.6), so we favour recall:
# 0.20 keeps 100 % of paraphrases and gives ARI 0.95 on the 367 synthetic complaints (0.30 -> 0.75).
HASH_THRESHOLD = 0.20
HASH_FEATURES = 1024

_HAS_ST = importlib.util.find_spec("sentence_transformers") is not None
BACKEND = "e5" if _HAS_ST else "hashing"
SIMILARITY_THRESHOLD = E5_THRESHOLD if _HAS_ST else HASH_THRESHOLD

_model: Any = None  # SentenceTransformer, or False once loading failed
_hasher: Any = None
_lock = threading.Lock()


def _use_hashing(reason: str) -> None:
    global _model, BACKEND, SIMILARITY_THRESHOLD
    log.warning("embeddings: hashing fallback (%s)", reason)
    _model, BACKEND, SIMILARITY_THRESHOLD = False, "hashing", HASH_THRESHOLD


def _get_model() -> Any:
    """Load the sentence-transformers model once; False when unavailable."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                if not _HAS_ST:
                    _use_hashing("sentence-transformers not installed")
                else:
                    try:
                        from sentence_transformers import SentenceTransformer
                        _model = SentenceTransformer(settings.embedding_model)
                    except Exception as exc:  # no weights offline, etc.
                        _use_hashing(f"cannot load {settings.embedding_model}: {exc}")
    return _model


def threshold() -> float:
    """Cosine threshold for the active embedding backend."""
    _get_model()
    return SIMILARITY_THRESHOLD


def fold(text: str) -> str:
    """Lowercase and strip diacritics (ł has no Unicode decomposition, so map it by hand)."""
    text = text.lower().replace("ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _hash_embed(texts: list[str]) -> np.ndarray:
    global _hasher
    if _hasher is None:
        from sklearn.feature_extraction.text import HashingVectorizer
        _hasher = HashingVectorizer(analyzer="char_wb", ngram_range=(3, 5), n_features=HASH_FEATURES,
                                    alternate_sign=False, norm=None, lowercase=False)
    mat = _hasher.transform([fold(t) for t in texts]).toarray().astype(np.float32)
    return _l2(mat)


def _l2(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return mat / np.where(norms == 0, 1.0, norms)


def embed(texts: list[str]) -> np.ndarray:
    """(n, d) float32 L2-normalized embeddings of `texts`."""
    texts = [t or "" for t in texts]
    model = _get_model()
    if model:
        if not texts:
            return np.zeros((0, model.get_sentence_embedding_dimension()), dtype=np.float32)
        vecs = model.encode([f"query: {t}" for t in texts], normalize_embeddings=True,
                            convert_to_numpy=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)
    if not texts:
        return np.zeros((0, HASH_FEATURES), dtype=np.float32)
    return _hash_embed(texts)


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(min(1.0, a)))


def _as_dt(value: datetime | str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def cosine(a: Sequence[float] | np.ndarray, b: Sequence[float] | np.ndarray) -> float:
    a, b = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    if a.shape != b.shape:
        return 0.0  # embeddings from different backends are not comparable
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b) / denom if denom else 0.0


def same_incident(a: dict, b: dict, threshold_: float | None = None) -> bool:
    """Rule check on two report dicts with category, lon, lat, created_at, emb."""
    if a.get("category") != b.get("category"):
        return False
    if None in (a.get("lon"), a.get("lat"), b.get("lon"), b.get("lat")):
        return False
    if haversine_m(a["lon"], a["lat"], b["lon"], b["lat"]) > RADIUS_M:
        return False
    if abs(_as_dt(a["created_at"]) - _as_dt(b["created_at"])) > timedelta(hours=WINDOW_H):
        return False
    if a.get("emb") is None or b.get("emb") is None:
        return False
    return cosine(a["emb"], b["emb"]) > (threshold() if threshold_ is None else threshold_)


_CANDIDATES_SQL = """
select id, duplicate_of, embedding
from reports
where category = %(category)s
  and embedding is not null
  and geom is not null
  and ST_DWithin(geom::geography,
                 ST_SetSRID(ST_MakePoint(%(lon)s::float8, %(lat)s::float8), 4326)::geography,
                 %(radius)s::float8)
  and created_at between %(t_from)s::timestamptz and %(t_to)s::timestamptz
"""


def find_duplicate(conn, *, category: str, lon: float, lat: float, created_at: datetime,
                   embedding: np.ndarray | Sequence[float]) -> int | None:
    """Canonical id of the most similar earlier report of the same incident, else None."""
    created_at = _as_dt(created_at)
    window = timedelta(hours=WINDOW_H)
    rows = db.fetch_all(conn, _CANDIDATES_SQL, {
        "category": str(category), "lon": float(lon), "lat": float(lat), "radius": RADIUS_M,
        "t_from": created_at - window, "t_to": created_at + window})
    query = np.asarray(embedding, dtype=np.float32).ravel()
    rows = [r for r in rows if r.get("embedding") is not None and len(r["embedding"]) == query.size]
    if not rows or not np.any(query):
        return None
    mat = _l2(np.asarray([r["embedding"] for r in rows], dtype=np.float32))
    sims = mat @ (query / np.linalg.norm(query))
    best = int(np.argmax(sims))
    if sims[best] <= threshold():
        return None
    return int(rows[best]["duplicate_of"] or rows[best]["id"])


def greedy_cluster(records: list[dict], *, threshold_: float | None = None,
                   radius_m: float = RADIUS_M, window_h: float = WINDOW_H) -> list[int]:
    """Offline replay of the online dedup: process records by created_at; each one joins the
    cluster of its most similar earlier record that passes the rule, else starts a new cluster.
    Records need category, lon, lat, created_at, emb. Returns a label per record (input order)."""
    n = len(records)
    if n == 0:
        return []
    thr = threshold() if threshold_ is None else threshold_
    order = sorted(range(n), key=lambda i: _as_dt(records[i]["created_at"]))
    cats = np.array([str(records[i].get("category")) for i in order], dtype=object)
    lon = np.array([np.nan if records[i].get("lon") is None else records[i]["lon"] for i in order], float)
    lat = np.array([np.nan if records[i].get("lat") is None else records[i]["lat"] for i in order], float)
    ts = np.array([_as_dt(records[i]["created_at"]).timestamp() for i in order])
    emb = _l2(np.asarray([records[i]["emb"] for i in order], dtype=np.float32))
    lon_r, lat_r = np.radians(lon), np.radians(lat)

    cluster = np.empty(n, dtype=int)
    n_clusters = 0
    for k in range(n):
        ok = (cats[:k] == cats[k]) & (np.abs(ts[:k] - ts[k]) <= window_h * 3600)
        if k and not np.isnan(lon[k]):
            a = (np.sin((lat_r[:k] - lat_r[k]) / 2) ** 2
                 + np.cos(lat_r[k]) * np.cos(lat_r[:k]) * np.sin((lon_r[:k] - lon_r[k]) / 2) ** 2)
            dist = 2 * 6_371_000 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
            ok &= np.nan_to_num(dist, nan=np.inf) <= radius_m
            cand = np.flatnonzero(ok)
            if cand.size:
                sims = emb[cand] @ emb[k]
                best = int(np.argmax(sims))
                if sims[best] > thr:
                    cluster[k] = cluster[cand[best]]
                    continue
        cluster[k] = n_clusters
        n_clusters += 1

    labels = [0] * n
    for pos, i in enumerate(order):
        labels[i] = int(cluster[pos])
    return labels
