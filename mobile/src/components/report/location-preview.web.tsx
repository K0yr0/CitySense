import type { LatLng } from '@/lib/geo';

type Props = { coords: LatLng; accuracy: number | null };

/** No map preview on web (react-native-maps is native only); the coordinates text is enough. */
export function LocationPreview(_props: Props) {
  return null;
}
