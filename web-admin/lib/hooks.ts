import { useCallback, useEffect, useEffectEvent, useState } from "react";

interface ApiState<T> {
  key: string;
  data: T | undefined;
  error: Error | null;
  at: number; // ms timestamp of the last successful load
}

/**
 * Loads `fn()` whenever `key` changes and every `intervalMs` (null = no polling).
 * Previous data is kept while a new key loads (`stale` = true), so views never flash.
 */
export function useApi<T>(key: string, fn: () => Promise<T>, intervalMs: number | null = null) {
  const [state, setState] = useState<ApiState<T>>({ key: "", data: undefined, error: null, at: 0 });
  const [nonce, setNonce] = useState(0);
  const load = useEffectEvent(() => fn());

  useEffect(() => {
    let alive = true;
    const run = () =>
      load().then(
        (data) => alive && setState({ key, data, error: null, at: Date.now() }),
        (error: Error) => alive && setState((s) => ({ ...s, key, error })),
      );
    run();
    const timer = intervalMs ? setInterval(run, intervalMs) : undefined;
    return () => {
      alive = false;
      if (timer) clearInterval(timer);
    };
  }, [key, intervalMs, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return {
    data: state.data,
    error: state.error,
    loading: state.at === 0 && !state.error,
    stale: state.key !== key,
    updatedAt: state.at,
    reload,
  };
}

/** Re-renders every `ms` so relative times ("3 min ago") stay current. */
export function useNow(ms = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}
