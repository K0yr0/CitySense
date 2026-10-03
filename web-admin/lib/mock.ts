// Demo fixtures in Warsaw city-centre coordinates. Shapes are identical to docs/ARCHITECTURE.md §6.
// Everything is deterministic (seeded PRNG); timestamps are relative to "now" so the demo stays fresh.
import { assess, DEFAULT_TRUST, statusFor, type Vote } from "./confidence";
import type {
  CitizenResponse,
  Department,
  Evidence,
  IncidentDetail,
  IncidentReport,
  IncidentStatus,
  IncidentSummary,
  IssueType,
  Mode,
  Segment,
  Signal,
  Stats,
  TimelineEvent,
  Vehicle,
  VehicleKind,
  VerifyResult,
  WorkStatus,
} from "./types";

type LonLat = [number, number];

// ---------------------------------------------------------------- geometry helpers

function mulberry32(seed: number) {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const M_PER_DEG_LAT = 111_320;
const M_PER_DEG_LON = 111_320 * Math.cos((52.23 * Math.PI) / 180);

function dist(a: LonLat, b: LonLat): number {
  const dx = (a[0] - b[0]) * M_PER_DEG_LON;
  const dy = (a[1] - b[1]) * M_PER_DEG_LAT;
  return Math.hypot(dx, dy);
}

function lerp(a: LonLat, b: LonLat, f: number): LonLat {
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
}

function lineLength(line: LonLat[]): number {
  let d = 0;
  for (let i = 0; i < line.length - 1; i++) d += dist(line[i], line[i + 1]);
  return d;
}

/** Point at fraction f (0..1) of the polyline length. */
function along(line: LonLat[], f: number): LonLat {
  let target = Math.min(1, Math.max(0, f)) * lineLength(line);
  for (let i = 0; i < line.length - 1; i++) {
    const d = dist(line[i], line[i + 1]);
    if (target <= d) return lerp(line[i], line[i + 1], d === 0 ? 0 : target / d);
    target -= d;
  }
  return line[line.length - 1];
}

/** Points every `step` metres along the polyline. */
function densify(line: LonLat[], step = 25): LonLat[] {
  const out: LonLat[] = [line[0]];
  let carry = 0;
  for (let i = 0; i < line.length - 1; i++) {
    const a = line[i];
    const b = line[i + 1];
    const d = dist(a, b);
    let pos = step - carry;
    while (pos <= d) {
      out.push(lerp(a, b, pos / d));
      pos += step;
    }
    carry = d - (pos - step);
  }
  const last = line[line.length - 1];
  if (dist(out[out.length - 1], last) > 5) out.push(last);
  return out;
}

/** Closest point on the polyline (equirectangular projection, fine at city scale). */
function snap(line: LonLat[], p: LonLat): LonLat {
  let best: LonLat = line[0];
  let bestD = Infinity;
  for (let i = 0; i < line.length - 1; i++) {
    const a = line[i];
    const b = line[i + 1];
    const abx = (b[0] - a[0]) * M_PER_DEG_LON;
    const aby = (b[1] - a[1]) * M_PER_DEG_LAT;
    const apx = (p[0] - a[0]) * M_PER_DEG_LON;
    const apy = (p[1] - a[1]) * M_PER_DEG_LAT;
    const len2 = abx * abx + aby * aby;
    const f = len2 === 0 ? 0 : Math.min(1, Math.max(0, (apx * abx + apy * aby) / len2));
    const q = lerp(a, b, f);
    const d = dist(q, p);
    if (d < bestD) {
      bestD = d;
      best = q;
    }
  }
  return best;
}

// ---------------------------------------------------------------- streets

const MARSZALKOWSKA: LonLat[] = [
  [21.0068, 52.244],
  [21.0073, 52.2396],
  [21.009, 52.2352],
  [21.0117, 52.2306],
  [21.0137, 52.2265],
  [21.016, 52.2222],
  [21.0175, 52.2195],
  [21.0186, 52.2152],
];
const JEROZOLIMSKIE: LonLat[] = [
  [20.9877, 52.2247],
  [20.996, 52.2268],
  [21.0035, 52.2287],
  [21.0117, 52.2306],
  [21.018, 52.2313],
  [21.0225, 52.2318],
];
const NOWY_SWIAT: LonLat[] = [
  [21.0172, 52.2405],
  [21.0187, 52.2355],
  [21.0196, 52.2318],
  [21.0212, 52.2278],
];
const SWIETOKRZYSKA: LonLat[] = [
  [20.9985, 52.2345],
  [21.009, 52.2352],
  [21.0175, 52.2362],
];

// ---------------------------------------------------------------- incidents

interface IncidentSeed {
  id: number;
  type: IssueType;
  department: Department;
  at: LonLat;
  street?: LonLat[];
  address: string;
  reports: number;
  sensorRides: number;
  sensorCount: number;
  closed?: boolean; // handled by the city
  misses?: number; // capable vehicles that passed without detecting anything
  yes?: number; // explicit citizen YES answers (besides the reports)
  no?: number; // citizen NO answers
  sev: number | null;
  urg: number | null;
  vuln: number;
  foundBefore: boolean;
  vehicle: string | null;
  eta: number | null;
  firstMin: number; // minutes ago
  lastMin: number;
  verifyAfterMin?: number; // minutes from verification request to sensor confirmation
  work?: { status: WorkStatus; min: number }; // city work (default todo), changed `min` minutes ago
  summary: string;
}

const SEEDS: IncidentSeed[] = [
  {
    id: 101, type: "tram_track", department: "Tramwaje Warszawskie", at: [21.0122, 52.2297], street: MARSZALKOWSKA,
    address: "Marszałkowska / Rondo Dmowskiego", reports: 24, sensorRides: 5, sensorCount: 6,
    sev: 0.86, urg: 4, vuln: 0.7, foundBefore: false, vehicle: "tram 17", eta: 6, firstMin: 26 * 60, lastMin: 35, verifyAfterMin: 7,
    work: { status: "in_progress", min: 3 * 60 },
    summary: "Passengers report heavy jolts at a rail joint just south of Rondo Dmowskiego. Tram 17 measured a strong vertical shock at the same spot, confirming a track defect.",
  },
  {
    id: 102, type: "road_damage", department: "ZDM", at: [21.0091, 52.2349], street: MARSZALKOWSKA,
    address: "Marszałkowska / Świętokrzyska", reports: 23, sensorRides: 0, sensorCount: 0, yes: 3, no: 1,
    sev: null, urg: 4, vuln: 0.85, foundBefore: false, vehicle: "tram 17", eta: 6, firstMin: 9 * 60, lastMin: 4,
    summary: "A deep pothole in the right lane at Świętokrzyska; drivers swerve onto the tram tracks to avoid it. Tram 17 has been asked to verify on its next pass.",
  },
  {
    id: 103, type: "tram_track", department: "Tramwaje Warszawskie", at: [21.0139, 52.2262], street: MARSZALKOWSKA,
    address: "Marszałkowska / Hoża", reports: 0, sensorRides: 3, sensorCount: 4,
    sev: 0.74, urg: null, vuln: 0.8, foundBefore: true, vehicle: null, eta: null, firstMin: 3 * 24 * 60, lastMin: 50,
    summary: "Three independent tram rides recorded the same vertical shock near Hoża. Nobody has reported it yet.",
  },
  {
    id: 104, type: "streetlight", department: "ZDM", at: [21.0133, 52.2273], street: MARSZALKOWSKA,
    address: "Marszałkowska / Wilcza", reports: 0, sensorRides: 2, sensorCount: 2,
    sev: 0.62, urg: null, vuln: 0.75, foundBefore: true, vehicle: null, eta: null, firstMin: 2 * 24 * 60, lastMin: 14 * 60,
    summary: "Night rides show a missing light peak in the lux signal at the Wilcza crossing: one streetlight is likely out.",
  },
  {
    id: 105, type: "road_damage", department: "ZDM", at: [21.0045, 52.2289], street: JEROZOLIMSKIE,
    address: "Al. Jerozolimskie / Dworzec Centralny", reports: 9, sensorRides: 3, sensorCount: 3,
    sev: 0.68, urg: 3, vuln: 0.9, foundBefore: false, vehicle: "bus 175", eta: 4, firstMin: 30 * 60, lastMin: 3 * 60, verifyAfterMin: 6,
    work: { status: "in_progress", min: 10 * 60 },
    summary: "Cracked asphalt and a sunken manhole on the bus lane outside Warszawa Centralna, reported by citizens and confirmed by bus 175.",
  },
  {
    id: 106, type: "flooding", department: "MPWiK", at: [21.0063, 52.2296],
    address: "Przejście podziemne, Dworzec Centralny", reports: 14, sensorRides: 0, sensorCount: 0,
    sev: null, urg: 5, vuln: 0.9, foundBefore: false, vehicle: null, eta: null, firstMin: 5 * 60, lastMin: 20,
    work: { status: "in_progress", min: 45 },
    summary: "The pedestrian underpass at Warszawa Centralna floods ankle-deep after rain; likely a blocked drain.",
  },
  {
    id: 107, type: "waste", department: "Straż Miejska", at: [21.0177, 52.2193],
    address: "Plac Zbawiciela", reports: 7, sensorRides: 0, sensorCount: 0,
    sev: null, urg: 2, vuln: 0.5, foundBefore: false, vehicle: null, eta: null, firstMin: 3 * 24 * 60, lastMin: 6 * 60,
    summary: "Overflowing bins and scattered litter around Plac Zbawiciela for three days.",
  },
  {
    id: 108, type: "road_damage", department: "ZDM", at: [21.0195, 52.2315], street: JEROZOLIMSKIE,
    address: "Al. Jerozolimskie / Nowy Świat", reports: 0, sensorRides: 4, sensorCount: 5,
    sev: 0.79, urg: null, vuln: 0.85, foundBefore: true, vehicle: null, eta: null, firstMin: 4 * 24 * 60, lastMin: 2 * 60,
    summary: "Buses 128 and 175 repeatedly hit a sharp bump at the Nowy Świat junction. Found before any citizen report.",
  },
  {
    id: 109, type: "road_damage", department: "ZDM", at: [21.0074, 52.2392], street: MARSZALKOWSKA,
    address: "Marszałkowska / Królewska", reports: 2, sensorRides: 0, sensorCount: 0, misses: 1,
    sev: null, urg: 2, vuln: 0.6, foundBefore: false, vehicle: "bus 160", eta: 3, firstMin: 20 * 60, lastMin: 19 * 60,
    summary: "Two reports of a bump near Królewska. Bus 160 drove over the spot and measured nothing unusual, so confidence dropped.",
  },
  {
    id: 110, type: "streetlight", department: "ZDM", at: [21.0104, 52.2329], street: MARSZALKOWSKA,
    address: "Marszałkowska / Chmielna", reports: 4, sensorRides: 0, sensorCount: 0, yes: 2,
    sev: null, urg: 3, vuln: 0.8, foundBefore: false, vehicle: "tram 15", eta: 3, firstMin: 2 * 60, lastMin: 12,
    summary: "Several lamps out at the Chmielna tram stop; the platform is dark in the evening.",
  },
  {
    id: 111, type: "road_damage", department: "ZDM", at: [21.0158, 52.2226], street: MARSZALKOWSKA,
    address: "Plac Konstytucji", reports: 5, sensorRides: 2, sensorCount: 2,
    sev: 0.57, urg: 3, vuln: 0.7, foundBefore: false, vehicle: "tram 18", eta: 5, firstMin: 2 * 24 * 60, lastMin: 9 * 60, verifyAfterMin: 8,
    summary: "Ruts and a broken edge at the Plac Konstytucji crossing, confirmed by tram 18.",
  },
  {
    id: 112, type: "waste", department: "Straż Miejska", at: [21.0189, 52.2349],
    address: "Nowy Świat / Chmielna", reports: 3, sensorRides: 0, sensorCount: 0,
    sev: null, urg: 2, vuln: 0.4, foundBefore: false, vehicle: null, eta: null, firstMin: 8 * 60, lastMin: 90,
    summary: "Old furniture dumped next to the bus stop.",
  },
  {
    id: 113, type: "road_damage", department: "ZDM", at: [20.9995, 52.2277], street: JEROZOLIMSKIE,
    address: "Al. Jerozolimskie / Emilii Plater", reports: 4, sensorRides: 6, sensorCount: 7,
    sev: 0.81, urg: 3, vuln: 0.75, foundBefore: false, vehicle: "bus 128", eta: 4, firstMin: 6 * 24 * 60, lastMin: 26 * 60, verifyAfterMin: 6,
    work: { status: "done", min: 20 * 60 },
    summary: "A wide pothole on the westbound lanes at Emilii Plater, measured on six bus rides and reported by drivers.",
  },
  {
    id: 114, type: "flooding", department: "MPWiK", at: [21.0112, 52.2247],
    address: "Wilcza / Poznańska", reports: 2, sensorRides: 0, sensorCount: 0, closed: true,
    sev: null, urg: 3, vuln: 0.5, foundBefore: false, vehicle: null, eta: null, firstMin: 5 * 24 * 60, lastMin: 4 * 24 * 60,
    work: { status: "done", min: 4 * 24 * 60 },
    summary: "Blocked storm drain causing standing water; cleaned by MPWiK.",
  },
  {
    id: 115, type: "road_damage", department: "ZDM", at: [20.9905, 52.2254], street: JEROZOLIMSKIE,
    address: "Al. Jerozolimskie / Plac Zawiszy", reports: 0, sensorRides: 1, sensorCount: 1,
    sev: 0.48, urg: null, vuln: 0.6, foundBefore: false, vehicle: null, eta: null, firstMin: 70, lastMin: 70,
    summary: "A single bus ride recorded a bump near Plac Zawiszy; waiting for a second ride to corroborate.",
  },
  {
    id: 116, type: "road_damage", department: "ZDM", at: [21.0082, 52.2318], street: MARSZALKOWSKA,
    address: "Marszałkowska / Złota", reports: 1, sensorRides: 0, sensorCount: 0, misses: 3, no: 2,
    sev: null, urg: 2, vuln: 0.6, foundBefore: false, vehicle: "bus 160", eta: 4, firstMin: 2 * 24 * 60, lastMin: 20 * 60,
    summary: "One report of a pothole near Złota. Three bus passes measured nothing and two citizens answered NO, so it was dismissed.",
  },
  {
    id: 117, type: "streetlight", department: "ZDM", at: [21.0168, 52.2341],
    address: "Nowy Świat / Świętokrzyska", reports: 1, sensorRides: 0, sensorCount: 0,
    sev: null, urg: 2, vuln: 0.55, foundBefore: false, vehicle: null, eta: null, firstMin: 50, lastMin: 50,
    summary: "A single report of a dark lamp near the Świętokrzyska crossing; waiting for more answers or a night ride.",
  },
];

function seedPosition(s: IncidentSeed): LonLat {
  return s.street ? snap(s.street, s.at) : s.at;
}

function priorityScore(s: IncidentSeed): number {
  const both = s.reports > 0 && s.sensorRides > 0;
  const base =
    0.35 * (s.sev ?? 0) +
    (0.25 * Math.log(1 + s.reports)) / Math.log(51) +
    (0.2 * (s.urg ?? 0)) / 5 +
    0.2 * s.vuln;
  return Math.round(base * (both ? 1.5 : 1) * 1000) / 1000;
}

const BASE_TIME = Date.now();
const minutesAgo = (m: number) => new Date(BASE_TIME - m * 60_000).toISOString();

// Mutable demo state (verification requests) so the mock behaves like a backend.
const overrides = new Map<number, Partial<IncidentSummary>>();

function seedSeverities(s: IncidentSeed): number[] {
  return Array.from({ length: s.sensorRides }, (_, i) => (s.sev ?? 0.5) * (i === 0 ? 1 : 0.9));
}

function seedVotes(s: IncidentSeed): Vote[] {
  return [
    ...Array.from({ length: s.reports + (s.yes ?? 0) }, () => ({ yes: true, trust: DEFAULT_TRUST })),
    ...Array.from({ length: s.no ?? 0 }, () => ({ yes: false, trust: DEFAULT_TRUST })),
  ];
}

/** Status the confidence engine gives a seed (closed seeds stay closed). */
function seedStatus(s: IncidentSeed): { status: IncidentStatus; a: ReturnType<typeof assess> } {
  const a = assess(seedSeverities(s), s.misses ?? 0, seedVotes(s));
  return { status: s.closed ? "closed" : statusFor(a.confidence), a };
}

function summaryFromSeed(s: IncidentSeed): IncidentSummary {
  const [lon, lat] = seedPosition(s);
  const { status, a } = seedStatus(s);
  const votes = seedVotes(s);
  const base: IncidentSummary = {
    id: s.id,
    type: s.type,
    status,
    score: priorityScore(s),
    department: s.department,
    lon,
    lat,
    address: s.address,
    report_count: s.reports,
    sensor_count: s.sensorCount,
    sensor_rides: s.sensorRides,
    sensor_confirmed: s.sensorRides > 0 && s.reports > 0,
    found_before_report: s.foundBefore,
    has_sensor: s.sensorRides > 0,
    has_report: s.reports > 0,
    max_severity: s.sev,
    max_urgency: s.urg,
    first_seen: minutesAgo(s.firstMin),
    last_seen: minutesAgo(s.lastMin),
    verify_vehicle: s.vehicle,
    verify_eta_min: s.vehicle ? s.eta : null,
    confidence: Math.round(a.confidence * 1000) / 1000,
    sensor_confidence: a.sensor_confidence === null ? null : Math.round(a.sensor_confidence * 1000) / 1000,
    citizen_confidence: a.citizen_confidence === null ? null : Math.round(a.citizen_confidence * 1000) / 1000,
    yes_count: votes.filter((v) => v.yes).length,
    no_count: votes.filter((v) => !v.yes).length,
    sensor_misses: s.misses ?? 0,
    awaiting_verification: !!s.vehicle && s.sensorRides === 0 && !s.misses && (status === "candidate" || status === "likely"),
    work_status: s.work?.status ?? "todo",
    work_status_changed_at: s.work ? minutesAgo(s.work.min) : null,
  };
  return { ...base, ...overrides.get(s.id) };
}

export function mockIncidents(params: { department?: string; status?: string; workStatus?: string; limit?: number } = {}): IncidentSummary[] {
  return SEEDS.map(summaryFromSeed)
    .filter((i) => !params.department || i.department === params.department)
    .filter((i) => !params.status || params.status.split(",").includes(i.status))
    .filter((i) => !params.workStatus || params.workStatus.split(",").includes(i.work_status))
    .sort((a, b) => b.score - a.score)
    .slice(0, params.limit ?? 200);
}

// ---------------------------------------------------------------- incident detail

const TEXTS: Record<IssueType, [string, string][]> = {
  road_damage: [
    ["Ogromna dziura w jezdni na Marszałkowskiej przy Świętokrzyskiej, auta gwałtownie hamują i zjeżdżają na torowisko.", "Large pothole; cars brake hard and swerve onto the tram tracks."],
    ["Wyrwa w asfalcie tuż przy przejściu dla pieszych, rowerzysta prawie się przewrócił.", "Pothole next to the pedestrian crossing; a cyclist nearly fell."],
    ["Dziura na prawym pasie, już kilka aut złapało kapcia.", "Pothole in the right lane; several cars have had flat tyres."],
    ["Zapadnięta studzienka i popękany asfalt, każdy autobus głośno w to uderza.", "Sunken manhole and cracked asphalt; every bus hits it loudly."],
    ["Ta dziura robi się coraz większa, proszę coś z tym zrobić zanim ktoś się zabije.", "The pothole keeps growing; please fix it before someone gets hurt."],
    ["Koleiny i wyrwa na środku pasa, w nocy w ogóle jej nie widać.", "Ruts and a hole mid-lane, invisible at night."],
  ],
  tram_track: [
    ["Tramwaj przy Rondzie Dmowskiego strasznie trzęsie, słychać głośne uderzenie na złączu szyn.", "Trams shake badly here; loud bang at a rail joint."],
    ["Na Marszałkowskiej tramwaj 17 podskakuje, stojący pasażerowie tracą równowagę.", "Tram 17 jolts; standing passengers lose their balance."],
    ["Wyszczerbiona szyna przy przystanku, tramwaje zwalniają prawie do zera.", "Chipped rail near the stop; trams slow almost to a halt."],
    ["Od kilku dni głośne stukanie pod tramwajem zawsze w tym samym miejscu.", "Loud knocking under trams at the same spot for several days."],
  ],
  streetlight: [
    ["Nie świeci latarnia przy przejściu, wieczorem jest zupełnie ciemno.", "Streetlight out at the crossing; completely dark in the evening."],
    ["Kilka lamp nie działa od tygodnia, przystanek tonie w ciemności.", "Several lamps out for a week; the stop is in darkness."],
    ["Latarnia miga i gaśnie, niebezpiecznie dla pieszych.", "Streetlight flickers and goes out; dangerous for pedestrians."],
  ],
  flooding: [
    ["Po każdym deszczu zalane przejście podziemne przy Dworcu Centralnym, woda po kostki.", "Underpass floods after every rain; ankle-deep water."],
    ["Zatkana studzienka, cała jezdnia pod wodą.", "Blocked drain; the whole carriageway is under water."],
    ["Woda wybija ze studzienki kanalizacyjnej.", "Water is bubbling up from a sewer drain."],
  ],
  waste: [
    ["Przepełnione kosze i porozrzucane śmieci od trzech dni.", "Overflowing bins and litter for three days."],
    ["Ktoś wyrzucił stare meble przy przystanku.", "Someone dumped old furniture by the stop."],
    ["Śmieci wysypują się z kontenera, czuć smród.", "Rubbish spilling from a container; strong smell."],
  ],
  other: [["Uszkodzony znak drogowy, leży na chodniku.", "Damaged road sign lying on the pavement."]],
};

function makeSignal(severity: number, rnd: () => number): Signal {
  const fs = 100;
  const n = 200;
  const peak = 100;
  const amp = 2.5 + 9 * severity; // m/s²
  const values: number[] = [];
  for (let i = 0; i < n; i++) {
    const dt = (i - peak) / fs;
    const ring = dt >= -0.02 ? amp * Math.exp(-Math.max(0, dt) / 0.09) * Math.cos(2 * Math.PI * 11 * dt) : 0;
    const pre = dt < 0 ? 0.6 * amp * Math.exp(dt / 0.015) * Math.sin(2 * Math.PI * 11 * dt) : 0;
    const noise = (rnd() - 0.5) * 0.7 + 0.25 * Math.sin(i / 3.1);
    values.push(Math.round((ring + pre + noise) * 100) / 100);
  }
  values[peak] = Math.round(amp * 100) / 100;
  return { fs, values, peak_index: peak };
}

// The backend serves all merged reports; the mock caps them to keep the page light.
const MAX_MOCK_REPORTS = 40;
const PHOTO_TYPES = new Set<IssueType>(["road_damage", "flooding", "waste", "tram_track"]);

/** Placeholder "photo" for the demo: clearly labelled, never presented as a real picture. */
function demoPhoto(type: IssueType, k: number): string {
  const hue = { road_damage: 30, tram_track: 210, flooding: 195, waste: 95, streetlight: 50, other: 0 }[type];
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420" viewBox="0 0 640 420">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl(${hue},25%,${38 + (k % 3) * 6}%)"/><stop offset="1" stop-color="hsl(${hue},20%,22%)"/></linearGradient></defs>
<rect width="640" height="420" fill="url(#g)"/><ellipse cx="${300 + (k % 5) * 12}" cy="250" rx="150" ry="60" fill="rgba(0,0,0,.35)"/>
<text x="320" y="200" fill="rgba(255,255,255,.85)" font-family="system-ui,sans-serif" font-size="30" font-weight="600" text-anchor="middle">Demo photo</text>
<text x="320" y="238" fill="rgba(255,255,255,.7)" font-family="system-ui,sans-serif" font-size="20" text-anchor="middle">${TYPE_NAME[type]} · report ${k + 1}</text></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

const TYPE_NAME: Record<IssueType, string> = {
  road_damage: "Road damage", tram_track: "Tram track", streetlight: "Streetlight", flooding: "Flooding", waste: "Waste", other: "Other",
};

/** The vehicle a sensor ride came from (the asked vehicle, else a plausible line for the mode). */
function rideVehicle(inc: IncidentSummary, r: number): string {
  if (inc.verify_vehicle) return inc.verify_vehicle;
  return inc.type === "tram_track" ? ["tram 17", "tram 4", "tram 15"][r % 3] : ["bus 128", "bus 175", "bus 160"][r % 3];
}

function vehicleName(v: string | null | undefined): string {
  return v ? v.charAt(0).toUpperCase() + v.slice(1) : "A vehicle";
}

export function mockIncidentDetail(id: number): IncidentDetail | null {
  const seed = SEEDS.find((s) => s.id === id);
  if (!seed) return null;
  const inc = summaryFromSeed(seed);
  const rnd = mulberry32(id * 7919);
  const first = Date.parse(inc.first_seen);
  const last = Date.parse(inc.last_seen);
  const span = Math.max(1, last - first);

  const reports: IncidentReport[] = [];
  const evidence: Evidence[] = [];
  const timeline: TimelineEvent[] = [];
  const pool = TEXTS[inc.type];

  // Citizen reports first (when the incident started from a report).
  const sensorFirst = inc.found_before_report || (inc.has_sensor && !inc.has_report);
  const reportStart = sensorFirst ? first + span * 0.6 : first;
  const shown = Math.min(inc.report_count, MAX_MOCK_REPORTS);
  for (let k = 0; k < shown; k++) {
    const created = reportStart + ((last - reportStart) * k) / Math.max(1, shown - 1);
    const [raw, en] = pool[k % pool.length];
    const rid = id * 100 + k;
    reports.push({
      id: rid,
      raw_text: raw,
      summary_en: en,
      urgency: Math.max(1, (inc.max_urgency ?? 3) - (k % 2)),
      created_at: new Date(created).toISOString(),
      photo_url: PHOTO_TYPES.has(inc.type) && k % 4 === 1 ? demoPhoto(inc.type, k) : null,
    });
    evidence.push({
      id: id * 1000 + k,
      source: "report",
      type: inc.type,
      severity: 0.4 + 0.1 * (k % 3),
      ts: new Date(created).toISOString(),
      ride_id: null,
      report_id: rid,
      vehicle: null,
      details: { kind: "report", urgency: inc.max_urgency ?? 3, summary_en: en, hazard_to_people: (inc.max_urgency ?? 0) >= 4, location_confidence: 0.8, location_text: inc.address },
    });
  }
  if (reports.length) {
    timeline.push({ ts: reports[0].created_at, kind: "first_report", label: "First citizen report (19115)" });
    if (inc.report_count > 1) {
      timeline.push({ ts: inc.last_seen, kind: "report", label: `${inc.report_count - 1} more reports merged into this incident` });
    }
  }

  // Verification loop.
  // Awaiting incidents were asked "just now" so the ETA in the UI stays plausible.
  const verifyAt = inc.awaiting_verification ? Date.now() - 2 * 60_000 : reportStart + 3 * 60_000;
  const askedVehicle = inc.verify_vehicle && inc.has_report;
  if (askedVehicle && !sensorFirst) {
    timeline.push({
      ts: new Date(verifyAt).toISOString(),
      kind: "verification_requested",
      label: `Verification requested: ${vehicleName(inc.verify_vehicle)}, ETA ~${inc.verify_eta_min ?? 5} min`,
    });
  }

  // Sensor evidence.
  for (let r = 0; r < inc.sensor_count; r++) {
    const ts = sensorFirst
      ? first + (span * 0.5 * r) / Math.max(1, inc.sensor_count - 1)
      : verifyAt + (seed.verifyAfterMin ?? 6) * 60_000 + r * 3_600_000;
    const sev = Math.round((inc.max_severity ?? 0.5) * (r === 0 ? 1 : 0.8 + 0.15 * rnd()) * 100) / 100;
    evidence.push({
      id: id * 1000 + 500 + r,
      source: "sensor",
      type: inc.type,
      severity: sev,
      ts: new Date(ts).toISOString(),
      ride_id: 400 + id + r * 3,
      report_id: null,
      vehicle: rideVehicle(inc, r),
      details:
        inc.type === "streetlight"
          ? { kind: "dark_gap", expected_lux: 38, observed_lux: 4 }
          : { kind: "bump", speed_kmh: 24 + Math.round(rnd() * 14), raw_peak: Math.round((9.81 + 10 * sev) * 10) / 10, signal_fs: 100, peak_index: 100 },
    });
  }
  const sensorEv = evidence.filter((e) => e.source === "sensor");
  if (sensorEv.length) {
    if (sensorFirst) {
      sensorEv.slice(0, 3).forEach((e, i) =>
        timeline.push({
          ts: e.ts,
          kind: "sensor",
          label: inc.type === "streetlight" ? `Ride #${e.ride_id}: missing light peak at night` : `Ride #${e.ride_id}: bump detected (severity ${e.severity.toFixed(2)})${i === 0 ? "" : ", same spot"}`,
        }),
      );
      if (inc.found_before_report && sensorEv.length >= 2) {
        timeline.push({ ts: sensorEv[1].ts, kind: "proactive", label: `Found before any report: ${inc.sensor_rides} independent rides agree` });
      }
    } else {
      const e = sensorEv[0];
      timeline.push({ ts: e.ts, kind: "sensor", label: `${vehicleName(inc.verify_vehicle)} measured a jolt (severity ${e.severity.toFixed(2)})` });
    }
  }
  for (let m = 0; m < inc.sensor_misses; m++) {
    timeline.push({
      ts: new Date(verifyAt + (4 + 30 * m) * 60_000).toISOString(),
      kind: "sensor_miss",
      label: `${vehicleName(inc.verify_vehicle)} passed: no anomaly measured, confidence down`,
    });
  }
  // Explicit YES/NO answers (reports already count as YES and are not listed here).
  const settled = inc.status === "verified" || inc.status === "dismissed";
  const responses: CitizenResponse[] = [
    ...Array.from({ length: seed.yes ?? 0 }, () => "yes" as const),
    ...Array.from({ length: seed.no ?? 0 }, () => "no" as const),
  ].map((answer, n) => ({
    answer,
    trust: Math.round((DEFAULT_TRUST + (rnd() - 0.4) * 0.3) * 100) / 100,
    created_at: new Date(last - (n + 1) * 45 * 60_000).toISOString(),
    settled,
  }));
  for (const r of responses) {
    const said = r.answer === "yes" ? "YES, still there" : "NO, not there";
    timeline.push({ ts: r.created_at, kind: "response", label: `Citizen answered ${said} (trust ${(r.trust ?? DEFAULT_TRUST).toFixed(2)})` });
  }
  const pct = `confidence ${Math.min(99, Math.round(inc.confidence * 100))}%`;
  const lastEvent = timeline.reduce((t, e) => Math.max(t, Date.parse(e.ts)), first);
  if (inc.status === "verified") {
    timeline.push({ ts: new Date(lastEvent + 60_000).toISOString(), kind: "verified", label: `Verified (${pct}); contributor trust updated` });
  } else if (inc.status === "dismissed") {
    timeline.push({ ts: new Date(lastEvent + 60_000).toISOString(), kind: "dismissed", label: `Dismissed: no problem found (${pct}); contributor trust updated` });
  }
  timeline.sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts));

  const signal = inc.has_sensor && inc.type !== "streetlight" ? makeSignal(inc.max_severity ?? 0.5, rnd) : null;
  responses.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  return { ...inc, summary: seed.summary, reports: reports.reverse(), evidence, timeline, signal, responses };
}

