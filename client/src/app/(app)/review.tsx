import { type ComponentRef, useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  ActivityIndicator,
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { AppScreen } from '@/components/app-screen';
import { NavigationLink } from '@/components/navigation-link';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';
import { authenticatedFetch } from '@/services/auth';

type Prompt = {
  word_id: string;
  english_explanation: string;
  example_sentence: string | null;
};
type Result = { result: 'correct' | 'incorrect'; correct_word: string };

export default function ReviewScreen() {
  const [item, setItem] = useState<Prompt | null>(null);
  const [answer, setAnswer] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reviewed, setReviewed] = useState(0);
  const [correctCount, setCorrectCount] = useState(0);
  const answerInput = useRef<ComponentRef<typeof TextInput>>(null);
  const busy = useRef(false);
  const started = useRef(0);
  const mounted = useRef(true);

  function load() {
    if (busy.current) return;
    busy.current = true;
    void authenticatedFetch('/reviews/next')
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const items: Prompt[] = await response.json();
        if (mounted.current) {
          setItem(items[0] ?? null);
          started.current = Date.now();
        }
      })
      .catch(() => {
        if (mounted.current)
          setError('Could not load your review. Please try again.');
      })
      .finally(() => {
        busy.current = false;
        if (mounted.current) setLoading(false);
      });
  }

  function next() {
    if (busy.current) return;
    setLoading(true);
    setError('');
    setItem(null);
    setResult(null);
    setAnswer('');
    void load();
  }

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    // Wait until the loaded prompt is editable, including after a failed submit.
    if (item && !loading && !result) {
      answerInput.current?.focus();
    }
  }, [item, loading, result]);

  const finished = !loading && !error && !item;
  const announcement = result
    ? result.result === 'correct'
      ? 'Correct! Well done.'
      : `Incorrect. You typed: ${answer || 'No answer'}. Correct word: ${result.correct_word}.`
    : finished
      ? `Review finished. ${correctCount} of ${reviewed} answers correct.`
      : '';

  useEffect(() => {
    // Android and web use the persistent live region below; VoiceOver needs this.
    if (Platform.OS === 'ios' && announcement) {
      AccessibilityInfo.announceForAccessibility(announcement);
    }
  }, [announcement]);

  async function submit() {
    if (!item || result || busy.current) return;
    busy.current = true;
    setLoading(true);
    setError('');
    try {
      const response = await authenticatedFetch(
        `/reviews/${item.word_id}/answer`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            typed_answer: answer,
            time_taken_ms: Math.min(
              2147483647,
              Math.max(0, Date.now() - started.current),
            ),
          }),
        },
      );
      if (response.status === 409) {
        setItem(null);
        throw new Error();
      }
      if (!response.ok) throw new Error();
      const feedback: Result = await response.json();
      if (mounted.current) {
        setResult(feedback);
        setReviewed((count) => count + 1);
        if (feedback.result === 'correct')
          setCorrectCount((count) => count + 1);
      }
    } catch {
      if (mounted.current)
        setError(
          'Could not submit your answer. Try again or reload the review.',
        );
    } finally {
      busy.current = false;
      if (mounted.current) setLoading(false);
    }
  }

  return (
    <AppScreen selected="Review">
      <View style={styles.content}>
        <ThemedText style={styles.title} accessibilityRole="header">
          {finished ? 'Review finished' : 'Time to recall'}
        </ThemedText>
        <ThemedText style={styles.subtitle}>
          Read the explanation. Type the word.
        </ThemedText>
        <ThemedText
          accessibilityLiveRegion="polite"
          accessibilityRole={Platform.OS === 'web' ? 'status' : undefined}
          style={styles.announcement}
        >
          {announcement}
        </ThemedText>
        {loading && (
          <ActivityIndicator
            color={colors.primary}
            accessibilityLabel="Loading review"
          />
        )}
        {item && (
          <>
            <ThemedText style={styles.question}>
              Which word matches this meaning?
            </ThemedText>
            <View style={styles.card}>
              <ThemedText style={styles.label}>ENGLISH EXPLANATION</ThemedText>
              <ThemedText style={styles.explanation}>
                {item.english_explanation}
              </ThemedText>
              {!!item.example_sentence && (
                <>
                  <ThemedText style={styles.label}>EXAMPLE SENTENCE</ThemedText>
                  <ThemedText style={styles.example}>
                    {item.example_sentence}
                  </ThemedText>
                </>
              )}
            </View>
            {result ? (
              <>
                <View
                  style={[
                    styles.card,
                    {
                      backgroundColor:
                        result.result === 'correct'
                          ? colors.successBackground
                          : colors.errorBackground,
                    },
                  ]}
                >
                  <ThemedText style={styles.question}>
                    {result.result === 'correct'
                      ? 'Correct! Well done.'
                      : 'Incorrect — compare answers'}
                  </ThemedText>
                  {result.result === 'incorrect' && (
                    <View style={styles.comparison}>
                      <View style={styles.comparisonColumn}>
                        <ThemedText style={styles.label}>YOU TYPED</ThemedText>
                        <ThemedText style={styles.explanation}>
                          {answer || 'No answer'}
                        </ThemedText>
                      </View>
                      <View style={styles.comparisonColumn}>
                        <ThemedText style={styles.label}>
                          CORRECT WORD
                        </ThemedText>
                        <ThemedText style={styles.explanation}>
                          {result.correct_word}
                        </ThemedText>
                      </View>
                    </View>
                  )}
                </View>
                <Pressable
                  accessibilityRole="button"
                  style={styles.button}
                  onPress={next}
                  disabled={loading}
                >
                  <ThemedText style={styles.buttonText}>Next word</ThemedText>
                </Pressable>
              </>
            ) : (
              <>
                <ThemedText style={styles.question}>Your answer</ThemedText>
                <TextInput
                  ref={answerInput}
                  multiline={false}
                  accessibilityLabel="Your answer"
                  style={styles.input}
                  value={answer}
                  onChangeText={setAnswer}
                  placeholder="Type the word here"
                  placeholderTextColor={colors.placeholder}
                  autoCapitalize="none"
                  autoCorrect={false}
                  spellCheck={false}
                  maxLength={200}
                  editable={!loading}
                  returnKeyType="done"
                  onSubmitEditing={() => void submit()}
                />
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ disabled: loading }}
                  style={[styles.button, loading && styles.disabled]}
                  disabled={loading}
                  onPress={() => void submit()}
                >
                  <ThemedText style={styles.buttonText}>
                    Submit answer
                  </ThemedText>
                </Pressable>
                <ThemedText style={styles.subtitle}>
                  The word is hidden until you submit.
                </ThemedText>
              </>
            )}
          </>
        )}
        {!!error && (
          <View accessibilityLiveRegion="polite">
            <ThemedText style={styles.error}>{error}</ThemedText>
            {!item && (
              <Pressable
                accessibilityRole="button"
                style={styles.button}
                onPress={next}
              >
                <ThemedText style={styles.buttonText}>Try again</ThemedText>
              </Pressable>
            )}
          </View>
        )}
        {!loading && !error && !item && (
          <View style={styles.card}>
            <ThemedText style={styles.explanation}>
              {correctCount} of {reviewed} answers correct.
            </ThemedText>
            <NavigationLink href="/" label="Back to Home" style={styles.button}>
              <ThemedText style={styles.buttonText}>Back to Home</ThemedText>
            </NavigationLink>
          </View>
        )}
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  announcement: {
    position: 'absolute',
    width: 1,
    height: 1,
    overflow: 'hidden',
  },
  comparison: { flexDirection: 'row', flexWrap: 'wrap', gap: 16 },
  comparisonColumn: { flex: 1, minWidth: 120, gap: 8 },
  content: {
    width: '100%',
    maxWidth: 600,
    alignSelf: 'center',
    paddingHorizontal: 22,
    paddingTop: 25,
    paddingBottom: 36,
    gap: 20,
  },
  title: {
    color: colors.text,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '800',
  },
  subtitle: { color: colors.secondary, fontSize: 13, lineHeight: 20 },
  question: {
    color: colors.text,
    fontSize: 17,
    lineHeight: 24,
    fontWeight: '700',
  },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 16,
    padding: 19,
    gap: 16,
  },
  label: {
    color: colors.placeholder,
    fontSize: 11,
    lineHeight: 17,
    fontWeight: '700',
    letterSpacing: 0.8,
  },
  explanation: {
    color: colors.text,
    fontSize: 18,
    lineHeight: 27,
    fontWeight: '600',
  },
  example: { color: colors.secondary, fontSize: 16, lineHeight: 25 },
  input: {
    backgroundColor: colors.surface,
    color: colors.text,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 10,
    minHeight: 54,
    padding: 14,
    fontSize: 16,
  },
  button: {
    backgroundColor: colors.primary,
    borderRadius: 13,
    minHeight: 53,
    padding: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: { color: colors.surface, fontSize: 15, fontWeight: '600' },
  disabled: { opacity: 0.5 },
  error: { color: colors.error, fontSize: 14 },
});
