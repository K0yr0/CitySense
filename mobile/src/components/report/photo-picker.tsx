import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { ActionButton } from '@/components/report/action-button';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { reportText } from '@/i18n/report';
import type { NewReport } from '@/lib/api';
import { useText } from '@/lib/i18n';

export type ReportPhoto = NonNullable<NewReport['photo']>;

const PICK_OPTIONS: ImagePicker.ImagePickerOptions = {
  mediaTypes: ['images'],
  quality: 0.7,
  allowsEditing: false,
  exif: false,
};

type Props = {
  photo: ReportPhoto | null;
  onChange: (photo: ReportPhoto | null) => void;
  disabled?: boolean;
};

/** Optional photo: take one with the camera or pick from the gallery; shows a thumbnail. */
export function PhotoPicker({ photo, onChange, disabled = false }: Props) {
  const theme = useTheme();
  const s = useText(reportText);
  const [error, setError] = useState<string | null>(null);

  const accept = (result: ImagePicker.ImagePickerResult) => {
    if (result.canceled || !result.assets?.length) return;
    const asset = result.assets[0];
    onChange({ uri: asset.uri, mimeType: asset.mimeType ?? 'image/jpeg', fileName: asset.fileName ?? null });
  };

  const takePhoto = async () => {
    setError(null);
    try {
      const current = await ImagePicker.getCameraPermissionsAsync();
      const permission = current.granted ? current : await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) {
        setError(s.cameraDenied);
        return;
      }
      accept(await ImagePicker.launchCameraAsync(PICK_OPTIONS));
    } catch (e) {
      setError(s.cameraFailed(e instanceof Error ? e.message : String(e)));
    }
  };

  const pickFromLibrary = async () => {
    setError(null);
    try {
      accept(await ImagePicker.launchImageLibraryAsync(PICK_OPTIONS));
    } catch (e) {
      setError(s.galleryFailed(e instanceof Error ? e.message : String(e)));
    }
  };

  return (
    <View style={styles.container}>
      <ThemedText type="smallBold">{s.photoLabel}</ThemedText>
      {photo ? (
        <View style={styles.previewRow}>
          <Image
            source={{ uri: photo.uri }}
            style={[styles.thumbnail, { backgroundColor: theme.backgroundElement }]}
            contentFit="cover"
            accessibilityLabel={s.photoA11y}
          />
          <View style={styles.previewActions}>
            <ThemedText type="small" themeColor="textSecondary">
              {s.photoAdded}
            </ThemedText>
            <Pressable
              accessibilityRole="button"
              disabled={disabled}
              onPress={() => onChange(null)}
              hitSlop={8}
              style={({ pressed }) => ({ opacity: disabled ? 0.5 : pressed ? 0.6 : 1 })}>
              <ThemedText type="smallBold" style={{ color: theme.danger }}>
                {s.removePhoto}
              </ThemedText>
            </Pressable>
          </View>
        </View>
      ) : (
        <View style={styles.buttons}>
          <ActionButton
            label={s.takePhoto}
            variant="secondary"
            compact
            disabled={disabled}
            onPress={takePhoto}
            style={styles.flex}
          />
          <ActionButton
            label={s.pickPhoto}
            variant="secondary"
            compact
            disabled={disabled}
            onPress={pickFromLibrary}
            style={styles.flex}
          />
        </View>
      )}
      {error ? (
        <ThemedText type="small" style={{ color: theme.danger }}>
          {error}
        </ThemedText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: Spacing.two,
  },
  buttons: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
  flex: {
    flex: 1,
  },
  previewRow: {
    flexDirection: 'row',
    gap: Spacing.three,
    alignItems: 'center',
  },
  thumbnail: {
    width: 96,
    height: 96,
    borderRadius: 12,
  },
  previewActions: {
    flex: 1,
    gap: Spacing.two,
  },
});