// ---------------------------------------------------------------- segments

const BAD_SPOTS = SEEDS.filter((s) => s.sensorRides > 0 && s.type !== "streetlight").map((s) => ({
  at: seedPosition(s),
  depth: 0.25 + 0.75 * (s.sev ?? 0.5),
}));

function buildSegments(): Segment[] {
  const rnd = mulberry32(2026);
  const out: Segment[] = [];
  const streets: { line: LonLat[]; mode: Mode; unmeasuredHead: number; phase: number }[] = [
    { line: MARSZALKOWSKA, mode: "tram", unmeasuredHead: 9, phase: 0.3 },
    { line: JEROZOLIMSKIE, mode: "road", unmeasuredHead: 11, phase: 1.7 },
  ];
  let id = 1;
  for (const st of streets) {
    const pts = densify(st.line, 25);
    for (let i = 0; i < pts.length - 1; i++) {
      const mid = lerp(pts[i], pts[i + 1], 0.5);
      let h = 0.8 + 0.12 * Math.sin(i / 8 + st.phase) + 0.05 * Math.sin(i / 2.3) + (rnd() - 0.5) * 0.12;
      for (const b of BAD_SPOTS) {
        const d = dist(mid, b.at);
        h -= b.depth * Math.exp(-((d / 110) ** 2));
      }
      const unmeasured = i < st.unmeasuredHead || rnd() < 0.04;
      out.push({
        id: id++,
        mode: st.mode,
        health: unmeasured ? null : Math.round(Math.min(0.98, Math.max(0.04, h)) * 100) / 100,
        rides: unmeasured ? 0 : 1 + Math.floor(rnd() * 9),
        path: [pts[i], pts[i + 1]],
      });
    }
  }
  return out;
}

