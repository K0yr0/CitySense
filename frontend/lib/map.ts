// Shared MapLibre settings (free, keyless OpenFreeMap styles).
export const MAP_STYLE = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};

/** MapLibre v6 module worker, copied into /public by scripts/copy-maplibre-worker.mjs. */
export const MAPLIBRE_WORKER_URL = "/maplibre/maplibre-gl-worker.mjs";

export const WARSAW_VIEW = { longitude: 21.012, latitude: 52.232, zoom: 13.5 };
