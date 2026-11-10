import { useLocalSearchParams } from 'expo-router';
import {
  selectPreviewWords,
  reviewPreviewWords,
} from '@/constants/review-preview';
import { connectionMessage } from '@/services/connectivity';
import { Image } from 'expo-image';
import {
  type ComponentRef,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
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
import { AuthError, authenticatedFetch } from '@/services/auth';
import { useSession } from '@/context/session';

type Prompt = {
  word_id: string;
  attempt_id: string;
  english_explanation: string;
  example_sentence: string | null;
  word?: string;
};
type Result = { result: 'correct' | 'incorrect'; correct_word: string };

export default function ReviewScreen() {
  const params = useLocalSearchParams<{
    preview?: string;
    source?: string;
    period?: string;
    topic?: string;
    includeOverdue?: string;
  }>();
  const preview = params.preview === 'true';
  const [mode, setMode] = useState<'choice' | 'typing'>(
    preview ? 'choice' : 'typing',
  );
  const { signedIn } = useSession();
  const queue = useRef<Prompt[]>([]);
  const [total, setTotal] = useState(0);
  const [position, setPosition] = useState(1);
  const [pendingBody, setPendingBody] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
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

  const load = useCallback(async () => {
    if (busy.current) return;
    if (preview) {
      await Promise.resolve();
      if (!mounted.current) return;
      const items = selectPreviewWords(
        params.source === 'recall' || params.source === 'topic'
          ? params.source
          : 'time',
        params.period === 'Yesterday' || params.period === 'Monthly'
          ? params.period
          : 'Weekly',
        params.topic ?? '',
        params.includeOverdue !== 'false',
      );
      queue.current = items.slice(1);
      setTotal(items.length);
      setPosition(1);
      setItem(items[0] ?? null);
      setLoading(false);
      return;
    }
    busy.current = true;
    void authenticatedFetch('/reviews/session')
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const items: Prompt[] = await response.json();
        if (mounted.current) {
          queue.current = items.slice(1);
          setTotal(items.length);
          setPosition(1);
          setItem(items[0] ?? null);
          started.current = performance.now();
        }
      })
      .catch((error) => {
        if (mounted.current)
          setError(
            connectionMessage(
              error,
              'Could not load your review. Please try again.',
            ),
          );
      })
      .finally(() => {
        busy.current = false;
        if (mounted.current) setLoading(false);
      });
  }, [
    preview,
    params.source,
    params.period,
    params.topic,
    params.includeOverdue,
  ]);

  function next() {
    if (busy.current) return;
    setLoading(true);
    setError('');
    setItem(null);
    setResult(null);
    setAnswer('');
    setPendingBody(null);
    setConflict(false);
    if (!item && total === 0) {
      void load();
      return;
    }
    setItem(queue.current.shift() ?? null);
    setPosition((value) => value + 1);
    started.current = performance.now();
    setLoading(false);
  }

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
    };
  }, [load]);

  useEffect(() => {
    // Wait until the loaded prompt is editable, including after a failed submit.
    if (
      signedIn &&
      mode === 'typing' &&
      item &&
      !loading &&
      !result &&
      !pendingBody
    ) {
      answerInput.current?.focus();
    }
  }, [signedIn, mode, item, loading, result, pendingBody]);

  const finished = !loading && !error && !item;
  const announcement = result
    ? result.result === 'correct'
      ? 'Correct! Well done.'
      : `Incorrect. You typed: ${answer || 'No answer'}. Correct word: ${result.correct_word}.`
    : finished
      ? total
        ? `Review finished. ${correctCount} of ${reviewed} answers correct.`
        : 'No reviews available right now.'
      : '';

  useEffect(() => {
    // Android and web use the persistent live region below; VoiceOver needs this.
    if (Platform.OS === 'ios' && announcement) {
      AccessibilityInfo.announceForAccessibility(announcement);
    }
  }, [announcement]);

  async function submit() {
    if (!signedIn || !item || result || conflict || busy.current) return;
    if (preview) {
      const correct = answer.trim().toLowerCase() === item.word?.toLowerCase();
      setResult({
        result: correct ? 'correct' : 'incorrect',
        correct_word: item.word ?? '',
      });
      setReviewed((count) => count + 1);
      if (correct) setCorrectCount((count) => count + 1);
      return;
    }
    busy.current = true;
    setLoading(true);
    setError('');
    const body =
      pendingBody ??
      JSON.stringify({
        attempt_id: item.attempt_id,
        typed_answer: answer,
        time_taken_ms: Math.min(
          2147483647,
          Math.max(0, Math.round(performance.now() - started.current)),
        ),
      });
    setPendingBody(body);
    try {
      const response = await authenticatedFetch(
        `/reviews/${item.word_id}/answer`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: body,
        },
      );
      if (response.status === 409 || response.status === 404) {
        const problem = await response.json();
        if (!mounted.current) return;
        if (problem.detail === 'Daily review cap reached') {
          queue.current = [];
          setItem(null);
        } else {
          setConflict(true);
          setError(
            'This word is no longer available to review. Continue to the next item.',
          );
        }
        return;
      }
      if (!response.ok) throw new Error();
      const feedback: Result = await response.json();
      if (mounted.current) {
        setResult(feedback);
        setReviewed((count) => count + 1);
        if (feedback.result === 'correct')
          setCorrectCount((count) => count + 1);
      }
    } catch (error) {
      if (mounted.current)
        setError(
          error instanceof AuthError && error.status === 401
            ? 'Sign in to continue. Your answer is still here.'
            : connectionMessage(
                error,
                'Could not confirm your answer was submitted. Please retry.',
              ) + ' Your answer is still here. Retry the same submission.',
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
          {finished
            ? total
              ? 'Review finished'
              : 'All caught up'
            : 'Time to recall'}
        </ThemedText>
        <ThemedText style={styles.subtitle}>
          {finished
            ? total
              ? 'You have completed this review.'
              : 'No reviews available right now.'
            : preview
              ? 'Fill the blank with the missing word.'
              : 'Read the explanation. Type the word.'}
        </ThemedText>
        <ThemedText
          accessibilityLiveRegion="polite"
          accessibilityRole={Platform.OS === 'web' ? 'status' : undefined}
          style={styles.announcement}
        >
          {announcement}
        </ThemedText>
        {preview && (
          <ThemedText style={styles.subtitle}>
            Sample data · practice only; progress is not saved.
          </ThemedText>
        )}
        {loading && (
          <ActivityIndicator
            color={colors.primary}
            accessibilityLabel="Loading review"
          />
        )}
        {item && (
          <>
            <ThemedText style={styles.progress}>
              WORD {position} OF {total}
            </ThemedText>
            {preview && !result && (
              <View style={styles.modeRow}>
                {(['choice', 'typing'] as const).map((value) => (
                  <Pressable
                    key={value}
                    accessibilityRole="radio"
                    accessibilityState={{ checked: mode === value }}
                    onPress={() => {
                      setMode(value);
                      setAnswer('');
                    }}
                    style={[styles.modeButton, mode === value && styles.button]}
                  >
                    <ThemedText
                      style={
                        mode === value ? styles.buttonText : styles.subtitle
                      }
                    >
                      {value === 'choice' ? 'Multiple choice' : 'Typing'}
                    </ThemedText>
                  </Pressable>
                ))}
              </View>
            )}
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
                {preview && mode === 'choice' ? (
                  <View style={styles.choices}>
                    {[
                      item.word!,
                      ...reviewPreviewWords
                        .filter((word) => word.word !== item.word)
                        .slice(0, 3)
                        .map((word) => word.word),
                    ]
                      .sort((a, b) => a.localeCompare(b))
                      .map((option, index) => (
                        <Pressable
                          key={option}
                          accessibilityRole="radio"
                          accessibilityState={{ checked: answer === option }}
                          onPress={() => setAnswer(option)}
                          style={[
                            styles.choice,
                            answer === option && styles.choiceSelected,
                          ]}
                        >
                          <ThemedText style={styles.explanation}>
                            {String.fromCharCode(65 + index)} {option}
                          </ThemedText>
                        </Pressable>
                      ))}
                  </View>
                ) : (
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
                    editable={!loading && !pendingBody && signedIn}
                    returnKeyType="done"
                    onSubmitEditing={() => void submit()}
                  />
                )}
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{
                    disabled:
                      loading ||
                      conflict ||
                      !signedIn ||
                      (preview && !answer.trim()),
                  }}
                  style={[styles.button, loading && styles.disabled]}
                  disabled={
                    loading ||
                    conflict ||
                    !signedIn ||
                    (preview && !answer.trim())
                  }
                  onPress={() => void submit()}
                >
                  <ThemedText style={styles.buttonText}>
                    {pendingBody
                      ? 'Retry submission'
                      : preview
                        ? 'Check answer'
                        : 'Submit answer'}
                  </ThemedText>
                </Pressable>
                <ThemedText style={styles.subtitle}>
                  {preview
                    ? 'Choose an answer or type the missing word.'
                    : 'The word is hidden until you submit.'}
                </ThemedText>
              </>
            )}
          </>
        )}
        {!!error && (
          <View accessibilityLiveRegion="polite">
            <ThemedText style={styles.error}>{error}</ThemedText>
            {(!item || conflict) && (
              <Pressable
                accessibilityRole="button"
                style={styles.button}
                onPress={next}
              >
                <ThemedText style={styles.buttonText}>
                  {conflict ? 'Next word' : 'Try again'}
                </ThemedText>
              </Pressable>
            )}
          </View>
        )}
        {!loading && !error && !item && (
          <View style={[styles.card, styles.finishedCard]}>
            <Image
              source={
                total
                  ? require('@/assets/images/wordwell/review-finished.svg')
                  : require('@/assets/images/wordwell/review-empty.svg')
              }
              style={{
                width: total ? 90 : 78,
                height: total ? 90 : 78,
                alignSelf: 'center',
              }}
              accessible={false}
            />
            <ThemedText style={[styles.title, styles.finishedTitle]}>
              {total ? 'Review finished!' : 'Nothing due'}
            </ThemedText>
            <ThemedText style={styles.finishedText}>
              {total
                ? `${correctCount} of ${reviewed} answers correct.`
                : 'You’re all caught up or have reached your daily limit. Add another word or come back later.'}
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
  modeRow: {
    flexDirection: 'row',
    gap: 6,
    padding: 4,
    backgroundColor: colors.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
  modeButton: {
    flex: 1,
    minHeight: 44,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 9,
  },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  choice: {
    flexGrow: 1,
    flexBasis: '45%',
    minHeight: 57,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    padding: 12,
    borderRadius: 11,
    justifyContent: 'center',
  },
  choiceSelected: {
    borderColor: colors.primary,
    backgroundColor: colors.primarySoft,
  },
  progress: {
    alignSelf: 'flex-start',
    backgroundColor: colors.primarySoft,
    color: colors.primary,
    borderRadius: 15,
    paddingHorizontal: 16,
    paddingVertical: 6,
    fontSize: 11,
    fontWeight: '700',
  },
  finishedCard: {
    marginTop: 24,
    minHeight: 430,
    justifyContent: 'center',
    alignItems: 'stretch',
    padding: 25,
    gap: 28,
  },
  finishedText: {
    textAlign: 'center',
    color: colors.secondary,
    fontSize: 15,
    lineHeight: 25,
  },
  finishedTitle: { textAlign: 'center', fontSize: 25 },
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
