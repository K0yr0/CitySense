// Anonymous contributor identity for the trust system: a random token kept in this browser.
// The backend only stores a salted hash of it, never a name, email or phone number.
import type { CitizenAnswer } from "./types";

const TOKEN_KEY = "cityecho.contributor";
const ANSWERS_KEY = "cityecho.answers";
const ANSWERS_EVENT = "cityecho:answers";

let memoryToken: string | null = null;
let memoryAnswers: Record<string, CitizenAnswer> = {};

function randomToken(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

/** Stable per-browser token (falls back to a per-session token when storage is blocked). */
export function contributorToken(): string {
  try {
    const existing = localStorage.getItem(TOKEN_KEY);
    if (existing) return existing;
    const token = randomToken();
    localStorage.setItem(TOKEN_KEY, token);
    return token;
  } catch {
    memoryToken ??= randomToken();
    return memoryToken;
  }
}

function readAnswers(): Record<string, CitizenAnswer> {
  try {
    return { ...memoryAnswers, ...JSON.parse(localStorage.getItem(ANSWERS_KEY) || "{}") };
  } catch {
    return memoryAnswers;
  }
}

/** The answer this browser gave on an incident, if any (to show "You answered YES"). */
export function myAnswer(incidentId: number): CitizenAnswer | null {
  return readAnswers()[String(incidentId)] ?? null;
}

export function rememberAnswer(incidentId: number, answer: CitizenAnswer): void {
  memoryAnswers = { ...readAnswers(), [String(incidentId)]: answer };
  try {
    localStorage.setItem(ANSWERS_KEY, JSON.stringify(memoryAnswers));
  } catch {
    /* storage blocked: kept in memory for this session */
  }
  window.dispatchEvent(new Event(ANSWERS_EVENT));
}

/** For useSyncExternalStore: re-read answers when this or another tab stores one. */
export function subscribeAnswers(onChange: () => void): () => void {
  window.addEventListener(ANSWERS_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(ANSWERS_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}
