// Phone ride recorder: DeviceMotion (accelerationIncludingGravity) + Geolocation -> /rides/stream chunks.
import { streamRide } from "@/lib/api";
import type { Mode, RideResult, RideSample, RideStreamAck } from "@/lib/types";

export const CHUNK_MS = 2000;

interface Fix {
  lat: number;
  lon: number;
  speedKmh: number;
  accuracy: number;
  ts: number;
}

export interface RecorderSnapshot {
  elapsedS: number;
  captured: number;
  sent: number;
  chunks: number;
  hz: number;
  waitingForGps: boolean;
  fix: Fix | null;
  gpsError: string | null;
  vibration: number[]; // recent |a| - g, m/s²
}

type MotionPermission = { requestPermission?: () => Promise<"granted" | "denied" | "default"> };

const r3 = (x: number) => Math.round(x * 1000) / 1000;

function metres(a: Fix, b: { lat: number; lon: number }): number {
  const k = Math.PI / 180;
  const x = (b.lon - a.lon) * k * Math.cos(((a.lat + b.lat) / 2) * k);
  const y = (b.lat - a.lat) * k;
  return Math.hypot(x, y) * 6_371_000;
}

function newSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `ride-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** iOS 13+ only grants motion events after DeviceMotionEvent.requestPermission() inside a user gesture. */
export async function ensureMotionPermission(): Promise<string | null> {
  if (typeof window === "undefined" || typeof DeviceMotionEvent === "undefined") {
    return "This device does not expose motion sensors (DeviceMotionEvent). Use a phone.";
  }
  const DME = DeviceMotionEvent as unknown as MotionPermission;
  if (typeof DME.requestPermission === "function") {
    try {
      const res = await DME.requestPermission();
      if (res !== "granted") return "Motion access was denied. Allow 'Motion & Orientation' for this site and try again.";
    } catch {
      return "Motion permission failed. iOS needs HTTPS and a tap on Start.";
    }
  }
  if (!("geolocation" in navigator)) return "This browser has no geolocation.";
  return null;
}

export class RideRecorder {
  private buffer: RideSample[] = [];
  private sessionId = "";
  private t0 = 0;
  private fix: Fix | null = null;
  private watchId: number | null = null;
  private flushTimer: ReturnType<typeof setInterval> | null = null;
  private chain: Promise<unknown> = Promise.resolve();
  private captured = 0;
  private sent = 0;
  private chunks = 0;
  private motionTimes: number[] = [];
  private vibration: number[] = [];
  private gpsError: string | null = null;
  private wake: { release: () => Promise<void> } | null = null;
  private line = "";
  private mode: Mode = "tram";
  running = false;

  private onMotion = (e: DeviceMotionEvent) => {
    const a = e.accelerationIncludingGravity;
    if (!a || a.x == null || a.y == null || a.z == null) return;
    const now = performance.now();
    this.motionTimes.push(now);
    if (this.motionTimes.length > 200) this.motionTimes.shift();
    this.vibration.push(Math.hypot(a.x, a.y, a.z) - 9.81);
    if (this.vibration.length > 300) this.vibration.shift();
    const f = this.fix;
    if (!f) return; // no GPS fix yet: samples without a position are useless for map-matching
    this.buffer.push({
      t: r3((now - this.t0) / 1000),
      ax: r3(a.x),
      ay: r3(a.y),
      az: r3(a.z),
      lat: f.lat,
      lon: f.lon,
      speed_kmh: Math.round(f.speedKmh * 10) / 10,
    });
    this.captured += 1;
  };

  private onFix = (p: GeolocationPosition) => {
    const { latitude: lat, longitude: lon, speed, accuracy } = p.coords;
    let speedKmh = speed != null && speed >= 0 ? speed * 3.6 : 0;
    const prev = this.fix;
    if ((speed == null || speed < 0) && prev) {
      const dt = (p.timestamp - prev.ts) / 1000;
      if (dt > 0.5) speedKmh = (metres(prev, { lat, lon }) / dt) * 3.6;
    }
    this.fix = { lat, lon, speedKmh, accuracy, ts: p.timestamp };
    this.gpsError = null;
  };

  private onGeoError = (e: GeolocationPositionError) => {
    this.gpsError = e.code === e.PERMISSION_DENIED ? "Location permission denied." : e.message || "GPS unavailable.";
  };

  start(line: string, mode: Mode) {
    this.line = line;
    this.mode = mode;
    this.sessionId = newSessionId();
    this.t0 = performance.now();
    this.buffer = [];
    this.captured = this.sent = this.chunks = 0;
    this.motionTimes = [];
    this.vibration = [];
    this.fix = null;
    this.gpsError = null;
    this.chain = Promise.resolve();
    this.watchId = navigator.geolocation.watchPosition(this.onFix, this.onGeoError, { enableHighAccuracy: true, maximumAge: 0, timeout: 15_000 });
    window.addEventListener("devicemotion", this.onMotion);
    this.flushTimer = setInterval(() => void this.flush(false), CHUNK_MS);
    this.running = true;
    const wl = (navigator as Navigator & { wakeLock?: { request: (t: "screen") => Promise<{ release: () => Promise<void> }> } }).wakeLock;
    wl?.request("screen").then(
      (s) => (this.wake = s),
      () => undefined,
    );
  }

  private detach() {
    window.removeEventListener("devicemotion", this.onMotion);
    if (this.watchId !== null) navigator.geolocation.clearWatch(this.watchId);
    if (this.flushTimer) clearInterval(this.flushTimer);
    this.watchId = null;
    this.flushTimer = null;
    this.wake?.release().catch(() => undefined);
    this.wake = null;
    this.running = false;
  }

  /** Sends buffered samples; chunks are chained so they arrive in order. */
  private flush(final: boolean): Promise<RideStreamAck | RideResult | null> {
    const samples = this.buffer.splice(0);
    if (!final && samples.length === 0) return Promise.resolve(null);
    const body = { session_id: this.sessionId, vehicle_line: this.line, mode: this.mode, samples, final };
    const p = this.chain.then(() => streamRide(body));
    this.chain = p.then(
      () => {
        this.sent += samples.length;
        this.chunks += 1;
      },
      () => undefined,
    );
    return p;
  }

  /** Stops sensors and sends the final chunk; resolves with the backend's ride result. */
  async stop(): Promise<RideStreamAck | RideResult | null> {
    this.detach();
    const res = await this.flush(true);
    await this.chain;
    return res;
  }

  abort() {
    if (this.running) this.detach();
  }

  snapshot(): RecorderSnapshot {
    const n = this.motionTimes.length;
    const span = n > 1 ? this.motionTimes[n - 1] - this.motionTimes[0] : 0;
    return {
      elapsedS: this.running ? (performance.now() - this.t0) / 1000 : 0,
      captured: this.captured,
      sent: this.sent,
      chunks: this.chunks,
      hz: span > 0 ? Math.round(((n - 1) / span) * 1000) : 0,
      waitingForGps: this.fix === null,
      fix: this.fix,
      gpsError: this.gpsError,
      vibration: [...this.vibration],
    };
  }
}
