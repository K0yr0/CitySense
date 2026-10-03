/** Shared props of the native map (incident-map.tsx) and its web fallback (incident-map.web.tsx). */
import type { Ref } from 'react';

import type { PublicIncident } from '@/lib/api';
import type { LatLng, Region } from '@/lib/geo';

/** A measured road/rail segment, already converted for drawing: only a colour, never a number. */
export type MapSegment = { key: string; color: string; width: number; coords: LatLng[] };

export type UserPosition = { coords: LatLng; accuracy: number | null };

export type IncidentMapHandle = {
  animateTo: (region: Region) => void;
};

export type IncidentMapProps = {
  ref?: Ref<IncidentMapHandle>;
  initialRegion: Region;
  segments: MapSegment[];
  incidents: PublicIncident[];
  showSegments: boolean;
  showIncidents: boolean;
  selectedId: number | null;
  user: UserPosition | null;
  dark: boolean;
  /** Space taken by overlays at the top/bottom, so map controls/logo stay visible. */
  topInset: number;
  bottomInset: number;
  onRegionChangeComplete: (region: Region) => void;
  onSelectIncident: (incident: PublicIncident | null) => void;
};
