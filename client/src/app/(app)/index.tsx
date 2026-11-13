import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { authenticatedFetch } from '@/services/auth';
import { connectionMessage } from '@/services/connectivity';
import { reviewEmptyKind, type LearningSummary } from '@/services/review';
import { LearningStatistics } from '@/components/learning-statistics';
import { ReviewEmptyState } from '@/components/review-empty-state';
import { Image } from 'expo-image';
import { Platform, Pressable, StyleSheet, View } from 'react-native';
import { AppScreen } from '@/components/app-screen';
import { NavigationLink } from '@/components/navigation-link';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';

export default function HomeScreen() {
  const [summary, setSummary] = useState<LearningSummary | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useFocusEffect(
    useCallback(() => {
      void retry;
      let active = true;
      setSummary(null);
      setError('');
      void authenticatedFetch('/reviews/summary')
        .then(async (response) => {
          if (!response.ok) throw new Error();
          const result: LearningSummary = await response.json();
          if (active) setSummary(result);
        })
        .catch((failure) => {
          if (active)
            setError(
              connectionMessage(
                failure,
                'Could not load your progress. Please try again.',
              ),
            );
        });
      return () => {
        active = false;
      };
    }, [retry]),
  );
  const empty =
    summary && (summary.saved_count === 0 || summary.due_count === 0);
  return (
    <AppScreen selected="Home">
      <View style={styles.content}>
        <ThemedText style={styles.greeting} accessibilityRole="header">
          Good morning
        </ThemedText>
        <ThemedText style={styles.subtitle}>
          Make today a word better.
        </ThemedText>
        {!!error && (
          <View accessibilityLiveRegion="polite">
            <ThemedText style={styles.subtitle}>{error}</ThemedText>
            <Pressable
              accessibilityRole="button"
              onPress={() => setRetry((value) => value + 1)}
              style={[styles.action, styles.secondaryAction]}
            >
              <ThemedText style={styles.actionText}>Try again</ThemedText>
            </Pressable>
          </View>
        )}
        {summary ? (
          <LearningStatistics summary={summary} />
        ) : (
          <ThemedText style={styles.loading} accessibilityLiveRegion="polite">
            {error
              ? 'Progress unavailable'
              : 'Loading your learning statistics…'}
          </ThemedText>
        )}
        {empty && (
          <ReviewEmptyState
            kind={reviewEmptyKind(summary)}
            showAction={summary.saved_count === 0}
          />
        )}
        {summary?.saved_count !== 0 && (
          <>
            <ThemedText style={styles.sectionTitle} accessibilityRole="header">
              What would you like to do?
            </ThemedText>
            <View style={styles.actions}>
              <NavigationLink
                href="/add-word"
                label="Add word"
                style={[styles.action, styles.primaryAction]}
              >
                <Image
                  source={require('@/assets/images/wordwell/add-white.svg')}
                  style={styles.icon}
                  accessible={false}
                />
                <ThemedText style={[styles.actionText, styles.primaryText]}>
                  Add word
                </ThemedText>
              </NavigationLink>
              <NavigationLink
                href="/review-preparation"
                label="Start review"
                style={[styles.action, styles.secondaryAction]}
              >
                <Image
                  source={require('@/assets/images/wordwell/review-dark.svg')}
                  style={styles.icon}
                  accessible={false}
                />
                <ThemedText style={styles.actionText}>Start review</ThemedText>
              </NavigationLink>
            </View>
            <View style={styles.progressCard}>
              <ThemedText style={styles.progressTitle}>
                Your daily progress
              </ThemedText>
              <ThemedText style={styles.progressDetail}>
                {summary
                  ? `${summary.saved_count} saved words · ${Math.min(summary.due_count, 50)} ready to review`
                  : 'Your progress will appear here.'}
              </ThemedText>
            </View>
          </>
        )}
      </View>
    </AppScreen>
  );
}
const fontFamily = Platform.select({
  web: 'Arial, sans-serif',
  default: undefined,
});
const styles = StyleSheet.create({
  content: {
    width: '100%',
    maxWidth: 600,
    alignSelf: 'center',
    paddingHorizontal: 22,
    paddingTop: 25,
    paddingBottom: 36,
  },
  greeting: {
    fontFamily,
    color: colors.text,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '800',
  },
  subtitle: {
    fontFamily,
    color: colors.secondary,
    fontSize: 13,
    lineHeight: 20,
    fontWeight: '400',
    marginTop: 9,
  },
  loading: {
    color: colors.secondary,
    marginTop: 30,
    textAlign: 'center',
  },
  sectionTitle: {
    fontFamily,
    color: colors.text,
    fontSize: 19,
    lineHeight: 25,
    fontWeight: '700',
    marginTop: 31,
  },
  actions: { gap: 16, marginTop: 22 },
  action: {
    minHeight: 54,
    borderRadius: 13,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
    padding: 14,
  },
  primaryAction: { backgroundColor: colors.primary },
  secondaryAction: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
  },
  actionText: {
    fontFamily,
    color: colors.text,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '600',
  },
  primaryText: { color: colors.surface },
  progressCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 16,
    padding: 17,
    minHeight: 100,
    marginTop: 23,
  },
  progressTitle: {
    fontFamily,
    color: colors.text,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '600',
  },
  progressDetail: {
    fontFamily,
    color: colors.secondary,
    fontSize: 13,
    lineHeight: 20,
    fontWeight: '400',
    marginTop: 7,
  },
  icon: { width: 24, height: 24 },
});
