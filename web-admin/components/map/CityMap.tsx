"use client";

import type { PickingInfo } from "@deck.gl/core";
import { IconLayer, PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import "maplibre-gl/dist/maplibre-gl.css";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import Map, { NavigationControl, type MapRef, type ViewStateChangeEvent } from "react-map-gl/maplibre";
import { getIncidents, getSegments, getVehicles } from "@/lib/api";
import { type Filters, filtersQuery, hasFilters, matches } from "@/lib/filters";
import { deptLabel, fmtScore, freshness, FRESHNESS_ALPHA, healthClass, healthClassRGBA, healthWord, sourceKind, statusLabel, timeAgo, typeLabel, workLabel } from "@/lib/format";
import { useDarkTheme } from "@/lib/theme";
import { useApi, useNow } from "@/lib/hooks";
import { MAP_STYLE, MAPLIBRE_WORKER_URL, WARSAW_VIEW } from "@/lib/map";
import { incidentIconUrl } from "@/lib/mapIcons";
import type { IncidentSummary, Segment, Vehicle } from "@/lib/types";
import DeckOverlay from "./DeckOverlay";
import IncidentPanel from "./IncidentPanel";
import LayerPanel, { type LayerToggles } from "./LayerPanel";

type Box = [number, number, number, number];
type RGBA = [number, number, number, number];

const INITIAL_BOX: Box = [20.95, 52.2, 21.075, 52.265];

const contains = (outer: Box, inner: Box) => inner[0] >= outer[0] && inner[1] >= outer[1] && inner[2] <= outer[2] && inner[3] <= outer[3];

function padded(b: Box, f = 0.5): Box {
  const dx = (b[2] - b[0]) * f;
  const dy = (b[3] - b[1]) * f;
  return [b[0] - dx, b[1] - dy, b[2] + dx, b[3] + dy].map((v) => Math.round(v * 1e4) / 1e4) as Box;
}

/** "ZDM · Verified · To do · “plac”" for the layer panel. */
function filterLabel(f: Filters): string {
  return [f.department && deptLabel(f.department), f.status && statusLabel(f.status), f.work && workLabel(f.work), f.q && `“${f.q}”`]
    .filter(Boolean)
    .join(" · ");
}

const incidentRadius = (d: IncidentSummary) => 7 + 13 * Math.min(1, Math.max(0, (d.score ?? 0) / 1.5));

const NO_FILTERS: Filters = { department: "", status: "", work: "", q: "" };

/**
 * `focusId` (from /?incident=ID): select that incident and fly to it once the incidents have loaded.
 * `filters` (from the queue's "Show on the map"): show only matching incidents and fit the camera to them.
 */
export default function CityMap({ focusId = null, filters = NO_FILTERS }: { focusId?: number | null; filters?: Filters }) {
  const dark = useDarkTheme();
  const router = useRouter();
  const mapRef = useRef<MapRef>(null);
  const positioned = useRef(false);
  const filtered = hasFilters(filters);
  const [toggles, setToggles] = useState<LayerToggles>({ segments: true, incidents: true, vehicles: true, hideDone: true });
  // Re-evaluates segment freshness (fading) and tooltip ages once a minute.
  const now = useNow(60_000);
  const [box, setBox] = useState<Box>(INITIAL_BOX);
  const [zoomedOut, setZoomedOut] = useState(false);
  const [zoom, setZoom] = useState(WARSAW_VIEW.zoom);
  const [selectedId, setSelectedId] = useState<number | null>(focusId);
  const [hovering, setHovering] = useState(false);
  // The map only renders in the browser (MapShell: ssr false), so window is available here.
  // Open by default only where it leaves most of the map free.
  const [layersOpen, setLayersOpen] = useState(() => window.innerWidth >= 1280);

  // Below lg both panels do not fit side by side: opening an incident folds the layer panel.
  const select = (id: number | null) => {
    setSelectedId(id);
    if (id !== null && window.innerWidth < 1024) setLayersOpen(false);
  };

  const bbox = box.join(",");
  // Health is recomputed live as the simulated fleet drives (owner C), so segments refresh every 30 s.
  const segments = useApi(`segments:${bbox}:${zoomedOut}`, () => getSegments({ bbox, measuredOnly: zoomedOut }), 30_000);
  const incidents = useApi("incidents", () => getIncidents({ limit: 500 }), 15_000);
  const vehicles = useApi("vehicles", () => getVehicles(), 15_000);
  const shownIncidents = useMemo(
    () =>
      (incidents.data ?? []).filter(
        // A work filter from the queue (e.g. "done") wins over the "hide finished work" toggle.
        (i) => matches(i, filters) && (filters.work !== "" || !toggles.hideDone || i.work_status !== "done"),
      ),
    [incidents.data, toggles.hideDone, filters],
  );
  // From all incidents: a deep link to finished work still opens its panel even when done ones are hidden.
  const selected = incidents.data?.find((i) => i.id === selectedId) ?? null;

  // Deep link: once the map and the data are there, fly to the focused incident, or fit the filtered ones.
  const focused = focusId === null ? null : (incidents.data?.find((i) => i.id === focusId) ?? null);
  const positionCamera = () => {
    const map = mapRef.current;
    if (positioned.current || !map || !incidents.data) return;
    if (focused) {
      map.flyTo({ center: [focused.lon, focused.lat], zoom: 16.5, duration: 1200 });
    } else if (filtered && shownIncidents.length) {
      const lons = shownIncidents.map((i) => i.lon);
      const lats = shownIncidents.map((i) => i.lat);
      map.fitBounds(
        [
          [Math.min(...lons), Math.min(...lats)],
          [Math.max(...lons), Math.max(...lats)],
        ],
        { padding: { top: 80, bottom: 80, left: window.innerWidth >= 768 ? 360 : 40, right: 60 }, maxZoom: 16.5, duration: 1000 },
      );
    }
    positioned.current = true;
  };
  useEffect(positionCamera);
  const latestMeasurement = useMemo(
    () => (segments.data ?? []).reduce<string | null>((best, s) => (s.updated_at && (!best || s.updated_at > best) ? s.updated_at : best), null),
    [segments.data],
  );

  // Refetch segments only when the view leaves the area we already loaded.
  const onViewSettled = (e: ViewStateChangeEvent | { target: ViewStateChangeEvent["target"] }) => {
    const map = e.target;
    const b = map.getBounds();
    const view: Box = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
    const out = map.getZoom() < 12.5;
    setZoom(map.getZoom());
    if (!contains(box, view) || out !== zoomedOut) {
      setBox(padded(view));
      setZoomedOut(out);
    }
  };

  const layers = useMemo(() => {
    const ring: RGBA = dark ? [14, 20, 36, 255] : [255, 255, 255, 255];
    const accent: RGBA = dark ? [141, 177, 242, 255] : [15, 45, 89, 255];
    const casing: RGBA = dark ? [0, 0, 0, 200] : [255, 255, 255, 235];
    const all = segments.data ?? [];
    const measured = all.filter((d) => d.health != null);
    const unmeasured = all.filter((d) => d.health == null);
    // Old measurements fade; no timestamp = age unknown (pipeline may not write it yet): not faded.
    const fade = (d: Segment, a: number) => (d.updated_at ? Math.round((a * FRESHNESS_ALPHA[freshness(d.updated_at, now)]) / 235) : a);
    // Highest priority drawn last, so it sits on top where markers overlap.
    const byScore = [...shownIncidents].sort((a, b) => (a.score ?? 0) - (b.score ?? 0));
    return [
      toggles.segments &&
        new PathLayer<Segment>({
          id: "segments-unmeasured",
          data: unmeasured,
          getPath: (d) => d.path,
          getColor: healthClassRGBA("unknown", dark),
          getWidth: (d) => (d.mode === "tram" ? 2 : 1.5),
          widthUnits: "pixels",
          pickable: true,
          updateTriggers: { getColor: [dark] },
        }),
      // A light (dark-mode: black) casing under the measured lines keeps them readable on any basemap.
      toggles.segments &&
        new PathLayer<Segment>({
          id: "segments-casing",
          data: measured,
          getPath: (d) => d.path,
          getColor: (d) => [casing[0], casing[1], casing[2], fade(d, casing[3])],
          getWidth: (d) => (d.mode === "tram" ? 9.5 : 8),
          widthUnits: "pixels",
          capRounded: true,
          jointRounded: true,
          updateTriggers: { getColor: [dark, now] },
        }),
      toggles.segments &&
        new PathLayer<Segment>({
          id: "segments",
          data: measured,
          getPath: (d) => d.path,
          getColor: (d) => {
            const c = healthClassRGBA(healthClass(d.health), dark);
            return [c[0], c[1], c[2], fade(d, c[3])];
          },
          getWidth: (d) => (d.mode === "tram" ? 6 : 5),
          widthUnits: "pixels",
          capRounded: true,
          jointRounded: true,
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 110],
          updateTriggers: { getColor: [dark, now] },
        }),
      toggles.vehicles &&
        new ScatterplotLayer<Vehicle>({
          id: "vehicles",
          data: vehicles.data ?? [],
          getPosition: (d) => [d.lon, d.lat],
          getRadius: (d) => (d.kind === "tram" ? 5 : 4),
          radiusUnits: "pixels",
          getFillColor: (d) => (dark ? (d.kind === "tram" ? [240, 240, 235, 235] : [170, 170, 162, 235]) : d.kind === "tram" ? [30, 30, 28, 230] : [110, 109, 104, 230]),
          stroked: true,
          getLineColor: ring,
          getLineWidth: 1.5,
          lineWidthUnits: "pixels",
          pickable: true,
          transitions: { getPosition: 1200 },
          updateTriggers: { getFillColor: [dark], getLineColor: [dark] },
        }),
      // Line numbers once the map is close enough to read them.
      toggles.vehicles &&
        zoom >= 15 &&
        new TextLayer<Vehicle>({
          id: "vehicle-lines",
          data: vehicles.data ?? [],
          getPosition: (d) => [d.lon, d.lat],
          getText: (d) => d.line,
          getSize: 12,
          getPixelOffset: [0, -15],
          getColor: dark ? [240, 240, 235, 255] : [11, 11, 11, 255],
          background: true,
          getBackgroundColor: dark ? [14, 20, 36, 230] : [255, 255, 255, 230],
          backgroundPadding: [4, 1],
          fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
          fontWeight: 600,
          characterSet: "auto",
          transitions: { getPosition: 1200 },
          updateTriggers: { getColor: [dark], getBackgroundColor: [dark] },
        }),
      toggles.incidents &&
        new IconLayer<IncidentSummary>({
          id: "incidents",
          data: byScore,
          getPosition: (d) => [d.lon, d.lat],
          getIcon: (d) => {
            const source = sourceKind(d);
            return { url: incidentIconUrl(d.type, source, dark), id: `${d.type}:${source}:${dark ? 1 : 0}`, width: 64, height: 64 };
          },
          getSize: (d) => incidentRadius(d) * 2 + 4,
          sizeUnits: "pixels",
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 60],
          updateTriggers: { getIcon: [dark] },
        }),
      toggles.incidents &&
        selected &&
        new ScatterplotLayer<IncidentSummary>({
          id: "selected",
          data: [selected],
          getPosition: (d) => [d.lon, d.lat],
          getRadius: (d) => incidentRadius(d) + 7,
          radiusUnits: "pixels",
          filled: false,
          stroked: true,
          getLineColor: accent,
          getLineWidth: 3,
          lineWidthUnits: "pixels",
          updateTriggers: { getLineColor: [dark] },
        }),
    ];
  }, [toggles, segments.data, vehicles.data, shownIncidents, selected, dark, now, zoom]);

  const getTooltip = ({ object, layer }: PickingInfo) => {
    if (!object || !layer) return null;
    let text = "";
    if (layer.id === "segments" || layer.id === "segments-unmeasured") {
      const s = object as Segment;
      const where = `${s.name ? `${s.name} · ` : ""}${s.mode === "tram" ? "tram track" : "road"}`;
      text =
        s.health == null
          ? `${where}\nNot measured yet`
          : `${where}\n${healthWord(s.health)} · health ${Math.round(s.health * 100)}%\n${s.rides} ride${s.rides === 1 ? "" : "s"}${s.updated_at ? ` · measured ${timeAgo(s.updated_at, Date.now())}` : ""}`;
    } else if (layer.id === "vehicles") {
      const v = object as Vehicle;
      text = `${v.kind === "tram" ? "Tram" : "Bus"} ${v.line}\nposition ${timeAgo(v.ts, Date.now())}`;
    } else if (layer.id === "incidents") {
      const i = object as IncidentSummary;
      text = `${typeLabel(i.type)} · score ${fmtScore(i.score)}\n${i.address ?? ""}\n${statusLabel(i.status)} · work: ${workLabel(i.work_status).toLowerCase()}`;
    } else return null;
    return {
      text,
      style: {
        background: "var(--surface)",
        color: "var(--ink)",
        border: "1px solid var(--line-strong)",
        borderRadius: "8px",
        padding: "6px 10px",
        fontSize: "14px",
        fontFamily: "var(--font-sans)",
        lineHeight: "1.4",
      },
    };
  };

  return (
    <div className="absolute inset-0">
      <Map
        ref={mapRef}
        initialViewState={WARSAW_VIEW}
        mapStyle={dark ? MAP_STYLE.dark : MAP_STYLE.light}
        workerUrl={MAPLIBRE_WORKER_URL}
        style={{ width: "100%", height: "100%" }}
        attributionControl={{ compact: true }}
        cursor={hovering ? "pointer" : "grab"}
        onLoad={(e) => {
          onViewSettled(e);
          positionCamera();
        }}
        onMoveEnd={onViewSettled}
        minZoom={10}
        maxZoom={19}
      >
        <NavigationControl position="bottom-right" showCompass={false} />
        <DeckOverlay
          layers={layers}
          getTooltip={getTooltip}
          onHover={(info) => setHovering(Boolean(info.object))}
          onClick={(info) => select(info.layer?.id === "incidents" && info.object ? (info.object as IncidentSummary).id : null)}
        />
      </Map>

      <LayerPanel
        toggles={toggles}
        onChange={setToggles}
        counts={{ segments: segments.data?.length, incidents: shownIncidents.length, vehicles: vehicles.data?.length }}
        vehiclesUpdatedAt={vehicles.updatedAt}
        latestMeasurement={latestMeasurement}
        filter={
          filtered
            ? { label: filterLabel(filters), listHref: `/incidents?${filtersQuery(filters)}`, onClear: () => router.replace("/", { scroll: false }) }
            : null
        }
        open={layersOpen}
        setOpen={setLayersOpen}
      />
      {selected && <IncidentPanel incident={selected} onClose={() => select(null)} />}
    </div>
  );
}
