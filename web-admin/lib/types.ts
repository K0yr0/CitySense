// Mirrors docs/ARCHITECTURE.md §6 (HTTP API JSON shapes). Timestamps are ISO-8601 strings.

export type IssueType = "road_damage" | "tram_track" | "streetlight" | "flooding" | "waste" | "other";
export type Source = "sensor" | "report";
export type Mode = "road" | "tram";
export type Department = "ZDM" | "Tramwaje Warszawskie" | "MPWiK" | "Straż Miejska" | "inne";
/** Confidence-driven lifecycle: candidate -> likely -> verified (or dismissed); closed = handled by the city. */
export type IncidentStatus = "candidate" | "likely" | "verified" | "dismissed" | "closed";
export type CitizenAnswer = "yes" | "no";
export type VehicleKind = "tram" | "bus";

/** GET /segments -> {"segments": Segment[]} */
export interface Segment {
  id: number;
  mode: Mode;
  health: number | null; // 0 (bad) .. 1 (good); null = not measured
  rides: number;
  path: [number, number][]; // [lon, lat]
}

/** GET /incidents -> {"incidents": IncidentSummary[]} (sorted by score desc) */
export interface IncidentSummary {
  id: number;
  type: IssueType;
  status: IncidentStatus;
  score: number; // ≈ 0–1.5
  department: Department;
  lon: number;
  lat: number;
  address: string | null;
  report_count: number;
  sensor_count: number;
  sensor_rides: number;
  sensor_confirmed: boolean;
  found_before_report: boolean;
  has_sensor: boolean;
  has_report: boolean;
  max_severity: number | null;
  max_urgency: number | null;
  first_seen: string;
  last_seen: string;
  verify_vehicle: string | null; // e.g. "tram 17"
  verify_eta_min: number | null;
  confidence: number; // 0–1, confidence engine (sensor + trust-weighted citizen evidence)
  sensor_confidence: number | null; // null = no sensor data yet
  citizen_confidence: number | null; // null = no citizen answers yet
  yes_count: number; // citizen YES (reports + explicit answers)
  no_count: number; // citizen NO answers
  sensor_misses: number; // capable vehicles that passed without detecting anything
  awaiting_verification: boolean; // a vehicle was asked to check and has not passed yet
}

export interface IncidentReport {
  id: number;
  raw_text: string;
  summary_en: string | null;
  urgency: number | null;
  created_at: string;
  photo_url: string | null;
}

export interface Evidence {
  id: number;
  source: Source;
  type: IssueType;
  severity: number;
  ts: string;
  ride_id: number | null;
  report_id: number | null;
  details: Record<string, unknown>;
}

export type TimelineKind =
  | "first_report"
  | "report"
  | "sensor"
  | "proactive"
  | "verification_requested"
  | "sensor_miss"
  | "response"
  | "verified"
  | "dismissed";

export interface TimelineEvent {
  ts: string;
  kind: TimelineKind;
  label: string;
}

export interface Signal {
  fs: number;
  values: number[];
  peak_index: number;
}

/** GET /incidents/{id} */
export interface IncidentDetail extends IncidentSummary {
  summary: string | null;
  reports: IncidentReport[];
  evidence: Evidence[];
  timeline: TimelineEvent[];
  signal: Signal | null;
}

/** POST /incidents/{id}/verify */
export interface VerifyResult {
  incident_id: number;
  status: IncidentStatus | null;
  vehicle: string | null;
  eta_min: number | null;
}

/** POST /reports, GET /reports/{id}/status */
export interface ReportStatus {
  report_id: number;
  incident_id: number | null;
  status: IncidentStatus | null;
  category: IssueType;
  department: Department;
  others_count: number;
  sensor_confirmed: boolean;
  verify_vehicle: string | null;
  verify_eta_min: number | null;
  confidence: number | null;
  contributor_trust: number | null; // the reporter's current trust (0–1)
  message: string;
}

/** POST /incidents/{id}/responses body {answer, contributor} -> */
export interface CitizenResponseResult {
  incident_id: number;
  status: IncidentStatus;
  confidence: number;
  sensor_confidence: number | null;
  citizen_confidence: number | null;
  yes_count: number;
  no_count: number;
  contributor_trust: number | null;
}

/** GET /stats */
export interface Stats {
  reports_total: number;
  incidents_total: number;
  found_before_report: number;
  candidate_total: number;
  likely_total: number;
  verified_total: number;
  awaiting_verification: number;
  contributors_total: number;
  avg_verification_min: number | null;
  rides_total: number;
  segments_measured: number;
}

/** GET /vehicles/live -> {"vehicles": Vehicle[]} */
export interface Vehicle {
  id: string | number;
  line: string;
  lon: number;
  lat: number;
  ts: string;
  kind: VehicleKind;
}

/** One accelerometer sample streamed by the /ride recorder. */
export interface RideSample {
  t: number; // seconds since start
  ax: number; // m/s², accelerationIncludingGravity
  ay: number;
  az: number;
  lat: number;
  lon: number;
  speed_kmh: number;
  lux?: number;
}

/** POST /rides/stream body */
export interface RideStreamRequest {
  session_id: string;
  vehicle_line: string;
  mode: Mode;
  samples: RideSample[];
  final: boolean;
}

/** POST /rides/stream (non-final) */
export interface RideStreamAck {
  session_id: string;
  buffered: number;
}

/** POST /rides/upload and the final /rides/stream chunk */
export interface RideResult {
  ride_id: number;
  bumps: number;
  dark_gaps: number;
  segments_covered: number;
  evidence_ids: number[];
  incident_ids: number[];
  verified_incident_ids: number[];
}

export function isRideResult(r: RideStreamAck | RideResult): r is RideResult {
  return (r as RideResult).ride_id !== undefined;
}
