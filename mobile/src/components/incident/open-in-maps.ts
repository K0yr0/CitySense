import { Linking, Platform } from 'react-native';

function googleMapsUrl(lat: number, lon: number): string {
  return `https://www.google.com/maps/search/?api=1&query=${lat},${lon}`;
}

/** Opens the point in the phone's maps app (Apple Maps / Google Maps), falling back to the web. */
export async function openInMaps(lon: number, lat: number, label: string): Promise<void> {
  const q = encodeURIComponent(label);
  const url = Platform.select({
    ios: `https://maps.apple.com/?ll=${lat},${lon}&q=${q}`,
    android: `geo:${lat},${lon}?q=${lat},${lon}(${q})`,
    default: googleMapsUrl(lat, lon),
  });
  try {
    await Linking.openURL(url);
  } catch {
    await Linking.openURL(googleMapsUrl(lat, lon)).catch(() => undefined);
  }
}
