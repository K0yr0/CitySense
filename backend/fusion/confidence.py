"""Confidence engine: sensor confidence + trust-weighted citizen confidence -> incident status.

Every piece of evidence adds or removes points in log-odds space, starting from a prior
(how often a reported spot turns out to be a real problem). Points become a probability
through the logistic curve, so every number on the dashboard can be explained line by line:

    sensor points  = Σ detecting rides  SENSOR_HIT · (0.5 + 0.5·severity)
                     − SENSOR_MISS · capable rides that passed without detecting anything
    citizen points = Σ YES  CITIZEN_VOTE · 2·trust  −  Σ NO  CITIZEN_VOTE · 2·trust
                     (clamped to ±CITIZEN_CAP)
    confidence     = σ(logit(PRIOR) + sensor points + citizen points)

    confidence ≥ 0.85 -> verified,  ≥ 0.60 -> likely,  < 0.10 -> dismissed,  else candidate

The citizen cap encodes that thirty people repeating one complaint are correlated, not thirty
independent witnesses: the crowd alone reaches `likely`; `verified` needs a vehicle sensor to
agree (the verification loop) or several sensor rides. Trust is 0–1 (0.6 for newcomers), so a
proven contributor's answer weighs up to 2x and a repeatedly wrong one fades towards 0.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from backend.models import IncidentStatus

PRIOR = 0.25            # share of reported spots that are real before any evidence
SENSOR_HIT = 1.2        # points per detecting ride at full severity weight
SENSOR_MISS = 0.8       # points against per capable ride that passed without detecting
CITIZEN_VOTE = 0.6      # points per YES/NO from a contributor with trust 0.5
CITIZEN_CAP = 2.5       # max |citizen points|: the crowd alone cannot verify

LIKELY_AT = 0.60
VERIFIED_AT = 0.85
DISMISSED_BELOW = 0.10

TERMINAL = (IncidentStatus.VERIFIED, IncidentStatus.DISMISSED, IncidentStatus.CLOSED)


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, float(x)))


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def sensor_points(ride_severities: Iterable[float], misses: int) -> float:
    """One hit per detecting ride (weighted by its strongest severity), minus clean passes."""
    hits = sum(SENSOR_HIT * (0.5 + 0.5 * _clamp01(s)) for s in ride_severities)
    return hits - SENSOR_MISS * max(0, int(misses))


def trust_weight(trust: float) -> float:
    """Trust 0–1 -> vote multiplier 0–2 (0.5 = neutral)."""
    return 2.0 * _clamp01(trust)


def citizen_points(votes: Iterable[tuple[bool, float]]) -> float:
    """votes: (answer, contributor trust). YES adds, NO subtracts; total clamped to ±CITIZEN_CAP."""
    total = sum((1.0 if yes else -1.0) * CITIZEN_VOTE * trust_weight(trust) for yes, trust in votes)
    return max(-CITIZEN_CAP, min(CITIZEN_CAP, total))


@dataclass(frozen=True)
class Assessment:
    sensor_confidence: float | None   # None = no sensor data yet
    citizen_confidence: float | None  # None = no citizen responses yet
    confidence: float
    sensor_points: float
    citizen_points: float


def assess(ride_severities: Iterable[float], misses: int,
           votes: Iterable[tuple[bool, float]]) -> Assessment:
    """Combine both sources into one confidence (see module docstring)."""
    severities, votes = list(ride_severities), list(votes)
    s, c = sensor_points(severities, misses), citizen_points(votes)
    base = _logit(PRIOR)
    return Assessment(
        sensor_confidence=_sigmoid(base + s) if severities or misses > 0 else None,
        citizen_confidence=_sigmoid(base + c) if votes else None,
        confidence=_sigmoid(base + s + c),
        sensor_points=s,
        citizen_points=c,
    )


def status_for(confidence: float, current: str) -> str:
    """Status from confidence. verified / dismissed / closed are terminal (trust is settled then)."""
    if current in TERMINAL:
        return str(current)
    if confidence >= VERIFIED_AT:
        return IncidentStatus.VERIFIED.value
    if confidence < DISMISSED_BELOW:
        return IncidentStatus.DISMISSED.value
    if confidence >= LIKELY_AT:
        return IncidentStatus.LIKELY.value
    return IncidentStatus.CANDIDATE.value
