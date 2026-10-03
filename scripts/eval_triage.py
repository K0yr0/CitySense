"""Measure triage quality on the synthetic 19115-style complaint set.

    .venv/bin/python scripts/eval_triage.py [--data data/complaints_synth.json] [--limit N]
                                            [--json] [--sweep] [--workers 8]

* category accuracy: structure(text).category vs true_category
* routing accuracy:  structure(text).department vs department rule(true_category)
* dedup quality:     greedy_cluster (embeddings + 50 m / 72 h / same predicted category rule)
                     on the TRUE lon/lat (= perfect geocoding) vs true_issue_id:
                     purity, inverse purity, ARI, complaints -> clusters compression.
Uses the Claude API when ANTHROPIC_API_KEY is set, else the keyword fallback.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from sklearn.metrics import adjusted_rand_score  # noqa: E402

from backend.config import settings  # noqa: E402
from backend.triage import dedup, structure  # noqa: E402

_FALLBACK_RULES = {"road_damage": "ZDM", "streetlight": "ZDM", "tram_track": "Tramwaje Warszawskie",
                   "flooding": "MPWiK", "waste": "Straż Miejska", "other": "inne"}


def department_for(category: str) -> str:
    try:
        from backend.fusion.routing import department_for as rule
        return str(rule(category))
    except ImportError:
        return _FALLBACK_RULES.get(category, "inne")


def purity(true: list, pred: list) -> float:
    """Share of items whose cluster's majority true label equals their own."""
    groups: dict = defaultdict(list)
    for t, p in zip(true, pred):
        groups[p].append(t)
    return sum(Counter(g).most_common(1)[0][1] for g in groups.values()) / len(true)


def dedup_metrics(records: list[dict], categories: list[str], emb: np.ndarray,
                  threshold: float | None = None) -> dict:
    recs = [{"category": c, "lon": r["lon"], "lat": r["lat"], "created_at": r["created_at"], "emb": e}
            for r, c, e in zip(records, categories, emb)]
    labels = dedup.greedy_cluster(recs, threshold_=threshold)
    true = [r["true_issue_id"] for r in records]
    n, k, k_true = len(records), len(set(labels)), len(set(true))
    return {"threshold": dedup.threshold() if threshold is None else threshold,
            "clusters": k, "true_issues": k_true,
            "purity": round(purity(true, labels), 4),
            "inverse_purity": round(purity(labels, true), 4),
            "ari": round(float(adjusted_rand_score(true, labels)), 4),
            "compression": round(n / k, 2), "ideal_compression": round(n / k_true, 2)}


def evaluate(records: list[dict], workers: int = 8, sweep: bool = False) -> dict:
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        triaged = list(pool.map(lambda r: structure.structure(r["text"]), records))
    t_structure = time.time() - t0
    pred_cat = [str(t.category) for t in triaged]
    true_cat = [r["true_category"] for r in records]
    cat_ok = [p == t for p, t in zip(pred_cat, true_cat)]
    route_ok = [str(t.department) == department_for(c) for t, c in zip(triaged, true_cat)]
    per_cat = {c: round(float(np.mean([ok for ok, t in zip(cat_ok, true_cat) if t == c])), 3)
               for c in sorted(set(true_cat))}

    t0 = time.time()
    emb = dedup.embed([r["text"] for r in records])
    t_embed = time.time() - t0
    result = {
        "n": len(records),
        "triage_backend": "claude" if settings.has_llm else "keyword",
        "embedding_backend": dedup.BACKEND,
        "category_accuracy": round(float(np.mean(cat_ok)), 4),
        "category_recall": per_cat,
        "routing_accuracy": round(float(np.mean(route_ok)), 4),
        "dedup": dedup_metrics(records, pred_cat, emb),
        "dedup_true_category": dedup_metrics(records, true_cat, emb),
        "seconds": {"structure": round(t_structure, 2), "embed": round(t_embed, 2)},
    }
    if sweep:
        result["sweep"] = [dedup_metrics(records, pred_cat, emb, thr)
                           for thr in np.round(np.arange(0.0, 0.95, 0.05), 2).tolist()]
    return result


def _print(res: dict) -> None:
    d, dt = res["dedup"], res["dedup_true_category"]
    print(f"CityEcho triage eval — {res['n']} complaints "
          f"(triage: {res['triage_backend']}, embeddings: {res['embedding_backend']})")
    print(f"  category accuracy  {res['category_accuracy']:.1%}")
    print("    per category     " + ", ".join(f"{c} {v:.0%}" for c, v in res["category_recall"].items()))
    print(f"  routing accuracy   {res['routing_accuracy']:.1%}")
    print(f"  dedup (thr {d['threshold']:.2f}, perfect geocoding, predicted category)")
    print(f"    clusters {d['clusters']} vs {d['true_issues']} true issues | purity {d['purity']:.3f} | "
          f"inverse purity {d['inverse_purity']:.3f} | ARI {d['ari']:.3f}")
    print(f"    compression {d['compression']:.1f} complaints/incident (ideal {d['ideal_compression']:.1f})")
    print(f"    with true category: ARI {dt['ari']:.3f}, clusters {dt['clusters']}")
    for row in res.get("sweep", []):
        print(f"    sweep thr {row['threshold']:.2f}: clusters {row['clusters']:4d} purity {row['purity']:.3f} "
              f"inv {row['inverse_purity']:.3f} ARI {row['ari']:.3f}")


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=settings.data_dir / "complaints_synth.json")
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N complaints")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON")
    ap.add_argument("--sweep", action="store_true", help="also sweep the similarity threshold")
    ap.add_argument("--workers", type=int, default=8, help="parallel structure() calls")
    args = ap.parse_args(argv)

    records = json.loads(args.data.read_text(encoding="utf-8"))
    if args.limit:
        records = records[: args.limit]
    res = evaluate(records, workers=args.workers, sweep=args.sweep)
    print(json.dumps(res, indent=2, ensure_ascii=False)) if args.json else _print(res)
    return res


if __name__ == "__main__":
    main()
