import { useState } from 'react';
import { StyleSheet, Switch, View } from 'react-native';

import { ActionButton } from '@/components/report/action-button';
import { LocationPreview } from '@/components/report/location-preview';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import type { LocationState } from '@/hooks/use-location';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { reportText } from '@/i18n/report';
import { useText } from '@/lib/i18n';

/** Above this the pin may land on the wrong street; we still allow it but say so. */
const LOW_ACCURACY_M = 50;

type Props = {
  location: LocationState;
  attach: boolean;
  onAttachChange: (attach: boolean) => void;
  disabled?: boolean;
};

/** "Your location is added (±N m)" with refresh, a toggle to leave the location out, and a small map. */
export function LocationField({ location, attach, onAttachChange, disabled = false }: Props) {
  const theme = useTheme();
  const s = useText(reportText);
  const c = useText(commonText);
  const [refreshing, setRefreshing] = useState(false);
  const { coords, accuracy, permission, error } = location;

  const refresh = async () => {
    setRefreshing(true);
    try {
      await location.refresh();
    } finally {
      setRefreshing(false);
    }
  };

  let status: string;
  let tone: 'ok' | 'muted' | 'warn' = 'muted';
  if (!attach) {
    status = s.locationOff;
  } else if (coords) {
    status =
      accuracy != null ? s.locationAddedAccuracy(Math.max(1, Math.round(accuracy))) : s.locationAdded;
    tone = accuracy != null && accuracy > LOW_ACCURACY_M ? 'warn' : 'ok';
  } else if (permission === 'denied') {
    status = s.locationDenied;
    tone = 'warn';
  } else if (error) {
    status = s.locationFailed(error);
    tone = 'warn';
  } else {
    status = s.locating;
  }

  const color = tone === 'ok' ? theme.success : tone === 'warn' ? theme.danger : theme.textSecondary;

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <ThemedText type="smallBold" style={styles.flex}>
          {s.locationLabel}
        </ThemedText>
        <Switch
          accessibilityLabel={s.locationA11y}
          value={attach}
          onValueChange={onAttachChange}
          disabled={disabled}
          trackColor={{ true: theme.tint, false: theme.backgroundSelected }}
        />
      </View>

      <View style={styles.statusRow}>
        <ThemedText type="small" style={[styles.flex, { color }]}>
          {status}
        </ThemedText>
        {attach ? (
          <ActionButton
            label={coords ? s.refresh : permission === 'denied' ? s.allow : c.retry}
            variant="secondary"
            compact
            loading={refreshing}
            disabled={disabled}
            onPress={refresh}
          />
        ) : null}
      </View>

      {attach && coords && accuracy != null && accuracy > LOW_ACCURACY_M ? (
        <ThemedText type="small" themeColor="textSecondary">
          {s.lowAccuracy}
        </ThemedText>
      ) : null}

      {attach && coords ? <LocationPreview coords={coords} accuracy={accuracy} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: Spacing.two,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  flex: {
    flex: 1,
  },
});
