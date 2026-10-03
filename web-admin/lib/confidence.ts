// Mirror of backend/fusion/confidence.py + trust.py (keep the constants in sync).
// Used by the demo fixtures and by the "how is this computed" breakdown on the incident page.
import type { IncidentStatus } from "./types";

export const PRIOR = 0.25;
export const SENSOR_HIT = 1.2;
export const SENSOR_MISS = 0.8;
export const CITIZEN_VOTE = 0.6;
export const CITIZEN_CAP = 2.5;
export const LIKELY_AT = 0.6;
export const VERIFIED_AT = 0.85;
export const DISMISSED_BELOW = 0.1;
export const DEFAULT_TRUST = 0.6;

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const logit = (p: number) => Math.log(p / (1 - p));
const sigmoid = (x: number) => 1 / (1 + Math.exp(-x));

export type Vote = { yes: boolean; trust: number };

export function sensorPoints(rideSeverities: number[], misses: number): number {
  const hits = rideSeverities.reduce((sum, s) => sum + SENSOR_HIT * (0.5 + 0.5 * clamp01(s)), 0);
  return hits - SENSOR_MISS * Math.max(0, misses);
}

export function citizenPoints(votes: Vote[]): number {
  const total = votes.reduce((sum, v) => sum + (v.yes ? 1 : -1) * CITIZEN_VOTE * 2 * clamp01(v.trust), 0);
  return Math.max(-CITIZEN_CAP, Math.min(CITIZEN_CAP, total));
}

export interface Assessment {
  sensor_confidence: number | null;
  citizen_confidence: number | null;
  confidence: number;
  sensor_points: number;
  citizen_points: number;
}

export function assess(rideSeverities: number[], misses: number, votes: Vote[]): Assessment {
  const s = sensorPoints(rideSeverities, misses);
  const c = citizenPoints(votes);
  const base = logit(PRIOR);
  return {
    sensor_confidence: rideSeverities.length || misses > 0 ? sigmoid(base + s) : null,
    citizen_confidence: votes.length ? sigmoid(base + c) : null,
    confidence: sigmoid(base + s + c),
    sensor_points: s,
    citizen_points: c,
  };
}

export function statusFor(confidence: number, current: IncidentStatus | null = null): IncidentStatus {
  if (current === "verified" || current === "dismissed" || current === "closed") return current;
  if (confidence >= VERIFIED_AT) return "verified";
  if (confidence < DISMISSED_BELOW) return "dismissed";
  if (confidence >= LIKELY_AT) return "likely";
  return "candidate";
}

/** Beta(3, 2) posterior mean: 0.6 for a newcomer, rises when right, falls when wrong. */
export function trustFromCounts(correct: number, incorrect: number): number {
  return (correct + 3) / (correct + incorrect + 5);
}
