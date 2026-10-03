// Tracks whether the UI is showing fixture data (mock mode, or a backend request failed).
import { useSyncExternalStore } from "react";

export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "1";

export interface DemoState {
  mock: boolean; // NEXT_PUBLIC_USE_MOCK=1
  failing: string[]; // endpoints currently served from fixtures because the backend failed
}

const INITIAL: DemoState = { mock: USE_MOCK, failing: [] };
let state: DemoState = INITIAL;
const listeners = new Set<() => void>();

function emit(next: DemoState) {
  state = next;
  listeners.forEach((l) => l());
}

export function markFallback(endpoint: string) {
  if (!state.failing.includes(endpoint)) emit({ ...state, failing: [...state.failing, endpoint] });
}

export function markLive(endpoint: string) {
  if (state.failing.includes(endpoint)) emit({ ...state, failing: state.failing.filter((e) => e !== endpoint) });
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useDemoState(): DemoState {
  return useSyncExternalStore(subscribe, () => state, () => INITIAL);
}
