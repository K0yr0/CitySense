// Demo mode (NEXT_PUBLIC_USE_MOCK=1) draws the real Warsaw network: C's map export
// (data/osm/segments_demo.geojson, 11,833 road and tram segments), the simulator's defects
// (data/demo/sim_world.json) and the bus routes it drives (data/demo/bus_lines.json),
// packed into one small file at public/demo/city.json.
// Read only; both sources belong to C. Missing sources (e.g. a deploy without the repo root)
// just skip: lib/mock.ts then falls back to its two hand-drawn streets.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

const root = new URL("../../", import.meta.url);
const segmentsSrc = new URL("data/osm/segments_demo.geojson", root);
const worldSrc = new URL("data/demo/sim_world.json", root);
const linesSrc = new URL("data/demo/bus_lines.json", root);
const dst = new URL("../public/demo/", import.meta.url);

if (!existsSync(segmentsSrc)) {
  console.warn("[copy-demo-data] data/osm/segments_demo.geojson not found, demo map keeps its built-in streets");
  process.exit(0);
}

const round = (v) => Math.round(v * 1e5) / 1e5; // ~1 m
const geo = JSON.parse(readFileSync(segmentsSrc, "utf8"));
const names = [];
const nameIndex = new Map();
const segments = [];
for (const f of geo.features ?? []) {
  const coords = f.geometry?.type === "LineString" ? f.geometry.coordinates : null;
  if (!coords || coords.length < 2) continue;
  const name = f.properties?.name ?? "";
  if (!nameIndex.has(name)) {
    nameIndex.set(name, names.length);
    names.push(name);
  }
  // [mode (1 = tram, 0 = road), name index, lon, lat, lon, lat, ...]
  segments.push([f.properties?.mode === "tram" ? 1 : 0, nameIndex.get(name), ...coords.flatMap(([x, y]) => [round(x), round(y)])]);
}

let defects = [];
if (existsSync(worldSrc)) {
  const world = JSON.parse(readFileSync(worldSrc, "utf8"));
  defects = (world.defects ?? []).map((d) => ({ id: d.id, kind: d.kind, mode: d.mode, line: d.line ?? null, street: d.street ?? null, lon: d.lon, lat: d.lat }));
}

// The real routes C's simulated buses drive (ZTM GTFS): which streets are measured, and where demo buses move.
const lines = {};
if (existsSync(linesSrc)) {
  for (const [id, l] of Object.entries(JSON.parse(readFileSync(linesSrc, "utf8")).lines ?? {})) {
    if (Array.isArray(l.path) && l.path.length > 1) lines[id] = { name: l.name ?? id, path: l.path.map(([x, y]) => [round(x), round(y)]) };
  }
}

mkdirSync(dst, { recursive: true });
const out = JSON.stringify({
  source: "data/osm/segments_demo.geojson + data/demo/sim_world.json + data/demo/bus_lines.json (owner C)",
  names,
  segments,
  defects,
  lines,
});
writeFileSync(new URL("city.json", dst), out);
console.log(
  `[copy-demo-data] ${segments.length} segments, ${defects.length} defects, ${Object.keys(lines).length} bus lines -> public/demo/city.json (${Math.round(out.length / 1024)} KB)`,
);
