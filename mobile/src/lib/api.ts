/**
 * CityEcho backend client (contracts: docs/ARCHITECTURE.md §6).
 *
 * Base URL comes from EXPO_PUBLIC_API_URL (mobile/.env). Default: http://localhost:8000.
 * `localhost` only works for web / the iOS simulator. On a real phone (Expo Go) use the
 * PC's LAN IP on the same Wi-Fi, e.g. EXPO_PUBLIC_API_URL=http://192.168.1.20:8000
 * and run the backend with `--host 0.0.0.0` so the phone can reach it.
 */

export const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000').replace(
  /\/+$/,
  '',
);

const TIMEOUT_MS = 8000;

export class ApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(`Sunucuya ulaşılamadı: ${API_URL}`);
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    throw new ApiError(`${path} → HTTP ${res.status}`, res.status);
  }
  return (await res.json()) as T;
}

// ---- Types (mirror docs/ARCHITECTURE.md §6) ----

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

// ---- Endpoints ----

/** GET /health -> {"ok": true} */
export function getHealth(): Promise<Health> {
  return request<Health>('/health');
}

/** GET /vehicles/live?kind=tram|bus -> {"vehicles": [...]} */
export async function getLiveVehicles(kind: VehicleKind): Promise<Vehicle[]> {
  const data = await request<{ vehicles: Vehicle[] }>(
    `/vehicles/live?kind=${encodeURIComponent(kind)}`,
  );
  return data.vehicles;
}
