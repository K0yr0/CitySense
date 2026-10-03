/**
 * Vector icons (SF Symbols on iOS, Material Symbols on Android / web) via expo-symbols.
 * Use these instead of emoji: emoji depend on the device's emoji font (the iOS 26 simulator, for
 * example, draws them as "?" boxes) and look different on every platform.
 */
import { SymbolView, type SymbolViewProps } from 'expo-symbols';
import type { ColorValue, StyleProp, ViewStyle } from 'react-native';

import type { IssueType } from '@/lib/api';

const ICONS = {
  road_damage: { ios: 'road.lanes', android: 'edit_road', web: 'edit_road' },
  tram_track: { ios: 'tram.fill', android: 'tram', web: 'tram' },
  streetlight: { ios: 'lightbulb.fill', android: 'lightbulb', web: 'lightbulb' },
  flooding: { ios: 'drop.fill', android: 'water_drop', web: 'water_drop' },
  waste: { ios: 'trash.fill', android: 'delete', web: 'delete' },
  other: { ios: 'questionmark.circle.fill', android: 'help', web: 'help' },
  tram: { ios: 'tram.fill', android: 'tram', web: 'tram' },
  bus: { ios: 'bus.fill', android: 'directions_bus', web: 'directions_bus' },
  pin: { ios: 'mappin.and.ellipse', android: 'location_on', web: 'location_on' },
  route: {
    ios: 'point.topleft.down.to.point.bottomright.curvepath',
    android: 'route',
    web: 'route',
  },
  warning: { ios: 'exclamationmark.triangle.fill', android: 'warning', web: 'warning' },
  check: { ios: 'checkmark.circle.fill', android: 'check_circle', web: 'check_circle' },
  trash: { ios: 'trash', android: 'delete', web: 'delete' },
  add: { ios: 'plus', android: 'add', web: 'add' },
  close: { ios: 'xmark', android: 'close', web: 'close' },
  search: { ios: 'magnifyingglass', android: 'search', web: 'search' },
  sensors: { ios: 'antenna.radiowaves.left.and.right', android: 'sensors', web: 'sensors' },
  people: { ios: 'person.2.fill', android: 'group', web: 'group' },
  clock: { ios: 'clock', android: 'schedule', web: 'schedule' },
  info: { ios: 'info.circle', android: 'info', web: 'info' },
} satisfies Record<string, SymbolViewProps['name']>;

export type IconName = keyof typeof ICONS;

type Props = {
  name: IconName;
  size?: number;
  color: ColorValue;
  style?: StyleProp<ViewStyle>;
};

export function Icon({ name, size = 20, color, style }: Props) {
  return <SymbolView name={ICONS[name]} size={size} tintColor={color} style={[{ width: size, height: size }, style]} />;
}

/** The icon of an incident type. */
export function TypeIcon({ type, size, color }: { type: IssueType | null | undefined; size?: number; color: ColorValue }) {
  return <Icon name={type && type in ICONS ? type : 'other'} size={size} color={color} />;
}