const SEGMENTS = buildSegments();

export function mockSegments(params: { bbox?: string; mode?: string; measuredOnly?: boolean } = {}): Segment[] {
  let box: number[] | null = null;
  if (params.bbox) {
    const b = params.bbox.split(",").map(Number);
    if (b.length === 4 && b.every(Number.isFinite)) box = b;
  }
  return SEGMENTS.filter((s) => !params.mode || s.mode === params.mode)
    .filter((s) => !params.measuredOnly || s.health !== null)
    .filter((s) => !box || s.path.some(([x, y]) => x >= box[0] && x <= box[2] && y >= box[1] && y <= box[3]));
}

// ---------------------------------------------------------------- vehicles

const ROUTES: { line: string; kind: VehicleKind; path: LonLat[]; phase: number; speed: number }[] = [
  { line: "17", kind: "tram", path: MARSZALKOWSKA, phase: 0.05, speed: 0.07 },
  { line: "17", kind: "tram", path: MARSZALKOWSKA, phase: 1.15, speed: 0.07 },
  { line: "4", kind: "tram", path: MARSZALKOWSKA, phase: 0.4, speed: 0.065 },
  { line: "15", kind: "tram", path: MARSZALKOWSKA, phase: 0.72, speed: 0.06 },
  { line: "18", kind: "tram", path: MARSZALKOWSKA, phase: 1.5, speed: 0.07 },
  { line: "35", kind: "tram", path: MARSZALKOWSKA, phase: 1.85, speed: 0.068 },
  { line: "18", kind: "tram", path: MARSZALKOWSKA, phase: 0.95, speed: 0.07 },
  { line: "35", kind: "tram", path: MARSZALKOWSKA, phase: 0.25, speed: 0.068 },
  { line: "7", kind: "tram", path: JEROZOLIMSKIE, phase: 0.2, speed: 0.08 },
  { line: "9", kind: "tram", path: JEROZOLIMSKIE, phase: 0.85, speed: 0.08 },
  { line: "22", kind: "tram", path: JEROZOLIMSKIE, phase: 1.3, speed: 0.075 },
  { line: "24", kind: "tram", path: JEROZOLIMSKIE, phase: 1.7, speed: 0.08 },
  { line: "25", kind: "tram", path: JEROZOLIMSKIE, phase: 0.55, speed: 0.078 },
  { line: "128", kind: "bus", path: JEROZOLIMSKIE, phase: 0.1, speed: 0.09 },
  { line: "175", kind: "bus", path: JEROZOLIMSKIE, phase: 1.05, speed: 0.09 },
  { line: "158", kind: "bus", path: JEROZOLIMSKIE, phase: 1.6, speed: 0.085 },
  { line: "111", kind: "bus", path: NOWY_SWIAT, phase: 0.3, speed: 0.12 },
  { line: "116", kind: "bus", path: NOWY_SWIAT, phase: 1.2, speed: 0.12 },
  { line: "180", kind: "bus", path: NOWY_SWIAT, phase: 0.75, speed: 0.11 },
  { line: "160", kind: "bus", path: SWIETOKRZYSKA, phase: 0.6, speed: 0.13 },
];

