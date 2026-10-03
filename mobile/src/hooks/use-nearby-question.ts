/**
 * M4: the 25 m "do you see it?" question, client side (ROADMAP M4, CLAUDE.md §5).
 *
 * - Watches the phone's position only while enabled (signed in) and the app is in the foreground.
 * - Asks the server (GET /mobile/question) only when GPS accuracy <= 25 m, and only when the phone
 *   moved >= 15 m since the last check or 60 s passed. Never more than one request in flight.
 * - "Once per incident": the server skips incidents the user already answered; on top of that the
 *   device remembers asked / answered / skipped ids (storage key below) so "Şimdi değil" sticks.
 * - Never asks when work_status = done (the server filters too) or when the incident is no longer
 *   candidate / likely.
 * - Answers go to POST /mobile/incidents/{id}/answer with a fresh position; the server weights them
 *   by the user's trust (backend/fusion/trust.py) and re-assesses the incident.
 *
 * The location is used on the device and sent only with these two requests; nothing is stored.
 */
import * as Location from 'expo-location';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';

import { useLocation } from '@/hooks/use-location';
import { ApiError, answerIncident, getQuestion, type Answer, type PublicIncident } from '@/lib/api';
import { distanceM, type LatLng } from '@/lib/geo';
import { getItem, setItem } from '@/lib/storage';

/** The question is asked only when the phone's GPS accuracy is at most this (metres). */
export const MAX_ACCURACY_M = 25;

const MOVE_RECHECK_M = 15; // re-check after moving this far...
const STALE_RECHECK_MS = 60_000; // ...or after this long standing still (so >= 20 s unless moved)
const MIN_GAP_MOVED_MS = 5_000; // hard floor even while moving (e.g. on a tram)
const TICK_MS = 5_000; // timer that drives the 60 s rule when the phone stands still
const WALK_AWAY_M = 60; // hide an open question once the user is this far away (it stays remembered)
const MESSAGE_MS = 2_500; // how long the closing message stays
const FIX_TIMEOUT_MS = 5_000; // fresh fix for the answer; falls back to the watched position
const FALLBACK_MAX_AGE_MS = 30_000;

const ASKED_KEY = 'cityecho.asked_incidents';
const ASKED_CAP = 500;

export type NearbyPhase = 'hidden' | 'asking' | 'sending' | 'closing';
export type NearbyTone = 'success' | 'info' | 'error';

export type NearbyQuestionState = {
  phase: NearbyPhase;
  /** The incident being asked about (null when hidden). Public fields only, never sensor data. */
  incident: PublicIncident | null;
  /** Server-side distance to the incident when it was offered. */
  distanceM: number | null;
  /** Short Turkish message: thanks, why the question closed, or why sending failed. */
  message: string | null;
  tone: NearbyTone | null;
  /** Send YES / NO with the current position. */
  answer: (answer: Answer) => Promise<void>;
  /** "Şimdi değil": hide and never ask about this incident again on this device. */
  skip: () => void;
};

type Fix = { lon: number; lat: number; accuracy_m: number };

