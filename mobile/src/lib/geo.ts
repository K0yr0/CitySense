/** Geometry helpers. The backend uses (lon, lat); react-native-maps uses {latitude, longitude}. */
import { commonText } from '@/i18n/common';
import type { BBox, LonLat } from '@/lib/api';
import { formatNumber, text } from '@/lib/i18n';

export type LatLng = { latitude: number; longitude: number };

export type Region = LatLng & { latitudeDelta: number; longitudeDelta: number };

/** Central Warsaw, where the demo data lives. */
export const WARSAW_REGION: Region = {
  latitude: 52.2297,
  longitude: 21.0122,
  latitudeDelta: 0.03,
  longitudeDelta: 0.03,
};

export function toLatLng([lon, lat]: LonLat): LatLng {
  return { latitude: lat, longitude: lon };
}

export function toLonLat({ latitude, longitude }: LatLng): LonLat {
  return [longitude, latitude];
}

/** Great-circle distance in metres. */
export function distanceM(a: LatLng, b: LatLng): number {
  const R = 6371000;
  const rad = Math.PI / 180;
  const dLat = (b.latitude - a.latitude) * rad;
  const dLon = (b.longitude - a.longitude) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.latitude * rad) * Math.cos(b.latitude * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/** Bounding box of a map region, optionally padded (0.2 = 20 % on each side). */
export function bboxOf(region: Region, pad = 0): BBox {
  const halfLat = (region.latitudeDelta / 2) * (1 + pad);
  const halfLon = (region.longitudeDelta / 2) * (1 + pad);
  return [
    region.longitude - halfLon,
    region.latitude - halfLat,
    region.longitude + halfLon,
    region.latitude + halfLat,
  ];
}

/** "120 m" / "1.4 km" (decimal separator and units follow the app language) */
export function formatDistance(m: number): string {
  const units = text(commonText).units;
  if (m < 1000) return `${Math.round(m)} ${units.m}`;
  return `${formatNumber(Math.round(m / 100) / 10)} ${units.km}`;
}
