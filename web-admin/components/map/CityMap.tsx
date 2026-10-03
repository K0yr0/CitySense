"use client";

import type { PickingInfo } from "@deck.gl/core";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef, useState } from "react";
import Map, { NavigationControl, type MapRef, type ViewStateChangeEvent } from "react-map-gl/maplibre";
import { getIncidents, getSegments, getVehicles } from "@/lib/api";
import { fmtScore, freshness, FRESHNESS_ALPHA, healthRGBA, healthWord, sourceKind, sourceRGBA, statusLabel, timeAgo, typeLabel, workLabel } from "@/lib/format";
import { useApi, useNow, usePrefersDark } from "@/lib/hooks";
import { MAP_STYLE, MAPLIBRE_WORKER_URL, WARSAW_VIEW } from "@/lib/map";
import type { IncidentSummary, Segment, Vehicle } from "@/lib/types";
import DeckOverlay from "./DeckOverlay";
import IncidentPanel from "./IncidentPanel";
import LayerPanel, { type LayerToggles } from "./LayerPanel";

type Box = [number, number, number, number];

const INITIAL_BOX: Box = [20.95, 52.2, 21.075, 52.265];

const contains = (outer: Box, inner: Box) => inner[0] >= outer[0] && inner[1] >= outer[1] && inner[2] <= outer[2] && inner[3] <= outer[3];

function padded(b: Box, f = 0.5): Box {
  const dx = (b[2] - b[0]) * f;
  const dy = (b[3] - b[1]) * f;
  return [b[0] - dx, b[1] - dy, b[2] + dx, b[3] + dy].map((v) => Math.round(v * 1e4) / 1e4) as Box;
}

const incidentRadius = (d: IncidentSummary) => 7 + 13 * Math.min(1, Math.max(0, (d.score ?? 0) / 1.5));

/** `focusId` (from /?incident=ID): select that incident and fly to it once the incidents have loaded. */
export default function CityMap({ focusId = null }: { focusId?: number | null }) {
  const dark = usePrefersDark();
  const mapRef = useRef<MapRef>(null);
  const flownTo = useRef<number | null>(null);
  const [toggles, setToggles] = useState<LayerToggles>({ segments: true, incidents: true, vehicles: true, hideDone: true });
  // Re-evaluates segment freshness (fading) and tooltip ages once a minute.
  const now = useNow(60_000);
  const [box, setBox] = useState<Box>(INITIAL_BOX);
  const [zoomedOut, setZoomedOut] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(focusId);
  const [hovering, setHovering] = useState(false);
  // The map only renders in the browser (MapShell: ssr false), so window is available here.
  const [layersOpen, setLayersOpen] = useState(() => window.innerWidth >= 768);

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
    () => (incidents.data ?? []).filter((i) => !toggles.hideDone || i.work_status !== "done"),
    [incidents.data, toggles.hideDone],
  );
  // From all incidents: a deep link to finished work still opens its panel even when done ones are hidden.
  const selected = incidents.data?.find((i) => i.id === selectedId) ?? null;

  // Deep link: fly to the focused incident once, as soon as both the map and the incident are there.
  const focused = focusId === null ? null : (incidents.data?.find((i) => i.id === focusId) ?? null);
  const flyToFocus = () => {
    if (!focused || flownTo.current === focused.id || !mapRef.current) return;
    flownTo.current = focused.id;
    mapRef.current.flyTo({ center: [focused.lon, focused.lat], zoom: 16.5, duration: 1200 });
  };
  useEffect(flyToFocus);
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
    if (!contains(box, view) || out !== zoomedOut) {
      setBox(padded(view));
      setZoomedOut(out);
    }
  };

  const layers = useMemo(() => {
    const ring: [number, number, number, number] = dark ? [26, 26, 25, 255] : [255, 255, 255, 255];
    const accent: [number, number, number, number] = dark ? [144, 133, 233, 255] : [74, 58, 167, 255];
    return [
      toggles.segments &&
        new PathLayer<Segment>({
          id: "segments",
          data: segments.data ?? [],
          getPath: (d) => d.path,
          getColor: (d) => {
            const c = healthRGBA(d.health, dark);
            // No timestamp = age unknown (the pipeline may not write health_updated_at yet): do not fade.
            return d.health == null || !d.updated_at ? c : [c[0], c[1], c[2], FRESHNESS_ALPHA[freshness(d.updated_at, now)]];
          },
          getWidth: (d) => (d.mode === "tram" ? 7 : 4.5),
          widthUnits: "pixels",
          widthMinPixels: 2,
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
      toggles.incidents &&
        new ScatterplotLayer<IncidentSummary>({
          id: "incidents",
          data: shownIncidents,
          getPosition: (d) => [d.lon, d.lat],
          getRadius: incidentRadius,
          radiusUnits: "pixels",
          getFillColor: (d) => sourceRGBA(sourceKind(d), dark),
          stroked: true,
          getLineColor: ring,
          getLineWidth: 2,
          lineWidthUnits: "pixels",
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 70],
          updateTriggers: { getFillColor: [dark], getLineColor: [dark] },
        }),
      toggles.incidents &&
        selected &&
        new ScatterplotLayer<IncidentSummary>({
          id: "selected",
          data: [selected],
          getPosition: (d) => [d.lon, d.lat],
          getRadius: (d) => incidentRadius(d) + 6,
          radiusUnits: "pixels",
          filled: false,
          stroked: true,
          getLineColor: accent,
          getLineWidth: 3,
          lineWidthUnits: "pixels",
          updateTriggers: { getLineColor: [dark] },
        }),
    ];
  }, [toggles, segments.data, vehicles.data, shownIncidents, selected, dark, now]);

  const getTooltip = ({ object, layer }: PickingInfo) => {
    if (!object || !layer) return null;
    let text = "";
    if (layer.id === "segments") {
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
          flyToFocus();
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
        open={layersOpen}
        setOpen={setLayersOpen}
      />
      {selected && <IncidentPanel incident={selected} onClose={() => select(null)} />}
    </div>
  );
}
