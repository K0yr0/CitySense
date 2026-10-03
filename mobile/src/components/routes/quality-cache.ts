/**
 * Small in-memory cache for GET /mobile/routes/{id}/quality, so the list cards and the detail
 * screen don't ask the backend (and its OSRM call) again on every render or tab switch.
 */
import { getRouteQuality, type RouteQuality } from '@/lib/api';

const TTL_MS = 2 * 60 * 1000;

type Entry = { at: number; promise: Promise<RouteQuality> };

const cache = new Map<number, Entry>();

/** Cached quality for a route; `fresh` forces a new request. Failed requests are not cached. */
export function loadRouteQuality(id: number, fresh = false): Promise<RouteQuality> {
  const hit = cache.get(id);
  if (!fresh && hit && Date.now() - hit.at < TTL_MS) return hit.promise;
  const promise = getRouteQuality(id);
  const entry = { at: Date.now(), promise };
  cache.set(id, entry);
  promise.catch(() => {
    if (cache.get(id) === entry) cache.delete(id);
  });
  return promise;
}

/** Forget one route (after delete) or everything (pull to refresh, sign-out). */
export function invalidateRouteQuality(id?: number) {
  if (id === undefined) cache.clear();
  else cache.delete(id);
}
