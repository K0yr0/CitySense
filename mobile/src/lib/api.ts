/**
 * CityEcho backend client (contracts: docs/ARCHITECTURE.md §6, §8 and the /mobile router).
 *
 * Base URL comes from EXPO_PUBLIC_API_URL (mobile/.env). Default: http://localhost:8000.
 * `localhost` only works for web / the iOS simulator. On a real phone (Expo Go) use the
 * PC's LAN IP on the same Wi-Fi, e.g. EXPO_PUBLIC_API_URL=http://192.168.1.20:8000
 * and run the backend with `--host 0.0.0.0` so the phone can reach it.
 *
 * The session token is set by lib/session.tsx (setAuthToken) and sent as a Bearer header.
 */

import { Platform } from 'react-native';

import { commonText } from '@/i18n/common';
import { getLocale, text } from '@/lib/i18n';

export const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000').replace(
  /\/+$/,
  '',
);

const TIMEOUT_MS = 8000;
const UPLOAD_TIMEOUT_MS = 60000;

export class ApiError extends Error {
  readonly status?: number;
  readonly detail?: string;

  constructor(message: string, status?: number, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

let authToken: string | null = null;

/** Called by the session provider on sign-in / sign-out. */
export function setAuthToken(token: string | null) {
  authToken = token;
}

type RequestOptions = RequestInit & { timeoutMs?: number };

async function request<T>(path: string, { timeoutMs = TIMEOUT_MS, ...init }: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        // The backend writes its short status messages in this language (en / pl / uk).
        'Accept-Language': getLocale(),
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        ...init.headers,
      },
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(text(commonText).backend.serverUnreachable(API_URL));
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail);
    } catch {
      // non-JSON error body
    }
    throw new ApiError(`${path} → HTTP ${res.status}${detail ? `: ${detail}` : ''}`, res.status, detail);
  }
  return (await res.json()) as T;
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

