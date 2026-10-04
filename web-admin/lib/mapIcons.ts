// Incident pins for the maps: a pin in the citizen app's colour (confidence status, green once fixed)
// with a white glyph for the issue type, drawn as SVG data URLs for deck.gl's IconLayer (no icon font,
// no sprite file). The source (report / sensor / both) is shown in the side panel, not by colour.
import { pinHex } from "./format";
import type { IncidentSummary, IssueType } from "./types";

// 24x24 white glyphs, centred in the pin's head.
const GLYPH: Record<IssueType, string> = {
  // pothole: a hole in the road with cracks
  road_damage: '<ellipse cx="12" cy="14" rx="7" ry="3.5"/><path d="M5 9l3 2M19 9l-3 2M12 5v4"/>',
  // tram track: two rails and sleepers
  tram_track: '<path d="M8 4v16M16 4v16M6 8h12M6 12h12M6 16h12"/>',
  // streetlight: pole and lamp
  streetlight: '<path d="M9 21h6M12 21V9M8 9h8l-1.5-4h-5z"/>',
  // flooding: a drop
  flooding: '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>',
  // waste: a bin
  waste: '<path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13"/>',
  // other: exclamation mark
  other: '<path d="M12 5v9M12 18v.5"/>',
};

/** Icon box in SVG units; the tip of the pin is the bottom centre (anchor). */
export const PIN_W = 64;
export const PIN_H = 80;

const PIN_PATH = "M32 77C26 65 6 52 6 31a26 26 0 1 1 52 0c0 21-20 34-26 46Z";

const cache = new Map<string, string>();

/** Data URL of the pin for one incident (type + colour), plain or selected, per theme (cached). */
export function incidentPinUrl(i: Pick<IncidentSummary, "type" | "status" | "work_status">, dark: boolean, selected = false): string {
  const fill = pinHex(i);
  const key = `${i.type}:${fill}:${dark ? 1 : 0}:${selected ? 1 : 0}`;
  let url = cache.get(key);
  if (!url) {
    // Selected: a thick ring in the admin accent; otherwise a thin ring that separates the pin from the map.
    const ring = selected ? (dark ? "#8db1f2" : "#0f2d59") : dark ? "#0e1424" : "#ffffff";
    const svg =
      `<svg xmlns="http://www.w3.org/2000/svg" width="${PIN_W}" height="${PIN_H}" viewBox="0 0 ${PIN_W} ${PIN_H}">` +
      `<path d="${PIN_PATH}" fill="${fill}" stroke="${ring}" stroke-width="${selected ? 6 : 4}" stroke-linejoin="round"/>` +
      `<g transform="translate(14 13) scale(1.5)" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">` +
      `${GLYPH[i.type] ?? GLYPH.other}</g></svg>`;
    url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
    cache.set(key, url);
  }
  return url;
}
