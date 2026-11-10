import { useEffect, useRef, useState, type ComponentRef } from 'react';
import { Platform, Pressable, StyleSheet, TextInput, View } from 'react-native';
import { WordForm } from '@/components/word-form';
import { AppScreen } from '@/components/app-screen';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';
import { authenticatedFetch } from '@/services/auth';
import { connectionMessage } from '@/services/connectivity';

const parts = ['Noun', 'Verb', 'Adjective', 'Adverb', 'Other'] as const;
const forms = ['V1', 'V2', 'V3'] as const;
const formLabels = {
  V1: 'V1 · Base',
  V2: 'V2 · Past',
  V3: 'V3 · Past participle',
};
type Entry = {
  saved?: boolean;
  word: string;
  part_of_speech: string;
  verb_forms: (typeof forms)[number][];
  english_explanation: string;
  example_sentence: string | null;
};

function CheckFilter({
  label,
  checked,
  disabled = false,
  plain = false,
  onPress,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  plain?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityLabel={label}
      accessibilityState={{ checked, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.filter,
        !plain && styles.chip,
        !plain && checked && styles.selectedChip,
        disabled && styles.disabled,
        pressed && styles.pressed,
      ]}
    >
      <View style={[styles.checkbox, checked && styles.checked]}>
        {checked && <ThemedText style={styles.checkmark}>✓</ThemedText>}
      </View>
      <ThemedText
        style={[styles.filterText, checked && !plain && styles.selectedText]}
      >
        {label}
      </ThemedText>
    </Pressable>
  );
}

