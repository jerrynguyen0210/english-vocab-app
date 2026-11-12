import { ReviewEmptyState } from '@/components/review-empty-state';
import { useFocusEffect } from 'expo-router';
import { authenticatedFetch } from '@/services/auth';
import { connectionMessage } from '@/services/connectivity';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Switch, View } from 'react-native';
import { AppScreen } from '@/components/app-screen';
import { NavigationLink } from '@/components/navigation-link';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';
import {
  reviewQuery,
  reviewEmptyKind,
  type ReviewSummary,
  type ReviewPeriod,
  type ReviewSource,
} from '@/services/review';

const sources = [
  {
    key: 'time',
    title: 'By time',
    detail: 'Words added in a selected period',
    icon: '◷',
  },
  {
    key: 'recall',
    title: 'SM-2 recall',
    detail: 'Review words scheduled as due',
    icon: '↗',
  },
  {
    key: 'topic',
    title: 'By topic',
    detail: 'Coming later',
    icon: '⌕',
  },
] as const;
export default function ReviewPreparationScreen() {
  const [source, setSource] = useState<ReviewSource>('time');
  const [period, setPeriod] = useState<ReviewPeriod>('Weekly');
  const [includeOverdue, setIncludeOverdue] = useState(true);
  const query = reviewQuery({
    source,
    period,
    includeOverdue: String(includeOverdue),
  });
  const [ready, setReady] = useState<{
    query: string;
    count: number;
    matching: number;
    summary: ReviewSummary | null;
  } | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const count = ready?.query === query ? ready.count : null;
  useFocusEffect(
    useCallback(() => {
      // Changing retry explicitly reloads the current selection.
      void retry;
      let active = true;
      setReady(null);
      setError('');
      const timer = setTimeout(() => {
        if (source === 'topic') {
          setReady({ query, count: 0, matching: 0, summary: null });
          return;
        }
        void authenticatedFetch(`/reviews/preparation?${query}`)
          .then(async (response) => {
            if (!response.ok) throw new Error();
            const result = await response.json();
            if (active)
              setReady({
                query,
                count: result.count,
                matching: result.matching_count,
                summary: result,
              });
          })
          .catch((failure) => {
            if (active)
              setError(
                connectionMessage(
                  failure,
                  'Could not load ready words. Please try again.',
                ),
              );
          });
      }, 250);
      return () => {
        active = false;
        clearTimeout(timer);
      };
    }, [query, retry, source]),
  );
  const startLabel = `Start review · ${count} words`;
  return (
    <AppScreen selected="Review">
      <View style={styles.content}>
        <ThemedText accessibilityRole="header" style={styles.title}>
          Prepare your review
        </ThemedText>
        <ThemedText style={styles.detail}>
          Choose which words to practise.
        </ThemedText>
        <ThemedText style={styles.label}>REVIEW SOURCE</ThemedText>
        <View style={styles.sources}>
          {sources.map(({ key, title, detail, icon }) => (
            <Pressable
              key={key}
              accessibilityRole="radio"
              accessibilityState={{ checked: source === key }}
              onPress={() => setSource(key)}
              style={[styles.source, source === key && styles.selected]}
            >
              <View style={styles.icon}>
                <ThemedText style={styles.iconText}>{icon}</ThemedText>
              </View>
              <View style={styles.sourceText}>
                <ThemedText style={styles.sourceTitle}>{title}</ThemedText>
                <ThemedText style={styles.detail}>{detail}</ThemedText>
              </View>
              <View
                style={[styles.radio, source === key && styles.radioSelected]}
              >
                {source === key && <View style={styles.dot} />}
              </View>
            </Pressable>
          ))}
        </View>
        <View style={styles.panel}>
          {source === 'time' ? (
            <>
              <ThemedText style={styles.label}>SELECT TIME PERIOD</ThemedText>
              <View style={styles.periods}>
                {(['Yesterday', 'Weekly', 'Monthly'] as const).map((value) => (
                  <Pressable
                    key={value}
                    accessibilityRole="radio"
                    accessibilityState={{ checked: period === value }}
                    onPress={() => setPeriod(value)}
                    style={[styles.period, period === value && styles.active]}
                  >
                    <ThemedText
                      style={[
                        styles.periodText,
                        period === value && styles.white,
                      ]}
                    >
                      {value}
                    </ThemedText>
                  </Pressable>
                ))}
              </View>
              <ThemedText style={styles.summary}>
                {count === null ? '…' : ready?.matching} words saved{' '}
                {period === 'Yesterday'
                  ? 'yesterday'
                  : `in the last ${period === 'Weekly' ? 7 : 30} days`}
              </ThemedText>
              <ThemedText style={styles.detail}>
                Yesterday · previous day | Monthly · last 30 days
              </ThemedText>
            </>
          ) : source === 'recall' ? (
            <>
              <ThemedText style={styles.label}>
                SPACED REPETITION · SM-2
              </ThemedText>
              <ThemedText style={styles.summary}>
                Practise words due today or overdue.
              </ThemedText>
              <ThemedText style={styles.detail}>
                Review timing adapts to your recall.
              </ThemedText>
              <View style={styles.row}>
                <ThemedText style={styles.summary}>
                  Include overdue words
                </ThemedText>
                <Switch
                  accessibilityLabel="Include overdue words"
                  value={includeOverdue}
                  onValueChange={setIncludeOverdue}
                  trackColor={{ true: colors.primary }}
                />
              </View>
              <ThemedText style={styles.badge}>
                {count === null ? '…' : ready?.matching} words due today
              </ThemedText>
            </>
          ) : (
            <>
              <ThemedText style={styles.summary}>
                Topic search is coming later.
              </ThemedText>
              <ThemedText style={styles.detail}>
                Choose By time or SM-2 recall to start a review.
              </ThemedText>
            </>
          )}
        </View>
        <View style={styles.row}>
          <ThemedText accessibilityLiveRegion="polite" style={styles.summary}>
            {source === 'topic'
              ? 'Not available yet'
              : count === null
                ? error
                  ? 'Count unavailable'
                  : 'Loading ready words…'
                : `${count} words ready`}
          </ThemedText>
          <ThemedText style={styles.next}>Answer mode next →</ThemedText>
        </View>
        {!!error && (
          <View accessibilityLiveRegion="polite">
            <ThemedText style={styles.detail}>{error}</ThemedText>
            <Pressable
              accessibilityRole="button"
              onPress={() => setRetry((value) => value + 1)}
              style={styles.period}
            >
              <ThemedText style={styles.periodText}>Try again</ThemedText>
            </Pressable>
          </View>
        )}
        {source !== 'topic' && count === 0 && !error && ready?.summary && (
          <ReviewEmptyState
            kind={reviewEmptyKind(ready.summary, ready.matching)}
          />
        )}
        {count !== null && ready && ready.matching > count && (
          <ThemedText style={styles.detail}>
            {ready.matching} matching words · each session includes up to 50
            words.
          </ThemedText>
        )}
        {count !== null && count > 0 && !error ? (
          <NavigationLink
            href={{
              pathname: '/review',
              params: {
                source,
                period,
                includeOverdue: String(includeOverdue),
              },
            }}
            label={startLabel}
            style={styles.button}
          >
            <ThemedText style={styles.white}>{startLabel}</ThemedText>
          </NavigationLink>
        ) : (
          <Pressable
            disabled
            accessibilityRole="button"
            accessibilityState={{ disabled: true }}
            style={[styles.button, styles.disabled]}
          >
            <ThemedText style={styles.white}>
              {error
                ? 'Count unavailable'
                : count === null
                  ? 'Loading…'
                  : source === 'topic'
                    ? 'Coming later'
                    : 'No words to review'}
            </ThemedText>
          </Pressable>
        )}
      </View>
    </AppScreen>
  );
}
const styles = StyleSheet.create({
  content: {
    width: '100%',
    maxWidth: 600,
    alignSelf: 'center',
    padding: 22,
    paddingTop: 25,
    paddingBottom: 36,
    gap: 16,
  },
  title: {
    color: colors.text,
    fontSize: 27,
    lineHeight: 34,
    fontWeight: '800',
  },
  detail: { color: colors.secondary, fontSize: 12, lineHeight: 19 },
  label: {
    color: colors.secondary,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.8,
  },
  sources: { gap: 8 },
  source: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 13,
    backgroundColor: colors.surface,
    padding: 12,
    minHeight: 73,
  },
  selected: {
    borderColor: colors.primary,
    backgroundColor: colors.primarySoft,
  },
  icon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconText: { color: colors.primary, fontSize: 28, lineHeight: 34 },
  sourceText: { flex: 1, gap: 3 },
  sourceTitle: { color: colors.text, fontSize: 16, fontWeight: '700' },
  radio: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioSelected: { borderColor: colors.primary },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.primary,
  },
  panel: {
    marginTop: 6,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 13,
    backgroundColor: colors.surface,
    padding: 16,
    gap: 14,
    minHeight: 158,
  },
  periods: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  period: {
    flexGrow: 1,
    padding: 10,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 9,
    alignItems: 'center',
    minHeight: 44,
  },
  active: { backgroundColor: colors.primary, borderColor: colors.primary },
  periodText: { color: colors.secondary, fontSize: 13, fontWeight: '600' },
  summary: {
    color: colors.text,
    fontSize: 12,
    fontWeight: '600',
    flexShrink: 1,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  badge: {
    color: colors.success,
    backgroundColor: colors.successBackground,
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 10,
    fontSize: 11,
    fontWeight: '700',
  },
  next: { color: colors.primary, fontSize: 11 },
  button: {
    backgroundColor: colors.primary,
    minHeight: 53,
    padding: 14,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },
  white: { color: colors.surface, fontSize: 14, fontWeight: '700' },
  disabled: { opacity: 0.5 },
});
