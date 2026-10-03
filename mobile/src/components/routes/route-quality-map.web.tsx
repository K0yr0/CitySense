/** Web: react-native-maps is not supported, so the route screen shows only its list UI. */
import type { RouteQuality, RouteWarning } from '@/lib/api';

export const ROUTE_MAP_SUPPORTED = false;

type Props = {
  quality: RouteQuality;
  highlighted?: RouteWarning | null;
  onWarningPress?: (warning: RouteWarning) => void;
  height?: number;
};

export function RouteQualityMap(_props: Props) {
  return null;
}
