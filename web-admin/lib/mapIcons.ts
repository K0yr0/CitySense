// Incident markers for the city map: a disc in the source colour (report / sensor / both) with a white
// glyph for the issue type, drawn as SVG data URLs for deck.gl's IconLayer (no icon font, no sprite file).
import { type SourceKind, sourceRGBA } from "./format";
import type { IssueType } from "./types";

// 24x24 white glyphs, centred in the marker.
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

const cache = new Map<string, string>();

/** Data URL of the marker for one incident type + source, per theme (cached). */
export function incidentIconUrl(type: IssueType, source: SourceKind, dark: boolean): string {
  const key = `${type}:${source}:${dark ? 1 : 0}`;
  let url = cache.get(key);
  if (!url) {
    const [r, g, b] = sourceRGBA(source, dark);
    const ring = dark ? "#1a1a19" : "#ffffff";
    const svg =
      `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">` +
      `<circle cx="32" cy="32" r="29" fill="rgb(${r},${g},${b})" stroke="${ring}" stroke-width="4"/>` +
      `<g transform="translate(14 14) scale(1.5)" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">` +
      `${GLYPH[type] ?? GLYPH.other}</g></svg>`;
    url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
    cache.set(key, url);
  }
  return url;
}