type Position = { coords: LatLng | null; accuracy: number | null; timestamp: number | null };

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<null>((resolve) => {
    timer = setTimeout(() => resolve(null), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

/** Turkish message for an answer that the server refused; null = keep the question open. */
function refusalMessage(status: number | undefined): string | null {
  switch (status) {
    case 403:
      return 'Artık 25 m içinde değilsin; soru kapatıldı.';
    case 409:
      return 'Bu soru artık geçerli değil (cevaplanmış ya da sorun giderilmiş).';
    case 422:
      return 'Konum isabeti yetersiz (25 m üstü); soru kapatıldı.';
    case 404:
      return 'Bu bildirim artık yok.';
    default:
      return null;
  }
}

export function useNearbyQuestion({ enabled = true }: { enabled?: boolean } = {}): NearbyQuestionState {
  const [appActive, setAppActive] = useState(() => AppState.currentState !== 'background');
  const on = enabled && appActive;

  const { coords, accuracy, timestamp } = useLocation({
    watch: on,
    requestOnMount: on,
    distanceIntervalM: 10,
  });

  const [phase, setPhase] = useState<NearbyPhase>('hidden');
  const [incident, setIncident] = useState<PublicIncident | null>(null);
  const [distance, setDistance] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [tone, setTone] = useState<NearbyTone | null>(null);

  // Mutable state read by timers and async callbacks (only written in effects / callbacks).
  const onRef = useRef(on);
  const phaseRef = useRef<NearbyPhase>('hidden');
  const incidentRef = useRef<PublicIncident | null>(null);
  const position = useRef<Position>({ coords: null, accuracy: null, timestamp: null });
  const inFlight = useRef(false);
  const lastCheck = useRef<{ at: number; coords: LatLng } | null>(null);
  const asked = useRef<number[]>([]);
  const askedLoaded = useRef(false);

  useEffect(() => {
    onRef.current = on;
  }, [on]);

  useEffect(() => {
    position.current = { coords, accuracy, timestamp };
  }, [coords, accuracy, timestamp]);

  useEffect(() => {
    phaseRef.current = phase;
    incidentRef.current = incident;
  }, [phase, incident]);

  // Foreground only: watching stops (useLocation unsubscribes) while the app is in the background.
  useEffect(() => {
    const sub = AppState.addEventListener('change', (next) => setAppActive(next !== 'background'));
    return () => sub.remove();
  }, []);

  // Device memory of asked / answered / skipped incidents.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const raw = await getItem(ASKED_KEY);
      if (cancelled) return;
      try {
        const parsed: unknown = raw ? JSON.parse(raw) : [];
        const ids = Array.isArray(parsed) ? parsed.filter((x): x is number => typeof x === 'number') : [];
        // Keep ids remembered before loading finished.
        asked.current = [...ids.filter((id) => !asked.current.includes(id)), ...asked.current].slice(-ASKED_CAP);
      } catch {
        // corrupt value: start fresh
      }
      askedLoaded.current = true;
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const remember = useCallback((id: number) => {
    const next = [...asked.current.filter((x) => x !== id), id].slice(-ASKED_CAP);
    asked.current = next;
    void setItem(ASKED_KEY, JSON.stringify(next));
  }, []);

  const hide = useCallback(() => {
    phaseRef.current = 'hidden';
    incidentRef.current = null;
    setPhase('hidden');
    setIncident(null);
    setDistance(null);
    setMessage(null);
    setTone(null);
  }, []);

  const close = useCallback((text: string, kind: NearbyTone) => {
    phaseRef.current = 'closing';
    setPhase('closing');
    setMessage(text);
    setTone(kind);
  }, []);

  // One evaluation step: hide a question the user walked away from, or ask the server.
  const evaluate = useCallback(async () => {
    if (!onRef.current) return;
    const { coords: here, accuracy: acc } = position.current;
    if (!here) return;

    const open = incidentRef.current;
    if (phaseRef.current === 'asking' && open) {
      if (distanceM(here, { latitude: open.lat, longitude: open.lon }) > WALK_AWAY_M) hide();
      return;
    }
    if (phaseRef.current !== 'hidden' || inFlight.current || !askedLoaded.current) return;
    if (acc == null || acc > MAX_ACCURACY_M) return;

    const now = Date.now();
    const last = lastCheck.current;
    if (last) {
      const moved = distanceM(last.coords, here);
      const elapsed = now - last.at;
      const due = (moved >= MOVE_RECHECK_M && elapsed >= MIN_GAP_MOVED_MS) || elapsed >= STALE_RECHECK_MS;
      if (!due) return;
    }

    inFlight.current = true;
    lastCheck.current = { at: now, coords: here };
    try {
      const q = await getQuestion(here.longitude, here.latitude, acc, asked.current);
      const found = q.incident;
      if (!found || !onRef.current || phaseRef.current !== 'hidden') return;
      if (asked.current.includes(found.id)) return; // skipped / answered on this device
      if (found.work_status === 'done') return; // defence in depth: never ask after repair
      if (found.status !== 'candidate' && found.status !== 'likely') return;
      remember(found.id); // once per incident, even if the app is closed without answering
      phaseRef.current = 'asking';
      incidentRef.current = found;
      setIncident(found);
      setDistance(q.distance_m);
      setMessage(null);
      setTone(null);
      setPhase('asking');
    } catch {
      // offline, endpoint not deployed yet, 401...: stay quiet and retry on the normal schedule
    } finally {
      inFlight.current = false;
    }
  }, [hide, remember]);

  // Re-evaluate on every position update (deferred so no state is set synchronously in the effect)...
  useEffect(() => {
    if (!on || !coords) return;
    const t = setTimeout(() => void evaluate(), 0);
    return () => clearTimeout(t);
  }, [on, coords, accuracy, evaluate]);

  // ...and on a timer, for the 60 s rule while standing still.
  useEffect(() => {
    if (!on) return;
    const t = setInterval(() => void evaluate(), TICK_MS);
    return () => clearInterval(t);
  }, [on, evaluate]);

  // Closing message disappears after a moment.
  useEffect(() => {
    if (phase !== 'closing') return;
    const t = setTimeout(hide, MESSAGE_MS);
    return () => clearTimeout(t);
  }, [phase, hide]);

  const currentFix = useCallback(async (): Promise<Fix | null> => {
    try {
      const pos = await withTimeout(
        Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
        FIX_TIMEOUT_MS,
      );
      if (pos && pos.coords.accuracy != null) {
        return { lon: pos.coords.longitude, lat: pos.coords.latitude, accuracy_m: pos.coords.accuracy };
      }
    } catch {
      // permission revoked / no fix: fall back to the watched position
    }
    const { coords: here, accuracy: acc, timestamp: ts } = position.current;
    if (here && acc != null && ts != null && Date.now() - ts <= FALLBACK_MAX_AGE_MS) {
      return { lon: here.longitude, lat: here.latitude, accuracy_m: acc };
    }
    return null;
  }, []);

  const answer = useCallback(
    async (value: Answer) => {
      const target = incidentRef.current;
      if (!target || phaseRef.current !== 'asking') return;
      phaseRef.current = 'sending';
      setPhase('sending');
      setMessage(null);
      setTone(null);

      const fix = await currentFix();
      if (incidentRef.current?.id !== target.id) return; // closed meanwhile
      if (!fix) {
        phaseRef.current = 'asking';
        setPhase('asking');
        setMessage('Konumun alınamadı. Lütfen tekrar dene.');
        setTone('error');
        return;
      }

      try {
        const result = await answerIncident(target.id, value, fix);
        remember(target.id);
        const trust = result.contributor_trust;
        close(
          trust != null
            ? `Teşekkürler! Güven puanın: %${Math.round(Math.min(1, Math.max(0, trust)) * 100)}`
            : 'Teşekkürler! Cevabın kaydedildi.',
          'success',
        );
      } catch (e) {
        const status = e instanceof ApiError ? e.status : undefined;
        const refusal = refusalMessage(status);
        if (refusal) {
          remember(target.id);
          close(refusal, 'info');
        } else if (status === 401) {
          close('Oturumun sona ermiş; cevap vermek için tekrar giriş yap.', 'info');
        } else {
          phaseRef.current = 'asking';
          setPhase('asking');
          setMessage('Gönderilemedi. Bağlantını kontrol edip tekrar dene.');
          setTone('error');
        }
      }
    },
    [close, currentFix, remember],
  );

  const skip = useCallback(() => {
    const target = incidentRef.current;
    if (target) remember(target.id);
    hide();
  }, [hide, remember]);

  return { phase, incident, distanceM: distance, message, tone, answer, skip };
}
