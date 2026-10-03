import { Tabs } from 'expo-router/js-tabs';
import { SymbolView, type SymbolViewProps } from 'expo-symbols';
import type { ColorValue } from 'react-native';

import { useTheme } from '@/hooks/use-theme';

function TabIcon({ name, color }: { name: SymbolViewProps['name']; color: ColorValue }) {
  return <SymbolView name={name} tintColor={color} size={24} />;
}

export default function TabLayout() {
  const theme = useTheme();
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: theme.tint,
        tabBarInactiveTintColor: theme.textSecondary,
      }}>
      <Tabs.Screen
        name="index"
        options={{
          title: 'Harita',
          tabBarIcon: ({ color }) => (
            <TabIcon name={{ ios: 'map', android: 'map', web: 'map' }} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="report"
        options={{
          title: 'Bildir',
          tabBarIcon: ({ color }) => (
            <TabIcon
              name={{ ios: 'exclamationmark.bubble', android: 'campaign', web: 'campaign' }}
              color={color}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="routes"
        options={{
          title: 'Rotalarım',
          tabBarIcon: ({ color }) => (
            <TabIcon
              name={{ ios: 'point.topleft.down.to.point.bottomright.curvepath', android: 'route', web: 'route' }}
              color={color}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profil',
          tabBarIcon: ({ color }) => (
            <TabIcon
              name={{ ios: 'person.crop.circle', android: 'person', web: 'person' }}
              color={color}
            />
          ),
        }}
      />
    </Tabs>
  );
}