export function mockVehicles(kind?: VehicleKind): Vehicle[] {
  const tMin = Date.now() / 60_000;
  const ts = new Date().toISOString();
  return ROUTES.map((r, i) => {
    const x = (((r.phase + tMin * r.speed) % 2) + 2) % 2;
    const [lon, lat] = along(r.path, x < 1 ? x : 2 - x);
    return { id: `${r.kind === "tram" ? 3000 : 7000}${i}`, line: r.line, lon, lat, ts, kind: r.kind };
  }).filter((v) => !kind || v.kind === kind);
}

// ---------------------------------------------------------------- stats

export function mockStats(): Stats {
  return {
    reports_total: 412,
    incidents_total: 63,
    found_before_report: 9,
    candidate_total: 20,
    likely_total: 18,
    verified_total: 21,
    awaiting_verification: 7,
    contributors_total: 286,
    avg_verification_min: 7,
    rides_total: 38,
    segments_measured: SEGMENTS.filter((s) => s.health !== null).length,
  };
}

// ---------------------------------------------------------------- write endpoints

export function mockVerify(id: number): VerifyResult {
  const seed = SEEDS.find((s) => s.id === id);
  if (!seed) return { incident_id: id, status: null, vehicle: null, eta_min: null };
  const inc = summaryFromSeed(seed);
  if (inc.has_sensor) return { incident_id: id, status: inc.status, vehicle: inc.verify_vehicle, eta_min: null };
  const vehicle = inc.verify_vehicle ?? (seed.street === JEROZOLIMSKIE ? "bus 175" : "tram 17");
  const eta = inc.verify_eta_min ?? 5;
  overrides.set(id, { verify_vehicle: vehicle, verify_eta_min: eta, awaiting_verification: true });
  return { incident_id: id, status: inc.status, vehicle, eta_min: eta };
}