function query(params: Record<string, string | number | undefined | null>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join('&')}` : '';
}

// ---- Types ----

export type LonLat = [number, number];

/** minLon, minLat, maxLon, maxLat */
export type BBox = [number, number, number, number];

export type Health = { ok: boolean };

export type VehicleKind = 'tram' | 'bus';

export type Vehicle = {
  id: string;
  line: string | null;
  lon: number;
  lat: number;
  ts: string | null; // ISO-8601
  kind: VehicleKind;
};

export type Role = 'citizen' | 'admin';

export type User = { id: number; email: string; name: string | null; role: Role };

export type Session = { token: string; user: User };

export type IssueType = 'road_damage' | 'tram_track' | 'streetlight' | 'flooding' | 'waste' | 'other';

/** Confidence status (set by the engine). */
export type IncidentStatus = 'candidate' | 'likely' | 'verified' | 'dismissed' | 'closed';

/** The city's work on the incident (set by the web admin). Independent of IncidentStatus. */
export type WorkStatus = 'todo' | 'in_progress' | 'done';

export type HealthClass = 'good' | 'fair' | 'poor' | 'unknown';

export type Mode = 'road' | 'tram';

/** What the citizen may see of an incident (ARCHITECTURE.md §8.4). No sensor data. */
export type PublicIncident = {
  id: number;
  type: IssueType;
  lon: number;
  lat: number;
  address: string | null;
  department: string | null;
  status: IncidentStatus;
  confidence: number; // 0–1
  work_status: WorkStatus;
  report_count: number;
  first_seen: string | null;
  last_seen: string | null;
};

export type IncidentDetail = PublicIncident & {
  my_answer: 'yes' | 'no' | null;
  i_reported: boolean;
  message: string;
};

export type MobileSegment = { id: number; mode: Mode; health_class: HealthClass; path: LonLat[] };

export type TransitLine = { line: string; mode: Mode };

export type Question = { incident: PublicIncident | null; distance_m: number | null };

export type Answer = 'yes' | 'no';

export type AnswerResult = {
  incident_id: number;
  status: IncidentStatus;
  confidence: number;
  work_status: WorkStatus;
  contributor_trust: number | null;
};

export type MobileReport = {
  report_id: number;
  text: string;
  created_at: string | null;
  category: IssueType | null;
  department: string | null;
  photo_url: string | null;
  incident: PublicIncident | null;
  others_count: number;
  message: string;
};

export type Me = {
  user: User;
  trust: number;
  correct: number;
  incorrect: number;
  reports_count: number;
  answers_count: number;
};

export type RouteKind = 'points' | 'line';

export type FavoriteRoute = {
  id: number;
  name: string;
  kind: RouteKind;
  start: LonLat | null;
  end: LonLat | null;
  line: string | null;
  mode: Mode | null;
  created_at: string | null;
};

export type NewRoute =
  | { name: string; kind: 'points'; start: LonLat; end: LonLat; mode?: Mode }
  | { name: string; kind: 'line'; line: string; mode?: Mode };

export type RouteWarning = {
  kind: 'incident' | 'poor_road';
  incident_id: number | null;
  lon: number;
  lat: number;
  distance_along_m: number;
  message: string;
};

export type RouteQuality = {
  route: FavoriteRoute;
  path: LonLat[];
  segments: MobileSegment[];
  summary: { good_m: number; fair_m: number; poor_m: number; unknown_m: number; overall: HealthClass };
  warnings: RouteWarning[];
};

export type NewReport = {
  text: string;
  lon?: number;
  lat?: number;
  /** Local file URI from expo-image-picker. */
  photo?: { uri: string; mimeType?: string | null; fileName?: string | null };
};

// ---- Meta ----

/** GET /health -> {"ok": true} */
export function getHealth(): Promise<Health> {
  return request<Health>('/health');
}

/** GET /vehicles/live?kind=tram|bus -> {"vehicles": [...]} */
export async function getLiveVehicles(kind: VehicleKind): Promise<Vehicle[]> {
  const data = await request<{ vehicles: Vehicle[] }>(`/vehicles/live${query({ kind })}`);
  return data.vehicles;
}

/** Absolute URL for a backend-relative path such as `/photos/<uuid>.jpg`. */
export function absoluteUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  return /^https?:\/\//.test(path) ? path : `${API_URL}${path}`;
}

// ---- Auth ----

/** POST /auth/google: exchange a Google ID token; `contributor` carries anonymous trust over. */
export function loginWithGoogle(idToken: string, contributor?: string): Promise<Session> {
  return request<Session>('/auth/google', json('POST', { id_token: idToken, contributor }));
}

/** POST /auth/dev: local/demo sign-in by email (404 unless the backend has AUTH_DEV_LOGIN=1). */
export function loginDev(email: string, contributor?: string): Promise<Session> {
  return request<Session>('/auth/dev', json('POST', { email, contributor }));
}

/** GET /users/me (Bearer) */
export function getUser(): Promise<User> {
  return request<User>('/users/me');
}

/** GET /mobile/me (Bearer): user + trust and activity counts. */
export function getMe(): Promise<Me> {
  return request<Me>('/mobile/me');
}

// ---- Map ----

function bboxParam(bbox: BBox): string {
  return bbox.map((v) => v.toFixed(5)).join(',');
}

/** GET /mobile/incidents (public): open incidents in the box. */
export async function getIncidents(bbox?: BBox, limit = 500): Promise<PublicIncident[]> {
  const data = await request<{ incidents: PublicIncident[] }>(
    `/mobile/incidents${query({ bbox: bbox && bboxParam(bbox), limit })}`,
  );
  return data.incidents;
}

/** GET /mobile/incidents/{id} (public; with a token also my_answer / i_reported). */
export function getIncident(id: number): Promise<IncidentDetail> {
  return request<IncidentDetail>(`/mobile/incidents/${id}`);
}

/** GET /mobile/segments (public): measured segments as colour classes only. */
export async function getSegments(bbox: BBox, mode?: Mode, limit = 5000): Promise<MobileSegment[]> {
  const data = await request<{ segments: MobileSegment[] }>(
    `/mobile/segments${query({ bbox: bboxParam(bbox), mode, limit })}`,
  );
  return data.segments;
}

/** GET /mobile/lines (public): bus/tram lines that have sensor rides. */
export async function getLines(mode?: Mode): Promise<TransitLine[]> {
  const data = await request<{ lines: TransitLine[] }>(`/mobile/lines${query({ mode })}`);
  return data.lines;
}

// ---- 25 m question ----

/**
 * GET /mobile/question (Bearer): an incident within 25 m to ask about, or null.
 * `exclude`: ids this device already asked / skipped, so the next nearest one can come up.
 */
export function getQuestion(lon: number, lat: number, accuracyM: number, exclude: number[] = []): Promise<Question> {
  const ids = exclude.slice(-200).join(',');
  return request<Question>(`/mobile/question${query({ lon, lat, accuracy_m: accuracyM, exclude: ids })}`);
}

/** POST /mobile/incidents/{id}/answer (Bearer) */
export function answerIncident(
  id: number,
  answer: Answer,
  where: { lon: number; lat: number; accuracy_m: number },
): Promise<AnswerResult> {
  return request<AnswerResult>(`/mobile/incidents/${id}/answer`, json('POST', { answer, ...where }));
}

// ---- Reports ----

/** POST /mobile/reports (Bearer, multipart) */
export async function submitReport(report: NewReport): Promise<MobileReport> {
  const form = new FormData();
  form.append('text', report.text);
  if (report.lon !== undefined && report.lat !== undefined) {
    form.append('lon', String(report.lon));
    form.append('lat', String(report.lat));
  }
  if (report.photo) {
    const name = report.photo.fileName || 'photo.jpg';
    if (Platform.OS === 'web') {
      // Browsers need a real Blob; the picker's uri is a blob:/data: URL there.
      form.append('photo', await (await fetch(report.photo.uri)).blob(), name);
    } else {
      // React Native's FormData accepts {uri, name, type} for files.
      form.append('photo', {
        uri: report.photo.uri,
        name,
        type: report.photo.mimeType || 'image/jpeg',
      } as unknown as Blob);
    }
  }
  return request<MobileReport>('/mobile/reports', { method: 'POST', body: form, timeoutMs: UPLOAD_TIMEOUT_MS });
}

/** GET /mobile/reports (Bearer): my reports, newest first. */
export async function getMyReports(): Promise<MobileReport[]> {
  const data = await request<{ reports: MobileReport[] }>('/mobile/reports');
  return data.reports;
}

// ---- Favourite routes ----

export async function getRoutes(): Promise<FavoriteRoute[]> {
  const data = await request<{ routes: FavoriteRoute[] }>('/mobile/routes');
  return data.routes;
}

export function createRoute(route: NewRoute): Promise<FavoriteRoute> {
  return request<FavoriteRoute>('/mobile/routes', json('POST', route));
}

export function deleteRoute(id: number): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/mobile/routes/${id}`, { method: 'DELETE' });
}

export function getRouteQuality(id: number): Promise<RouteQuality> {
  return request<RouteQuality>(`/mobile/routes/${id}/quality`, { timeoutMs: 20000 });
}
