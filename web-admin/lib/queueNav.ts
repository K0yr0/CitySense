// The order of the incident queue as last shown (filters applied), so the incident page can offer
// "previous / next" and a way back to the same filtered queue. Kept in sessionStorage (this tab only).
import { useSyncExternalStore } from "react";

export interface QueueOrder {
  ids: number[];
  query: string; // the queue's search params, e.g. "department=ZDM&work=todo"
}

const KEY = "citysense.queue";
const EMPTY: QueueOrder = { ids: [], query: "" };
let cached: QueueOrder | null = null;
let raw: string | null = null;

function read(): QueueOrder {
  try {
    const now = sessionStorage.getItem(KEY);
    if (now !== raw || !cached) {
      raw = now;
      const parsed = JSON.parse(now || "null") as QueueOrder | null;
      cached = parsed && Array.isArray(parsed.ids) ? { ids: parsed.ids, query: parsed.query || "" } : EMPTY;
    }
    return cached;
  } catch {
    return EMPTY;
  }
}

export function saveQueueOrder(order: QueueOrder): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(order));
  } catch {
    /* storage blocked: no previous / next, the page still works */
  }
}

/** The last queue order; empty on the server and when the incident was opened directly. */
export function useQueueOrder(): QueueOrder {
  return useSyncExternalStore(
    () => () => {},
    read,
    () => EMPTY,
  );
}
