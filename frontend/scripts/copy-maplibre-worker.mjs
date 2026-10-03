// MapLibre GL v6 runs its tile parser in a module worker that is resolved relative to
// the library file. Bundlers break that path, so we serve the worker (and the chunk it
// imports) from /public/maplibre and point maplibre at it with setWorkerUrl().
import { cpSync, existsSync, mkdirSync } from "node:fs";

const src = new URL("../node_modules/maplibre-gl/dist/", import.meta.url);
const dst = new URL("../public/maplibre/", import.meta.url);

if (!existsSync(src)) {
  console.warn("[copy-maplibre-worker] maplibre-gl not installed yet, skipping");
  process.exit(0);
}
mkdirSync(dst, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  cpSync(new URL(file, src), new URL(file, dst));
}
