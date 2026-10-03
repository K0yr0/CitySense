/**
 * The phone's current position via expo-location (foreground permission only).
 * Location is used on the device for the map and the 25 m question; the app never
 * stores a location history (ROADMAP: RODO/GDPR).
 */
import * as Location from 'expo-location';
import { useCallback, useEffect, useRef, useState } from 'react';

import type { LatLng } from '@/lib/geo';

export type Permission = 'unknown' | 'granted' | 'denied';

export type LocationState = {
  coords: LatLng | null;
  /** Horizontal accuracy radius in metres (null when unknown). */
  accuracy: number | null;
  timestamp: number | null;
  permission: Permission;
  error: string | null;
  /** Ask for permission if needed and take one fresh, high-accuracy fix. */
  refresh: () => Promise<LatLng | null>;
};

type Options = {
  /** Keep following the user (watchPositionAsync) while mounted. */
  watch?: boolean;
  /** Ask for permission on mount (otherwise only on refresh()). */
  requestOnMount?: boolean;
  /** Minimum movement between watch updates. */
  distanceIntervalM?: number;
};

export function useLocation({ watch = false, requestOnMount = true, distanceIntervalM = 5 }: Options = {}): LocationState {
  const [coords, setCoords] = useState<LatLng | null>(null);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [timestamp, setTimestamp] = useState<number | null>(null);
  const [permission, setPermission] = useState<Permission>('unknown');
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const apply = useCallback((pos: Location.LocationObject) => {
    if (!mounted.current) return;
    setCoords({ latitude: pos.coords.latitude, longitude: pos.coords.longitude });
    setAccuracy(pos.coords.accuracy ?? null);
    setTimestamp(pos.timestamp);
    setError(null);
  }, []);

  const ensurePermission = useCallback(async (): Promise<boolean> => {
    try {
      const current = await Location.getForegroundPermissionsAsync();
      const result = current.granted ? current : await Location.requestForegroundPermissionsAsync();
      if (mounted.current) setPermission(result.granted ? 'granted' : 'denied');
      if (!result.granted && mounted.current) setError('Konum izni verilmedi.');
      return result.granted;
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : String(e));
      return false;
    }
  }, []);

  const refresh = useCallback(async (): Promise<LatLng | null> => {
    if (!(await ensurePermission())) return null;
    try {
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      apply(pos);
      return { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, [apply, ensurePermission]);

  useEffect(() => {
    mounted.current = true;
    let subscription: Location.LocationSubscription | null = null;
    let cancelled = false;
    (async () => {
      if (!requestOnMount && !watch) return;
      if (!(await ensurePermission()) || cancelled) return;
      try {
        const last = await Location.getLastKnownPositionAsync();
        if (last && !cancelled) apply(last);
        if (watch) {
          subscription = await Location.watchPositionAsync(
            { accuracy: Location.Accuracy.High, distanceInterval: distanceIntervalM, timeInterval: 3000 },
            apply,
          );
          if (cancelled) subscription.remove();
        } else {
          apply(await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }));
        }
      } catch (e) {
        if (!cancelled && mounted.current) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
      mounted.current = false;
      subscription?.remove();
    };
  }, [apply, ensurePermission, watch, requestOnMount, distanceIntervalM]);

  return { coords, accuracy, timestamp, permission, error, refresh };
}
