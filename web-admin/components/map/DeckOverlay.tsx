"use client";

import { MapboxOverlay, type MapboxOverlayProps } from "@deck.gl/mapbox";
import { useEffect } from "react";
import { useControl } from "react-map-gl/maplibre";

/** deck.gl layers rendered on top of a react-map-gl (MapLibre) map. */
export default function DeckOverlay(props: MapboxOverlayProps) {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay(props));
  useEffect(() => {
    overlay.setProps(props);
  });
  return null;
}
