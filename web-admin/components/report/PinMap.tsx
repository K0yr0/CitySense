"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useEffectEvent, useRef } from "react";
import Map, { Marker, NavigationControl, type MapRef } from "react-map-gl/maplibre";
import { usePrefersDark } from "@/lib/hooks";
import { MAP_STYLE, MAPLIBRE_WORKER_URL } from "@/lib/map";

export interface Pin {
  lon: number;
  lat: number;
}

/** Small map to drop / drag a location pin. `flyKey` changes -> recentre on the pin. */
export default function PinMap({ pin, onPin, flyKey }: { pin: Pin | null; onPin: (p: Pin) => void; flyKey: number }) {
  const dark = usePrefersDark();
  const ref = useRef<MapRef>(null);

  const flyToPin = useEffectEvent(() => {
    if (pin && ref.current) ref.current.flyTo({ center: [pin.lon, pin.lat], zoom: Math.max(16, ref.current.getZoom()), duration: 800 });
  });
  useEffect(() => {
    if (flyKey > 0) flyToPin();
  }, [flyKey]);

  return (
    <Map
      ref={ref}
      initialViewState={{ longitude: 21.0122, latitude: 52.2297, zoom: 14 }}
      mapStyle={dark ? MAP_STYLE.dark : MAP_STYLE.light}
      workerUrl={MAPLIBRE_WORKER_URL}
      style={{ width: "100%", height: "100%" }}
      attributionControl={{ compact: true }}
      cursor="crosshair"
      onClick={(e) => onPin({ lon: e.lngLat.lng, lat: e.lngLat.lat })}
    >
      <NavigationControl position="top-right" showCompass={false} />
      {pin && (
        <Marker
          longitude={pin.lon}
          latitude={pin.lat}
          anchor="bottom"
          draggable
          onDragEnd={(e) => onPin({ lon: e.lngLat.lng, lat: e.lngLat.lat })}
        >
          <svg width="34" height="44" viewBox="0 0 34 44" aria-label="Report location">
            <path d="M17 43S2 27.5 2 16.5a15 15 0 0 1 30 0C32 27.5 17 43 17 43Z" fill="var(--accent)" stroke="var(--surface)" strokeWidth="2.5" />
            <circle cx="17" cy="16.5" r="5.5" fill="var(--surface)" />
          </svg>
        </Marker>
      )}
    </Map>
  );
}
