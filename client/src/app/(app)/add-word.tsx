import { useRef, useState, type ComponentRef } from 'react';
import { Platform, Pressable, StyleSheet, TextInput, View } from 'react-native';
import { NavigationLink } from '@/components/navigation-link';
import { AppScreen } from '@/components/app-screen';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';
import { authenticatedFetch } from '@/services/auth';
import { validateWord, wordPayload } from '@/utils/word-validation';

const fields = [
  { key: 'word', label: 'Word *', placeholder: 'e.g. resilience' },
  {
    key: 'english_explanation',
    label: 'English explanation *',
    placeholder: 'e.g. Able to recover from difficulty.',
  },
  {
    key: 'example_sentence',
    label: 'Example sentence (optional)',
    placeholder: 'e.g. She showed resilience.',
  },
] as const;
type Field = (typeof fields)[number]['key'];
const empty = { word: '', english_explanation: '', example_sentence: '' };

export default function AddWordScreen() {
  const [values, setValues] = useState(empty);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [message, setMessage] = useState('');
  const [duplicate, setDuplicate] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [focused, setFocused] = useState<Field | null>(null);
  const inputs = useRef<
    Partial<Record<Field, ComponentRef<typeof TextInput> | null>>
  >({});
  const pending = useRef(false);

  async function save() {
    if (pending.current || duplicate) return;
    const nextErrors = validateWord(values);
    setErrors(nextErrors);
    setMessage('');
    setSaved(false);
    const firstInvalid = fields.find((field) => nextErrors[field.key]);
    if (firstInvalid) {
      inputs.current[firstInvalid.key]?.focus();
      return;
    }
    pending.current = true;
    setSaving(true);
    try {
      const response = await authenticatedFetch('/words', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(wordPayload(values)),
      });
      if (response.status === 409) {
        setDuplicate(true);
        inputs.current.word?.focus();
        return;
      }
      if (!response.ok) throw new Error('Save failed');
      setValues(empty);
      setSaved(true);
      setMessage('Word saved to your word bank.');
    } catch {
      setMessage('Could not save your word. Please try again.');
    } finally {
      pending.current = false;
      setSaving(false);
    }
  }

  return (
    <AppScreen selected="Add">
      <View style={styles.content}>
        <ThemedText accessibilityRole="header" style={styles.title}>
          Add a word
        </ThemedText>
        <ThemedText style={styles.subtitle}>
          Build your personal word bank.
        </ThemedText>
        <View style={styles.card}>
          {fields.map((field) => (
            <View key={field.key} style={styles.field}>
              <ThemedText nativeID={`${field.key}-label`} style={styles.label}>
                {field.label}
              </ThemedText>
              <TextInput
                ref={(input) => {
                  inputs.current[field.key] = input;
                }}
                accessibilityLabel={field.label.replace(' *', ' (required)')}
                accessibilityLabelledBy={`${field.key}-label`}
                aria-invalid={
                  !!errors[field.key] || (field.key === 'word' && duplicate)
                }
                value={values[field.key]}
                editable={!saving}
                placeholder={field.placeholder}
                placeholderTextColor={colors.placeholder}
                multiline={field.key !== 'word'}
                autoCapitalize={field.key === 'word' ? 'none' : 'sentences'}
                autoCorrect={field.key !== 'word'}
                returnKeyType={field.key === 'word' ? 'next' : 'default'}
                onSubmitEditing={
                  field.key === 'word'
                    ? () => inputs.current.english_explanation?.focus()
                    : undefined
                }
                onFocus={() => setFocused(field.key)}
                onBlur={() => {
                  setFocused(null);
                  setErrors((current) => ({
                    ...current,
                    [field.key]: validateWord(values)[field.key],
                  }));
                }}
                onChangeText={(text) => {
                  if (field.key === 'word') setDuplicate(false);
                  setValues((current) => ({ ...current, [field.key]: text }));
                  setErrors((current) => ({
                    ...current,
                    [field.key]: current[field.key]
                      ? validateWord({ ...values, [field.key]: text })[
                          field.key
                        ]
                      : undefined,
                  }));
                  setMessage('');
                }}
                style={[
                  styles.input,
                  field.key === 'english_explanation' && styles.explanation,
                  field.key === 'example_sentence' && styles.example,
                  focused === field.key && styles.focused,
                  (!!errors[field.key] ||
                    (field.key === 'word' && duplicate)) &&
                    styles.invalid,
                ]}
              />
              {field.key === 'word' && duplicate && (
                <View>
                  <ThemedText accessibilityRole="alert" style={styles.error}>
                    You already saved this word. Enter a different word or
                    cancel.
                  </ThemedText>
                  <NavigationLink
                    href="/"
                    replace
                    label="Cancel adding word"
                    style={styles.cancel}
                  >
                    <ThemedText style={styles.cancelText}>Cancel</ThemedText>
                  </NavigationLink>
                </View>
              )}
              {!!errors[field.key] && (
                <ThemedText accessibilityRole="alert" style={styles.error}>
                  {errors[field.key]}
                </ThemedText>
              )}
            </View>
          ))}
          {!!message && (
            <ThemedText
              accessibilityLiveRegion="polite"
              style={[styles.message, saved ? styles.success : styles.error]}
            >
              {message}
            </ThemedText>
          )}
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: saving || duplicate, busy: saving }}
            disabled={saving || duplicate}
            onPress={save}
            style={({ pressed }) => [
              styles.button,
              (pressed || saving || duplicate) && styles.pressed,
            ]}
          >
            <ThemedText style={styles.buttonText}>
              {saving ? 'Saving…' : 'Save word'}
            </ThemedText>
          </Pressable>
        </View>
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
  title: {
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
    marginTop: 9,
  },
  card: {
    marginTop: 30,
    padding: 17,
    minHeight: 470,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 16,
    backgroundColor: colors.surface,
  },
  field: { marginBottom: 30 },
  label: {
    fontFamily,
    color: colors.text,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '600',
    marginBottom: 12,
  },
  input: {
    fontFamily,
    color: colors.text,
    fontSize: 14,
    lineHeight: 20,
    minHeight: 49,
    paddingHorizontal: 13,
    paddingVertical: 13,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  explanation: { minHeight: 83, textAlignVertical: 'top' },
  example: { minHeight: 57, textAlignVertical: 'top' },
  focused: { borderColor: colors.primary },
  invalid: {
    borderColor: colors.error,
    backgroundColor: colors.errorBackground,
  },
  error: {
    fontFamily,
    color: colors.error,
    fontSize: 11,
    lineHeight: 17,
    marginTop: 6,
  },
  message: { fontFamily, fontSize: 13, lineHeight: 19, marginBottom: 12 },
  success: { color: colors.success },
  button: {
    marginTop: 'auto',
    minHeight: 48,
    borderRadius: 13,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 12,
  },
  cancel: {
    minHeight: 44,
    alignSelf: 'flex-start',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  cancelText: {
    fontFamily,
    color: colors.primary,
    fontSize: 13,
    lineHeight: 20,
    fontWeight: '600',
  },
  pressed: { opacity: 0.75 },
  buttonText: {
    fontFamily,
    color: colors.surface,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '600',
  },
});
