import { StyleSheet, View } from 'react-native';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';
import type { LearningSummary } from '@/services/review';

const plotHeight = 180;

export function LearningStatistics({ summary }: { summary: LearningSummary }) {
  const columns = [
    { label: 'Words due today', value: summary.due_count },
    { label: 'Saved', value: summary.saved_count },
    { label: 'Learned', value: summary.learned_count },
    { label: 'Total', value: summary.total_count },
  ];
  const maximum = Math.max(1, ...columns.map(({ value }) => value));
  // Four equal intervals, with integer ticks even for a small or empty bank.
  const roughStep = maximum / 4;
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const step = Math.max(1, Math.ceil(roughStep / magnitude) * magnitude);
  const ceiling = step * 4;

  return (
    <View style={styles.container}>
      <ThemedText style={styles.heading} accessibilityRole="header">
        Learning statistics
      </ThemedText>
      <View
        accessible
        accessibilityLabel={`Learning statistics. ${columns.map(({ label, value }) => `${label}: ${value}`).join('. ')}.`}
        style={styles.chart}
      >
        <View style={styles.axis}>
          {[4, 3, 2, 1, 0].map((tick) => (
            <ThemedText key={tick} style={styles.tick}>
              {tick * step}
            </ThemedText>
          ))}
        </View>
        <View style={styles.plotAndLabels}>
          <View style={styles.plot}>
            <View style={styles.grid}>
              {[4, 3, 2, 1, 0].map((tick) => (
                <View key={tick} style={styles.gridLine} />
              ))}
            </View>
            <View style={styles.columns}>
              {columns.map(({ label, value }) => (
                <View key={label} style={styles.column}>
                  <ThemedText style={styles.value}>{value}</ThemedText>
                  <View
                    testID={`bar-${label}`}
                    style={[
                      styles.bar,
                      { height: (value / ceiling) * plotHeight },
                    ]}
                  />
                </View>
              ))}
            </View>
          </View>
          <View style={styles.labels}>
            {columns.map(({ label }) => (
              <ThemedText key={label} style={styles.label}>
                {label}
              </ThemedText>
            ))}
          </View>
        </View>
      </View>
      <ThemedText style={styles.note}>
        Learned: correct answers in Common practice. Total: unique saved and
        learned words.
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginTop: 28 },
  heading: {
    color: colors.text,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '600',
    marginBottom: 28,
  },
  chart: { flexDirection: 'row', gap: 8 },
  axis: {
    height: plotHeight + 16,
    marginTop: -8,
    justifyContent: 'space-between',
    alignItems: 'flex-end',
    minWidth: 28,
  },
  tick: { color: colors.secondary, fontSize: 10, lineHeight: 16 },
  plotAndLabels: { flex: 1 },
  plot: { height: plotHeight },
  grid: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: 0,
    right: 0,
    justifyContent: 'space-between',
  },
  gridLine: { borderTopWidth: 1, borderColor: colors.border },
  columns: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 12,
    paddingHorizontal: 4,
  },
  column: { flex: 1, alignItems: 'center' },
  value: {
    color: colors.text,
    fontSize: 11,
    lineHeight: 18,
    fontWeight: '600',
    marginBottom: 3,
  },
  bar: {
    width: '100%',
    backgroundColor: colors.primary,
    borderTopLeftRadius: 12,
    borderTopRightRadius: 12,
  },
  labels: { flexDirection: 'row', gap: 12, paddingHorizontal: 4, marginTop: 8 },
  label: {
    flex: 1,
    color: colors.text,
    textAlign: 'center',
    fontSize: 10,
    lineHeight: 14,
  },
  note: {
    color: colors.secondary,
    fontSize: 11,
    lineHeight: 16,
    marginTop: 14,
  },
});
