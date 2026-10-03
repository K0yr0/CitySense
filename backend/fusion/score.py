"""Explainable incident priority score (spec §C2), small enough to fit on one pitch slide.

    score = ( 0.35 · sensor_severity                 (0–1, strongest sensor peak)
            + 0.25 · log(1 + reports) / log(51)      (saturates at 50 reports)
            + 0.20 · max_urgency / 5                 (LLM triage urgency 1–5)
            + 0.20 · vulnerability )                 (school/hospital/stop/cycleway within 100 m)
            × 1.5 if sensors and citizens agree

The range is 0–1.0 for a single source and 0–1.5 when both sources agree.
"""
from __future__ import annotations

import math
from typing import Any

W_SENSOR = 0.35
W_REPORTS = 0.25
W_URGENCY = 0.20
W_VULNERABILITY = 0.20
AGREEMENT_MULTIPLIER = 1.5
REPORTS_SATURATION = 50  # log(1+n)/log(1+50) reaches 1.0 at 50 reports and is capped there
MAX_URGENCY = 5

FORMULA = (
    "(0.35·sensor_severity + 0.25·log(1+reports)/log(51) + 0.20·max_urgency/5 "
    "+ 0.20·vulnerability) × 1.5 if both sources agree"
)


def _clamp01(x: Any) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(x) else max(0.0, min(1.0, x))


def _nonneg_int(x: Any) -> int:
    try:
        return max(0, int(x))
    except (TypeError, ValueError):
        return 0


def score_breakdown(*, sensor_severity: float, report_count: int, max_urgency: int,
                    vulnerability: float, both_sources: bool) -> dict:
    """Every term of the score with its raw input, normalized value (0–1), weight and points."""
    reports = _nonneg_int(report_count)
    urgency = min(MAX_URGENCY, _nonneg_int(max_urgency))
    rows = [
        ("sensor_severity", "Sensor severity", sensor_severity, _clamp01(sensor_severity), W_SENSOR),
        ("reports", "Citizen reports", reports,
         min(1.0, math.log1p(reports) / math.log1p(REPORTS_SATURATION)), W_REPORTS),
        ("urgency", "Max urgency (1–5)", urgency, urgency / MAX_URGENCY, W_URGENCY),
        ("vulnerability", "Vulnerable place nearby", vulnerability, _clamp01(vulnerability), W_VULNERABILITY),
    ]
    terms = [
        {"name": name, "label": label, "input": raw, "normalized": round(norm, 4),
         "weight": weight, "points": round(weight * norm, 4)}
        for name, label, raw, norm, weight in rows
    ]
    base = sum(weight * norm for *_, norm, weight in rows)
    multiplier = AGREEMENT_MULTIPLIER if both_sources else 1.0
    return {
        "terms": terms,
        "base": round(base, 4),
        "both_sources": bool(both_sources),
        "multiplier": multiplier,
        "score": round(base * multiplier, 4),
        "formula": FORMULA,
    }


def priority_score(*, sensor_severity: float, report_count: int, max_urgency: int,
                   vulnerability: float, both_sources: bool) -> float:
    """Priority in ≈ 0–1.5 (higher = more urgent); see the module docstring."""
    return score_breakdown(sensor_severity=sensor_severity, report_count=report_count,
                           max_urgency=max_urgency, vulnerability=vulnerability,
                           both_sources=both_sources)["score"]
