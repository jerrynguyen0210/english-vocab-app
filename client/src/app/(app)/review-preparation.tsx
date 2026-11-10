import { useState } from 'react';
import { Pressable, StyleSheet, Switch, TextInput, View } from 'react-native';
import { AppScreen } from '@/components/app-screen';
import { NavigationLink } from '@/components/navigation-link';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';
import {
  selectPreviewWords,
  type ReviewPeriod,
  type ReviewSource,
} from '@/constants/review-preview';

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
    detail: 'Search your saved word topics',
    icon: '⌕',
  },
] as const;
export default function ReviewPreparationScreen() {
  const [source, setSource] = useState<ReviewSource>('time');
  const [period, setPeriod] = useState<ReviewPeriod>('Weekly');
  const [topic, setTopic] = useState('');
  const [includeOverdue, setIncludeOverdue] = useState(true);
  const words = selectPreviewWords(source, period, topic, includeOverdue);
  const count = words.length;
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
        <ThemedText style={styles.preview}>
          Sample data · practice only; progress is not saved.
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
                {count} words saved{' '}
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
                {count} words due now
              </ThemedText>
            </>
          ) : (
            <>
              <ThemedText style={styles.label}>TYPE A TOPIC</ThemedText>
              <TextInput
                accessibilityLabel="Search saved word topics"
                placeholder="Search topics"
                placeholderTextColor={colors.placeholder}
                value={topic}
                onChangeText={setTopic}
                style={styles.input}
                autoCorrect={false}
              />
              <ThemedText style={styles.badge}>
                {count} matching words
              </ThemedText>
              <ThemedText style={styles.detail}>
                Try Workplace communication, Travel or Wellbeing.
              </ThemedText>
            </>
          )}
        </View>
        <View style={styles.row}>
          <ThemedText accessibilityLiveRegion="polite" style={styles.summary}>
            {count} words ready
          </ThemedText>
          <ThemedText style={styles.next}>Answer mode next →</ThemedText>
        </View>
        {count ? (
          <NavigationLink
            href={{
              pathname: '/review',
              params: {
                preview: 'true',
                source,
                period,
                topic,
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
            <ThemedText style={styles.white}>No words to review</ThemedText>
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
  preview: { color: colors.secondary, fontSize: 11, lineHeight: 17 },
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
  input: {
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: 10,
    minHeight: 47,
    padding: 12,
    color: colors.text,
    fontSize: 14,
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
