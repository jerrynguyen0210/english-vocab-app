import { useLocalSearchParams } from 'expo-router';
import {
  reviewQuery,
  reviewEmptyKind,
  type ReviewSummary,
} from '@/services/review';
import { ReviewEmptyState } from '@/components/review-empty-state';
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
  prompt_sentence: string;
  review_token?: string;
  choices?: string[];
};
type Result = { result: 'correct' | 'incorrect'; correct_word: string };
function hasFourChoices(choices: string[] | undefined): choices is string[] {
  return (
    Array.isArray(choices) &&
    choices.length === 4 &&
    choices.every(
      (value) => typeof value === 'string' && value.trim().length > 0,
    ) &&
    new Set(
      choices.map((value) => value.normalize('NFKC').trim().toLowerCase()),
    ).size === 4
  );
}

export default function ReviewScreen() {
  const params = useLocalSearchParams<{
    source?: string;
    period?: string;
    includeOverdue?: string;
  }>();
  const [mode, setMode] = useState<'choice' | 'typing'>('typing');
  const query = reviewQuery(params);
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
  const [emptySummary, setEmptySummary] = useState<
    (ReviewSummary & { matching_count: number }) | null
  >(null);
  const answerInput = useRef<ComponentRef<typeof TextInput>>(null);
  const busy = useRef(false);
  const started = useRef(0);
  const mounted = useRef(true);
  const loadVersion = useRef(0);

  const load = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    const version = ++loadVersion.current;
    void authenticatedFetch(`/reviews/session?${query}&answer_mode=typing`)
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const items: Prompt[] = await response.json();
        let emptyData: (ReviewSummary & { matching_count: number }) | null =
          null;
        if (items.length === 0) {
          const status = await authenticatedFetch(
            `/reviews/preparation?${query}`,
          );
          if (!status.ok) throw new Error();
          emptyData = await status.json();
        }
        if (mounted.current && version === loadVersion.current) {
          setEmptySummary(emptyData);
          setReviewed(0);
          setCorrectCount(0);
          setResult(null);
          setAnswer('');
          setPendingBody(null);
          setConflict(false);
          setError('');
          queue.current = items.slice(1);
          setTotal(items.length);
          setPosition(1);
          setItem(items[0] ?? null);
          started.current = performance.now();
        }
      })
      .catch((error) => {
        if (mounted.current && version === loadVersion.current)
          setError(
            connectionMessage(
              error,
              'Could not load your review. Please try again.',
            ),
          );
      })
      .finally(() => {
        if (version === loadVersion.current) {
          busy.current = false;
          if (mounted.current) setLoading(false);
        }
      });
  }, [query]);

  function next(startedAt: number) {
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
    const following = queue.current.shift() ?? null;
    setItem(following);
    setPosition((value) => value + 1);
    started.current = startedAt;
    setLoading(false);
    if (following && mode === 'choice') void chooseMode('choice', following);
  }

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
      loadVersion.current += 1;
      busy.current = false;
    };
  }, [load]);

  const serverChoices = item?.choices;
  const choiceAvailable = hasFourChoices(serverChoices);
  const canLoadChoices =
    choiceAvailable || (!!item?.review_token && serverChoices === undefined);

  async function chooseMode(value: 'typing' | 'choice', prompt = item) {
    if (!prompt || busy.current || (prompt === item && (pendingBody || result)))
      return;
    setAnswer('');
    setError('');
    if (value === 'typing') {
      setMode(value);
      setItem({ ...prompt, choices: undefined });
      return;
    }
    if (hasFourChoices(prompt.choices)) {
      setMode(value);
      return;
    }
    if (!prompt.review_token) return;
    busy.current = true;
    setLoading(true);
    const version = loadVersion.current;
    try {
      const response = await authenticatedFetch(
        `/reviews/${prompt.word_id}/choices`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            attempt_id: prompt.attempt_id,
            review_token: prompt.review_token,
          }),
        },
      );
      if (!response.ok) throw new Error();
      const loaded: Prompt = await response.json();
      if (
        !hasFourChoices(loaded.choices) ||
        loaded.word_id !== prompt.word_id ||
        loaded.attempt_id !== prompt.attempt_id
      )
        throw new Error();
      if (mounted.current && version === loadVersion.current) {
        setItem({ ...prompt, choices: loaded.choices });
        setMode('choice');
      }
    } catch (failure) {
      if (mounted.current && version === loadVersion.current) {
        setMode('typing');
        setError(
          connectionMessage(
            failure,
            'Could not load answer options. Try Multiple choice again, or type your answer.',
          ),
        );
      }
    } finally {
      if (version === loadVersion.current) {
        busy.current = false;
        if (mounted.current) setLoading(false);
      }
    }
  }

  useEffect(() => {
    // Wait until the loaded prompt is editable, including after a failed submit.
    if (
      signedIn &&
      (mode === 'typing' || !choiceAvailable) &&
      item &&
      !loading &&
      !result &&
      !pendingBody
    ) {
      answerInput.current?.focus();
    }
  }, [signedIn, mode, item, loading, result, pendingBody, choiceAvailable]);

  const finished = !loading && !error && !item;
  const progressPercent =
    total > 0 ? Math.min(100, Math.round((position / total) * 100)) : 0;
  const progressLabel = `Word ${position} of ${total}, ${progressPercent}% complete`;
  const completionText =
    reviewed === total
      ? `You reviewed all ${reviewed} ${reviewed === 1 ? 'word' : 'words'}.`
      : `You reviewed ${reviewed} of ${total} words.`;
  const emptyKind = emptySummary
    ? reviewEmptyKind(emptySummary, emptySummary.matching_count)
    : 'nothing_due';
  const announcement = result
    ? result.result === 'correct'
      ? `Correct answer! The word is ${result.correct_word}.`
      : `Incorrect answer. Your answer: ${answer || 'No answer'}. Correct word: ${result.correct_word}.`
    : finished
      ? total
        ? `Review finished. ${completionText} ${correctCount} of ${reviewed} answers correct.`
        : emptyKind === 'empty_bank'
          ? 'Empty word bank. Add your first word.'
          : emptyKind === 'nothing_due'
            ? "Nothing due. You're all caught up."
            : emptyKind === 'daily_limit'
              ? 'Daily review limit reached.'
              : 'No words match this review.'
      : '';

  useEffect(() => {
    // Android and web use the persistent live region below; VoiceOver needs this.
    if (Platform.OS === 'ios' && announcement) {
      AccessibilityInfo.announceForAccessibility(announcement);
    }
  }, [announcement]);

  async function submit() {
    if (
      !signedIn ||
      !item ||
      result ||
      conflict ||
      busy.current ||
      (!pendingBody && !answer.trim())
    )
      return;
    busy.current = true;
    setLoading(true);
    setError('');
    const body =
      pendingBody ??
      JSON.stringify({
        attempt_id: item.attempt_id,
        ...(item.review_token ? { review_token: item.review_token } : {}),
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
            'This review item has expired or changed. Continue to the next item.',
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
              : emptyKind === 'empty_bank'
                ? 'Empty word bank'
                : emptyKind === 'nothing_due'
                  ? 'Nothing due'
                  : emptyKind === 'daily_limit'
                    ? 'Daily review limit reached'
                    : 'No matching words'
            : 'Review your words'}
        </ThemedText>
        <ThemedText style={styles.subtitle}>
          {finished
            ? total
              ? reviewed === total
                ? 'You have completed this review.'
                : 'This review session has ended.'
              : 'Add a word or choose another review.'
            : 'Fill the blank with the missing word.'}
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
            <View
              accessible
              accessibilityLabel={progressLabel}
              style={styles.progressRow}
            >
              <ThemedText style={styles.progress}>
                Word {position} of {total}
              </ThemedText>
              <ThemedText style={styles.subtitle}>
                {progressPercent}% complete
              </ThemedText>
            </View>
            <View accessible={false} style={styles.progressTrack}>
              <View
                style={[styles.progressFill, { width: `${progressPercent}%` }]}
              />
            </View>
            {!result && (
              <View style={styles.modeRow}>
                {(['choice', 'typing'] as const).map((value) => (
                  <Pressable
                    key={value}
                    disabled={
                      loading ||
                      !!pendingBody ||
                      (value === 'choice' && !canLoadChoices)
                    }
                    accessibilityRole="radio"
                    accessibilityState={{
                      disabled:
                        loading ||
                        !!pendingBody ||
                        (value === 'choice' && !canLoadChoices),
                      checked: (choiceAvailable ? mode : 'typing') === value,
                    }}
                    onPress={() => void chooseMode(value)}
                    style={[
                      styles.modeButton,
                      (choiceAvailable ? mode : 'typing') === value &&
                        styles.button,
                    ]}
                  >
                    <ThemedText
                      style={
                        (choiceAvailable ? mode : 'typing') === value
                          ? styles.buttonText
                          : styles.subtitle
                      }
                    >
                      {value === 'choice' ? 'Multiple choice' : 'Typing'}
                    </ThemedText>
                  </Pressable>
                ))}
              </View>
            )}
            <ThemedText style={styles.question}>
              Complete the sentence
            </ThemedText>
            <View style={styles.card}>
              <ThemedText style={styles.label}>FILL IN THE BLANK</ThemedText>
              <ThemedText style={styles.sentence}>
                {item.prompt_sentence}
              </ThemedText>
            </View>
            {result ? (
              <>
                <View
                  testID="review-feedback"
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
                  <ThemedText
                    accessibilityRole="header"
                    style={styles.question}
                  >
                    {result.result === 'correct'
                      ? 'Correct answer!'
                      : 'Incorrect answer'}
                  </ThemedText>
                  {result.result === 'correct' ? (
                    <View style={styles.comparisonColumn}>
                      <ThemedText style={styles.label}>CORRECT WORD</ThemedText>
                      <ThemedText style={styles.explanation}>
                        {result.correct_word}
                      </ThemedText>
                    </View>
                  ) : (
                    <View style={styles.comparison}>
                      <View style={styles.comparisonColumn}>
                        <ThemedText style={styles.label}>
                          YOUR ANSWER
                        </ThemedText>
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
                  onPress={() => next(performance.now())}
                  disabled={loading}
                >
                  <ThemedText style={styles.buttonText}>Next word</ThemedText>
                </Pressable>
              </>
            ) : (
              <>
                <ThemedText style={styles.question}>Your answer</ThemedText>
                {mode === 'choice' && !!choiceAvailable ? (
                  <View style={styles.choices}>
                    {serverChoices!.map((option, index) => (
                      <Pressable
                        key={option}
                        accessibilityRole="radio"
                        accessibilityState={{ checked: answer === option }}
                        disabled={loading || !!pendingBody || !signedIn}
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
                    autoComplete="off"
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
                      loading || conflict || !signedIn || !answer.trim(),
                  }}
                  style={[styles.button, loading && styles.disabled]}
                  disabled={loading || conflict || !signedIn || !answer.trim()}
                  onPress={() => void submit()}
                >
                  <ThemedText style={styles.buttonText}>
                    {pendingBody ? 'Retry submission' : 'Check answer'}
                  </ThemedText>
                </Pressable>
                <ThemedText style={styles.subtitle}>
                  {mode === 'typing' || !choiceAvailable
                    ? 'Spelling matters · Enter to submit'
                    : 'Select one answer, then check it.'}
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
                onPress={() => next(performance.now())}
              >
                <ThemedText style={styles.buttonText}>
                  {conflict ? 'Next word' : 'Try again'}
                </ThemedText>
              </Pressable>
            )}
          </View>
        )}
        {finished && total === 0 && (
          <>
            <ReviewEmptyState kind={emptyKind} />
            <NavigationLink href="/" label="Back to Home" style={styles.button}>
              <ThemedText style={styles.buttonText}>Back to Home</ThemedText>
            </NavigationLink>
          </>
        )}
        {finished && total > 0 && (
          <View style={[styles.card, styles.finishedCard]}>
            <Image
              source={require('@/assets/images/wordwell/review-finished.svg')}
              style={{ width: 90, height: 90, alignSelf: 'center' }}
              accessible={false}
            />
            <ThemedText
              accessibilityRole="header"
              style={[styles.title, styles.finishedTitle]}
            >
              Review finished
            </ThemedText>
            <ThemedText style={styles.finishedText}>
              {completionText}
            </ThemedText>
            <ThemedText style={styles.finishedText}>
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
  progressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: 8,
  },
  progressTrack: {
    height: 6,
    backgroundColor: colors.border,
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: colors.primary,
    borderRadius: 3,
  },
  sentence: {
    color: colors.text,
    fontSize: 18,
    lineHeight: 29,
    fontWeight: '600',
  },
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
