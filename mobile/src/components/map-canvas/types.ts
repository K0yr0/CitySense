/**
 * Declarative map API shared by every map in the app (data in, events out).
 * iOS: react-native-maps (Apple Maps). Android: Leaflet in a WebView with OpenStreetMap
 * tiles, because Google rejects Expo Go's built-in Maps key and its map renders nothing there.
 */
import type { Ref } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';

import type { LatLng, Region } from '@/lib/geo';

export type CanvasPolyline = {
  id: string;
  coords: LatLng[];
  color: string;
  width: number;
  zIndex?: number;
  /** Dashed line: [dash, gap] in pixels. */
  dash?: [number, number];
};

export type CanvasCircle = {
  id: string;
  center: LatLng;
  /** Metres. */
  radius: number;
  strokeColor: string;
  fillColor: string;
  strokeWidth?: number;
};

export type CanvasMarker = {
  id: string;
  coord: LatLng;
  color: string;
  /** "pin" (default) or "dot" (the user's position). */
  kind?: 'pin' | 'dot';
  /** Shown when the pin is tapped; tapping it fires onCalloutPress. */
  title?: string;
  /** Second line under the title. */
  description?: string;
  draggable?: boolean;
  zIndex?: number;
};

export type EdgeInsets = { top: number; bottom: number; left: number; right: number };

export type MapCanvasHandle = {
  animateTo: (region: Region) => void;
  fitTo: (coords: LatLng[], padding?: EdgeInsets) => void;
};

export type MapCanvasProps = {
  ref?: Ref<MapCanvasHandle>;
  style?: StyleProp<ViewStyle>;
  initialRegion: Region;
  /** false = a still picture (no pan / zoom / taps). Default true. */
  interactive?: boolean;
  dark?: boolean;
  /** Space covered by overlays, so the logo / attribution stay visible. */
  padding?: EdgeInsets;
  polylines?: CanvasPolyline[];
  circles?: CanvasCircle[];
  markers?: CanvasMarker[];
  onPress?: (coord: LatLng) => void;
  onMarkerPress?: (id: string) => void;
  onCalloutPress?: (id: string) => void;
  onMarkerDragEnd?: (id: string, coord: LatLng) => void;
  onRegionChangeComplete?: (region: Region) => void;
  onReady?: () => void;
};

export const NO_PADDING: EdgeInsets = { top: 0, bottom: 0, left: 0, right: 0 };