export default function AddWordScreen() {
  const [word, setWord] = useState('');
  const [topicTags, setTopicTags] = useState('');
  const [includeFamily, setIncludeFamily] = useState(true);
  const [selectedParts, setSelectedParts] = useState<string[]>([
    'Noun',
    'Verb',
    'Adjective',
    'Adverb',
  ]);
  const [selectedForms, setSelectedForms] = useState<string[]>([...forms]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [retry, setRetry] = useState<'search' | Entry | null>(null);
  const [toast, setToast] = useState<{ text: string } | null>(null);
  const [focused, setFocused] = useState(false);
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<Entry[] | null>(null);
  const [saved, setSaved] = useState<string[]>([]);
  const [saving, setSaving] = useState<string[]>([]);
  const input = useRef<ComponentRef<typeof TextInput>>(null);
  const pending = useRef(false);
  const pendingSaves = useRef(new Set<string>());
  const generation = useRef(0);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  function changed() {
    generation.current += 1;
    setResults(null);
    setMessage('');
    setRetry(null);
  }

  async function search() {
    if (pending.current) return;
    setMessage('');
    setRetry(null);
    const query = word.normalize('NFKC').trim();
    setWord(query);
    if (!query || Array.from(query).length > 200) {
      setError(
        query ? 'Use 200 characters or fewer.' : 'Enter a word to search.',
      );
      input.current?.focus();
      return;
    }
    setError('');
    if (
      !selectedParts.length ||
      (selectedParts.length === 1 &&
        selectedParts[0] === 'Verb' &&
        !selectedForms.length)
    ) {
      setMessage('Select a word type and, for verbs, at least one verb form.');
      return;
    }
    const params = new URLSearchParams({
      q: query,
      include_family: String(includeFamily),
    });
    selectedParts.forEach((part) => params.append('parts', part.toLowerCase()));
    // Excluding Verb avoids the API's default forms when none are selected.
    if (!selectedForms.length) {
      params.delete('parts');
      selectedParts
        .filter((part) => part !== 'Verb')
        .forEach((part) => params.append('parts', part.toLowerCase()));
    } else selectedForms.forEach((form) => params.append('forms', form));
    pending.current = true;
    setSearching(true);
    const requestGeneration = generation.current;
    try {
      const response = await authenticatedFetch(`/words/search?${params}`);
      if (!response.ok) throw new Error('Search failed');
      const entries: Entry[] = await response.json();
      if (requestGeneration === generation.current) {
        setResults(entries);
        setSaved((current) => [
          ...new Set([
            ...current,
            ...entries
              .filter((entry) => entry.saved)
              .map((entry) => entry.word),
          ]),
        ]);
      }
    } catch (failure) {
      if (requestGeneration === generation.current) {
        setMessage(
          connectionMessage(
            failure,
            'Could not search the dictionary. Please try again.',
          ),
        );
        setRetry('search');
      }
    } finally {
      pending.current = false;
      setSearching(false);
    }
  }

  async function save(entry: Entry) {
    if (saved.includes(entry.word)) {
      setToast({ text: `“${entry.word}” is already in your word bank.` });
      return;
    }
    const topics = [
      ...new Set(
        topicTags
          .split(',')
          .map((tag) => tag.normalize('NFKC').trim())
          .filter(Boolean),
      ),
    ];
    if (
      topics.length > 10 ||
      topics.some((tag) => Array.from(tag).length > 100)
    ) {
      setMessage('Use up to 10 topic tags, each 100 characters or fewer.');
      return;
    }
    if (pendingSaves.current.has(entry.word)) return;
    pendingSaves.current.add(entry.word);
    setSaving([...pendingSaves.current]);
    setMessage('');
    setRetry(null);
    const requestGeneration = generation.current;
    try {
      const response = await authenticatedFetch('/words', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...(topics.length ? { topics } : {}),
          word: entry.word,
          english_explanation: entry.english_explanation,
          example_sentence: entry.example_sentence,
        }),
      });
      if (!response.ok && response.status !== 409)
        throw new Error('Save failed');
      setSaved((current) => [...current, entry.word]);
      if (requestGeneration === generation.current)
        setToast({
          text:
            response.status === 409
              ? `“${entry.word}” is already in your word bank.`
              : `“${entry.word}” added to your word bank.`,
        });
    } catch (failure) {
      if (requestGeneration === generation.current) {
        setMessage(
          connectionMessage(
            failure,
            `Could not save “${entry.word}”. Please retry.`,
          ),
        );
        setRetry(entry);
      }
    } finally {
      pendingSaves.current.delete(entry.word);
      setSaving([...pendingSaves.current]);
    }
  }

  return (
    <AppScreen selected="Add" toast={toast?.text}>
      <View style={styles.content}>
        <ThemedText accessibilityRole="header" style={styles.title}>
          Add a word
        </ThemedText>
        <ThemedText style={styles.subtitle}>
          Find word forms and save the ones you need.
        </ThemedText>
        <ThemedText style={styles.label}>Topic tags (optional)</ThemedText>
        <TextInput
          accessibilityLabel="Topic tags (comma separated)"
          value={topicTags}
          onChangeText={setTopicTags}
          placeholder="Work, travel"
          placeholderTextColor={colors.placeholder}
          style={styles.input}
        />
        <ThemedText style={styles.subtitle}>
          Separate tags with commas. Tags apply to words you save below.
        </ThemedText>
        <WordForm onSubmit={search}>
          <View style={styles.card}>
            <ThemedText nativeID="word-search-label" style={styles.label}>
              Word to search *
            </ThemedText>
            <View style={styles.inputWrapper}>
              <TextInput
                ref={input}
                accessibilityLabel="Word to search (required)"
                accessibilityLabelledBy="word-search-label"
                aria-required
                aria-invalid={!!error}
                value={word}
                placeholder="Enter a word, e.g. create"
                placeholderTextColor={colors.placeholder}
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="search"
                onSubmitEditing={() => {
                  if (Platform.OS !== 'web') void search();
                }}
                onFocus={() => setFocused(true)}
                onBlur={() => setFocused(false)}
                onChangeText={(value) => {
                  setWord(value);
                  setError('');
                  changed();
                }}
                style={[
                  styles.input,
                  focused && styles.focused,
                  !!error && styles.invalid,
                ]}
              />
              <View pointerEvents="none" style={styles.searchIcon}>
                <View style={styles.searchCircle} />
                <View style={styles.searchHandle} />
              </View>
            </View>
            {!!error && (
              <ThemedText accessibilityRole="alert" style={styles.error}>
                {error}
              </ThemedText>
            )}
            <CheckFilter
              plain
              label="Include word family"
              checked={includeFamily}
              onPress={() => {
                setIncludeFamily(!includeFamily);
                changed();
              }}
            />
            <View style={styles.filters}>
              {parts.map((part) => (
                <CheckFilter
                  key={part}
                  label={part}
                  checked={selectedParts.includes(part)}
                  onPress={() => {
                    setSelectedParts((current) =>
                      current.includes(part)
                        ? current.filter((item) => item !== part)
                        : [...current, part],
                    );
                    changed();
                  }}
                />
              ))}
            </View>
            <ThemedText style={styles.sectionLabel}>VERB FORMS</ThemedText>
            <View style={styles.filters}>
              {forms.map((form) => (
                <CheckFilter
                  key={form}
                  label={formLabels[form]}
                  checked={selectedForms.includes(form)}
                  disabled={!selectedParts.includes('Verb')}
                  onPress={() => {
                    setSelectedForms((current) =>
                      current.includes(form)
                        ? current.filter((item) => item !== form)
                        : [...current, form],
                    );
                    changed();
                  }}
                />
              ))}
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: searching, busy: searching }}
              disabled={searching}
              onPress={search}
              style={({ pressed }) => [
                styles.button,
                styles.searchButton,
                (pressed || searching) && styles.pressed,
              ]}
            >
              <ThemedText style={styles.buttonText}>
                {searching ? 'Searching…' : 'Search'}
              </ThemedText>
            </Pressable>
          </View>
        </WordForm>
        {!!message && (
          <ThemedText accessibilityLiveRegion="polite" style={styles.message}>
            {message}
          </ThemedText>
        )}
        {!!retry && (
          <Pressable
            accessibilityRole="button"
            disabled={searching || saving.length > 0}
            accessibilityState={{ disabled: searching || saving.length > 0 }}
            onPress={() => (retry === 'search' ? search() : save(retry))}
            style={styles.button}
          >
            <ThemedText style={styles.buttonText}>Try again</ThemedText>
          </Pressable>
        )}
        {searching && results !== null && (
          <ThemedText accessibilityLiveRegion="polite" style={styles.message}>
            Fetching matching forms and definitions…
          </ThemedText>
        )}
        {results === null ? (
          <View style={styles.emptyCard}>
            <ThemedText
              accessibilityLiveRegion="polite"
              style={styles.emptyTitle}
            >
              {searching ? 'Searching dictionary…' : 'No results yet'}
            </ThemedText>
            <ThemedText style={styles.emptyText}>
              {searching
                ? 'Fetching matching forms and definitions…'
                : 'Enter a word and select Search\nto find related word forms.'}
            </ThemedText>
          </View>
        ) : (
          <View style={styles.results}>
            <View style={styles.resultsHeader}>
              <ThemedText accessibilityRole="header" style={styles.emptyTitle}>
                Search results
              </ThemedText>
              <ThemedText
                accessibilityLiveRegion="polite"
                style={styles.subtitle}
              >
                {results.length} found
              </ThemedText>
            </View>
            {!results.length && (
              <ThemedText style={styles.emptyText}>
                No matching words found. Try another word or change your
                filters.
              </ThemedText>
            )}
            {results.map((entry) => (
              <View
                key={`${entry.word}:${entry.part_of_speech}`}
                style={styles.resultCard}
              >
                <View style={styles.resultBody}>
                  <ThemedText style={styles.emptyTitle}>
                    {entry.word}
                  </ThemedText>
                  <ThemedText style={styles.resultType}>
                    {entry.part_of_speech.charAt(0).toUpperCase() +
                      entry.part_of_speech.slice(1)}
                    {entry.verb_forms.length
                      ? ` · ${entry.verb_forms.join('/')}`
                      : ''}
                  </ThemedText>
                  <ThemedText style={styles.definition}>
                    {entry.english_explanation}
                  </ThemedText>
                </View>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`${saved.includes(entry.word) ? 'Saved' : 'Save'} ${entry.word}`}
                  accessibilityState={{
                    disabled:
                      saved.includes(entry.word) || saving.includes(entry.word),
                    busy: saving.includes(entry.word),
                  }}
                  disabled={
                    saved.includes(entry.word) || saving.includes(entry.word)
                  }
                  onPress={() => save(entry)}
                  style={({ pressed }) => [
                    styles.button,
                    (pressed ||
                      saved.includes(entry.word) ||
                      saving.includes(entry.word)) &&
                      styles.pressed,
                  ]}
                >
                  <ThemedText style={styles.buttonText}>
                    {saved.includes(entry.word)
                      ? 'Saved'
                      : saving.includes(entry.word)
                        ? 'Saving…'
                        : 'Save'}
                  </ThemedText>
                </Pressable>
              </View>
            ))}
            <ThemedText style={styles.emptyText}>
              Definitions: Princeton WordNet. Word-family coverage varies;
              particles, interjections and other word types may not be
              available.
            </ThemedText>
          </View>
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
    marginTop: 18,
    padding: 17,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 16,
    backgroundColor: colors.surface,
  },
  label: {
    fontFamily,
    color: colors.text,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '700',
    marginBottom: 8,
  },
  inputWrapper: { position: 'relative' },
  input: {
    fontFamily,
    color: colors.text,
    fontSize: 14,
    lineHeight: 20,
    minHeight: 44,
    paddingLeft: 13,
    paddingRight: 42,
    paddingVertical: 11,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  focused: { borderColor: colors.primary },
  invalid: {
    borderColor: colors.error,
    backgroundColor: colors.errorBackground,
  },
  searchIcon: {
    position: 'absolute',
    right: 16,
    top: 14,
    width: 18,
    height: 18,
  },
  searchCircle: {
    width: 13,
    height: 13,
    borderWidth: 1.7,
    borderColor: colors.placeholder,
    borderRadius: 7,
  },
  searchHandle: {
    position: 'absolute',
    width: 7,
    height: 2,
    backgroundColor: colors.placeholder,
    transform: [{ rotate: '45deg' }],
    left: 10,
    top: 13,
  },
  filters: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  filter: { flexDirection: 'row', alignItems: 'center', gap: 7, minHeight: 44 },
  chip: {
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderWidth: 1,
    borderRadius: 8,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  selectedChip: {
    borderColor: colors.primary,
    backgroundColor: colors.primarySoft,
  },
  checkbox: {
    width: 15,
    height: 15,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 3,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
  },
  checked: { borderColor: colors.primary, backgroundColor: colors.primary },
  checkmark: {
    color: colors.surface,
    fontSize: 12,
    lineHeight: 14,
    fontWeight: '700',
  },
  filterText: {
    fontFamily,
    fontSize: 12,
    lineHeight: 18,
    color: colors.text,
    fontWeight: '600',
  },
  selectedText: { color: colors.primary },
  sectionLabel: {
    fontFamily,
    fontSize: 11,
    lineHeight: 16,
    fontWeight: '800',
    letterSpacing: 0.7,
    color: colors.secondary,
    marginTop: 16,
    marginBottom: 7,
  },
  error: {
    fontFamily,
    color: colors.error,
    fontSize: 11,
    lineHeight: 17,
    marginTop: 6,
  },
  message: {
    fontFamily,
    color: colors.text,
    fontSize: 13,
    lineHeight: 19,
    marginTop: 16,
  },
  button: {
    minHeight: 44,
    borderRadius: 10,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 12,
  },
  searchButton: { marginTop: 13 },
  buttonText: {
    fontFamily,
    color: colors.surface,
    fontSize: 13,
    lineHeight: 20,
    fontWeight: '700',
  },
  pressed: { opacity: 0.75 },
  disabled: { opacity: 0.4 },
  emptyCard: {
    marginTop: 20,
    padding: 24,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    gap: 8,
  },
  emptyTitle: {
    fontFamily,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '800',
    color: colors.text,
  },
  emptyText: {
    fontFamily,
    fontSize: 12,
    lineHeight: 19,
    color: colors.secondary,
    textAlign: 'center',
  },
  results: { marginTop: 20, gap: 8 },
  resultsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  resultCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 15,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  resultBody: { flex: 1 },
  resultType: {
    fontFamily,
    fontSize: 11,
    lineHeight: 17,
    color: colors.primary,
    textTransform: 'capitalize',
    fontWeight: '600',
  },
  definition: {
    fontFamily,
    fontSize: 12,
    lineHeight: 18,
    color: colors.secondary,
  },
});
