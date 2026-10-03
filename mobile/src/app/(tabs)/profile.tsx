/**
 * M2 profile tab. Signed out: why to sign in + button. Signed in: trust score, counts
 * (GET /mobile/me) and "My reports" (GET /mobile/reports), pull-to-refresh, sign out.
 * The language picker sits at the top in both states.
 */
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, FlatList, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { ActionButton } from '@/components/profile/action-button';
import { LanguagePicker } from '@/components/profile/language-picker';
import { ReportRow } from '@/components/profile/report-row';
import { TrustCard } from '@/components/profile/trust-card';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { profileText } from '@/i18n/profile';
import { API_URL, ApiError, getMe, getMyReports, type Me, type MobileReport } from '@/lib/api';
import { useText } from '@/lib/i18n';
import { useSession } from '@/lib/session';

function ApiFooter() {
  const s = useText(profileText);
  return (
    <ThemedText type="code" themeColor="textSecondary" style={styles.footer}>
      {s.server(API_URL)}
    </ThemedText>
  );
}

function SignedOut() {
  const router = useRouter();
  const s = useText(profileText);
  const c = useText(commonText);
  return (
    <ScrollView contentContainerStyle={styles.content}>
      <LanguagePicker />
      <ThemedView type="backgroundElement" style={styles.card}>
        <ThemedText type="smallBold">{s.signedOutTitle}</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {s.signedOutBody}
        </ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {s.trustCarryOver}
        </ThemedText>
        <ActionButton label={c.signIn} onPress={() => router.push('/sign-in')} />
      </ThemedView>
      <ApiFooter />
    </ScrollView>
  );
}

function SignedIn() {
  const router = useRouter();
  const theme = useTheme();
  const s = useText(profileText);
  const c = useText(commonText);
  const { user, signOut } = useSession();
  const [me, setMe] = useState<Me | null>(null);
  const [reports, setReports] = useState<MobileReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const [meResult, reportsResult] = await Promise.allSettled([getMe(), getMyReports()]);
    const failure = [meResult, reportsResult].find((r) => r.status === 'rejected');
    if (failure && failure.reason instanceof ApiError && failure.reason.status === 401) {
      await signOut(); // token expired or revoked
      return;
    }
    if (meResult.status === 'fulfilled') setMe(meResult.value);
    if (reportsResult.status === 'fulfilled') setReports(reportsResult.value);
    setError(
      failure ? (failure.reason instanceof Error ? failure.reason.message : String(failure.reason)) : null,
    );
  }, [signOut]);

  // Reload whenever the tab is shown (e.g. after sending a report).
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const header = (
    <View style={styles.headerBlock}>
      <LanguagePicker />
      <ThemedView type="backgroundElement" style={styles.card}>
        <ThemedText type="smallBold">{user?.name || s.defaultName}</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {user?.email}
        </ThemedText>
      </ThemedView>

      {me ? (
        <TrustCard me={me} />
      ) : (
        !error && <ActivityIndicator color={theme.tint} style={styles.spinner} />
      )}

      {error && (
        <ThemedView type="backgroundElement" style={styles.card}>
          <ThemedText type="small" style={{ color: theme.danger }}>
            {s.loadFailed}
          </ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            {error}
          </ThemedText>
        </ThemedView>
      )}

      <ThemedText type="smallBold" style={styles.sectionTitle}>
        {s.myReports}
      </ThemedText>
    </View>
  );

  const empty =
    reports === null ? null : (
      <ThemedText type="small" themeColor="textSecondary" style={styles.empty}>
        {s.noReports(c.tabs.report)}
      </ThemedText>
    );

  const footer = (
    <View style={styles.footerBlock}>
      <ActionButton label={c.signOut} variant="danger" onPress={() => signOut()} />
      <ApiFooter />
    </View>
  );

  return (
    <FlatList
      data={reports ?? []}
      keyExtractor={(r) => String(r.report_id)}
      renderItem={({ item }) => {
        const incident = item.incident;
        return (
          <ReportRow
            report={item}
            onPress={incident ? () => router.push(`/incident/${incident.id}`) : undefined}
          />
        );
      }}
      ListHeaderComponent={header}
      ListEmptyComponent={empty}
      ListFooterComponent={footer}
      ItemSeparatorComponent={Separator}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={theme.tint} />}
    />
  );
}

function Separator() {
  return <View style={styles.separator} />;
}

export default function ProfileScreen() {
  const theme = useTheme();
  const { status } = useSession();

  return (
    <ThemedView style={styles.flex}>
      {status === 'loading' ? (
        <View style={styles.center}>
          <ActivityIndicator color={theme.tint} />
        </View>
      ) : status === 'signedIn' ? (
        <SignedIn />
      ) : (
        <SignedOut />
      )}
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  content: {
    padding: Spacing.three,
    gap: Spacing.three,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  headerBlock: {
    gap: Spacing.three,
    marginBottom: Spacing.two,
  },
  card: {
    padding: Spacing.three,
    borderRadius: Spacing.three,
    gap: Spacing.two,
  },
  spinner: {
    marginVertical: Spacing.three,
  },
  sectionTitle: {
    marginTop: Spacing.two,
  },
  empty: {
    paddingVertical: Spacing.two,
  },
  separator: {
    height: Spacing.two,
  },
  footerBlock: {
    marginTop: Spacing.four,
    gap: Spacing.three,
  },
  footer: {
    textAlign: 'center',
  },
});
