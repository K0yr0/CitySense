/** react-native-maps has no web implementation: the web build shows no mini map. */
export type IncidentMiniMapProps = {
  lon: number;
  lat: number;
  color: string;
  title?: string;
  height?: number;
};

export function IncidentMiniMap(_props: IncidentMiniMapProps) {
  return null;
}
