"use client";

import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import "maplibre-gl/dist/maplibre-gl.css";
import { useMemo } from "react";
import Map, { NavigationControl } from "react-map-gl/maplibre";
import { getSegments } from "@/lib/api";
import { healthRGBA, sourceKind, sourceRGBA } from "@/lib/format";
import { useApi, usePrefersDark } from "@/lib/hooks";
import { MAP_STYLE, MAPLIBRE_WORKER_URL } from "@/lib/map";
import type { IncidentSummary, Segment } from "@/lib/types";
import DeckOverlay from "../map/DeckOverlay";

// ~300 m around the incident: enough street context to recognise the spot.
const PAD_LON = 0.0045;
const PAD_LAT = 0.003;

/** Small map of one incident with the road / track health around it. Browser only (see LocationMap). */
export default function LocationMapInner({ incident: i }: { incident: IncidentSummary }) {
  const dark = usePrefersDark();
  const bbox = [i.lon - PAD_LON, i.lat - PAD_LAT, i.lon + PAD_LON, i.lat + PAD_LAT].map((v) => v.toFixed(5)).join(",");
  const segments = useApi(`segments:near:${bbox}`, () => getSegments({ bbox }));

  const layers = useMemo(() => {
    const ring: [number, number, number, number] = dark ? [26, 26, 25, 255] : [255, 255, 255, 255];
    return [
      new PathLayer<Segment>({
        id: "near-segments",
        data: segments.data ?? [],
        getPath: (d) => d.path,
        getColor: (d) => healthRGBA(d.health, dark),
        getWidth: (d) => (d.mode === "tram" ? 6 : 4),
        widthUnits: "pixels",
        capRounded: true,
        jointRounded: true,
        updateTriggers: { getColor: [dark] },
      }),
      new ScatterplotLayer<IncidentSummary>({
        id: "incident",
        data: [i],
        getPosition: (d) => [d.lon, d.lat],
        getRadius: 11,
        radiusUnits: "pixels",
        getFillColor: (d) => sourceRGBA(sourceKind(d), dark),
        stroked: true,
        getLineColor: ring,
        getLineWidth: 3,
        lineWidthUnits: "pixels",
        updateTriggers: { getFillColor: [dark], getLineColor: [dark] },
      }),
    ];
  }, [segments.data, i, dark]);

  return (
    <Map
      initialViewState={{ longitude: i.lon, latitude: i.lat, zoom: 16 }}
      mapStyle={dark ? MAP_STYLE.dark : MAP_STYLE.light}
      workerUrl={MAPLIBRE_WORKER_URL}
      style={{ width: "100%", height: "100%" }}
      attributionControl={{ compact: true }}
      cooperativeGestures
      minZoom={12}
      maxZoom={19}
    >
      <NavigationControl position="top-right" showCompass={false} />
      <DeckOverlay layers={layers} />
    </Map>
  );
}
