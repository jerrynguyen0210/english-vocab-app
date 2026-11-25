import { useRef, useState, type ComponentRef } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';
import { useTeacherSelection } from '@/context/teacher-selection';

export function TeacherSelection() {
  const { teachers, teacherId, selectTeacher, loading, saving, error, reload } =
    useTeacherSelection();
  const [expanded, setExpanded] = useState(false);
  const trigger = useRef<ComponentRef<typeof Pressable>>(null);
  const teacher = teachers.find(({ id }) => id === teacherId);
  const disabled = loading || saving || teachers.length === 0;
  const placeholder = loading
    ? 'Loading teachers…'
    : teachers.length === 0
      ? error
        ? 'Teachers unavailable'
        : 'No teachers available yet'
      : 'Select a teacher';

  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <View style={styles.avatar} accessible={false}>
          <ThemedText style={styles.illustration}>🧑‍🏫</ThemedText>
        </View>
        <View style={styles.details}>
          <ThemedText style={styles.title} accessibilityRole="header">
            Teacher
          </ThemedText>
          <ThemedText style={styles.description}>
            Choose your teacher.
          </ThemedText>
        </View>
      </View>
      <View style={styles.field}>
        <ThemedText style={styles.label}>Name</ThemedText>
        <Pressable
          ref={trigger}
          accessibilityRole="button"
          accessibilityLabel={`Teacher name: ${teacher?.name ?? placeholder}`}
          accessibilityHint="Shows available teachers"
          disabled={disabled}
          accessibilityState={{
            expanded: expanded && !loading && teachers.length > 0,
            disabled,
            busy: loading || saving,
          }}
          onPress={() => setExpanded((value) => !value)}
          style={({ pressed }) => [
            styles.select,
            expanded && styles.selectExpanded,
            pressed && styles.pressed,
          ]}
        >
          <ThemedText style={[styles.name, !teacher && styles.placeholder]}>
            {teacher?.name ?? placeholder}
          </ThemedText>
          <ThemedText style={styles.chevron} accessible={false}>
            {expanded ? '▴' : '▾'}
          </ThemedText>
        </Pressable>
        {expanded && !loading && teachers.length > 0 ? (
          <View style={styles.options}>
            {teachers.map(({ id, name }) => (
              <Pressable
                key={id}
                accessibilityRole="button"
                accessibilityLabel={name}
                disabled={saving}
                accessibilityState={{
                  selected: id === teacherId,
                  disabled: saving,
                }}
                onPress={() => {
                  void selectTeacher(id).then((saved) => {
                    if (saved) {
                      setExpanded(false);
                      trigger.current?.focus();
                    }
                  });
                }}
                style={({ pressed }) => [
                  styles.option,
                  id === teacherId && styles.selectedOption,
                  pressed && styles.pressed,
                ]}
              >
                <ThemedText style={styles.name}>{name}</ThemedText>
                {id === teacherId ? (
                  <ThemedText style={styles.check} accessible={false}>
                    ✓
                  </ThemedText>
                ) : null}
              </Pressable>
            ))}
          </View>
        ) : null}
        {saving ? (
          <ThemedText
            style={styles.description}
            accessibilityLiveRegion="polite"
          >
            Saving teacher…
          </ThemedText>
        ) : null}
        {error ? (
          <View style={styles.field}>
            <ThemedText style={styles.error} accessibilityRole="alert">
              {error}
            </ThemedText>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Retry loading teachers"
              disabled={loading || saving}
              onPress={reload}
              style={styles.select}
            >
              <ThemedText style={styles.check}>Retry</ThemedText>
            </Pressable>
          </View>
        ) : null}
      </View>
    </View>
  );
}

const fontFamily = Platform.select({
  web: 'Arial, sans-serif',
  default: undefined,
});
const styles = StyleSheet.create({
  card: {
    marginTop: 24,
    padding: 22,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    gap: 20,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 18 },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    borderWidth: 3,
    borderColor: '#9EDFD9',
    backgroundColor: '#F0FAF8',
    alignItems: 'center',
    justifyContent: 'center',
  },
  illustration: { fontSize: 44, lineHeight: 58 },
  details: { flex: 1, minWidth: 0, gap: 5 },
  title: {
    fontFamily,
    fontSize: 25,
    lineHeight: 32,
    fontWeight: '800',
    color: colors.text,
  },
  description: {
    fontFamily,
    fontSize: 13,
    lineHeight: 20,
    color: colors.secondary,
  },
  field: { gap: 7 },
  label: {
    fontFamily,
    fontSize: 12,
    lineHeight: 18,
    color: colors.secondary,
  },
  select: {
    minHeight: 50,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  selectExpanded: { borderColor: colors.primary },
  name: {
    flexShrink: 1,
    fontFamily,
    fontSize: 14,
    lineHeight: 22,
    color: colors.text,
    fontWeight: '400',
  },
  placeholder: { color: colors.placeholder },
  chevron: { color: colors.secondary, fontSize: 18 },
  options: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    overflow: 'hidden',
  },
  option: {
    minHeight: 48,
    paddingHorizontal: 14,
    paddingVertical: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  selectedOption: { backgroundColor: colors.primarySoft },
  check: { color: colors.primary, fontSize: 16 },
  pressed: { backgroundColor: colors.primarySoft },
  error: { fontFamily, color: colors.error, fontSize: 13, lineHeight: 20 },
});
