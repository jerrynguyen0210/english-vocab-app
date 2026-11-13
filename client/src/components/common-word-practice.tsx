import { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';
import { authenticatedFetch } from '@/services/auth';
import { connectionMessage } from '@/services/connectivity';
import {
  loadCommonWords,
  CommonWordsError,
  type CommonWordQuestion,
} from '@/services/common-words';

type Phase = 'question' | 'correct' | 'reveal' | 'saved' | 'complete';

function Action({
  label,
  onPress,
  secondary = false,
  disabled = false,
  busy = false,
}: {
  label: string;
  onPress: () => void;
  secondary?: boolean;
  disabled?: boolean;
  busy?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled, busy }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary && styles.secondaryButton,
        (pressed || disabled) && styles.dimmed,
      ]}
    >
      <ThemedText style={[styles.buttonText, secondary && styles.primaryText]}>
        {label}
      </ThemedText>
    </Pressable>
  );
}

export function CommonWordPractice({
  active,
  savedWords,
  onSaved,
  onBackToVocab,
  onStepChange,
}: {
  active: boolean;
  savedWords: readonly string[];
  onSaved: (word: string) => void;
  onBackToVocab: () => void;
  onStepChange?: () => void;
}) {
  const [questions, setQuestions] = useState<
    readonly CommonWordQuestion[] | null
  >(null);
  const [loadError, setLoadError] = useState('');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [phase, setPhase] = useState<Phase>('question');
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [correctCount, setCorrectCount] = useState(0);
  const [batchSaved, setBatchSaved] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [alreadySaved, setAlreadySaved] = useState(false);
  const answerLocked = useRef(false);
  const savePending = useRef(false);
  const mounted = useRef(true);
  const loadedQuestionIds = useRef(new Set<string>());
  const question = questions?.[index];

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!active || questions !== null) return;
    let cancelled = false;
    const controller = new AbortController();
    loadCommonWords([...loadedQuestionIds.current], controller.signal).then(
      (items) => {
        if (!cancelled) {
          setLoadError('');
          items.forEach((item) => loadedQuestionIds.current.add(item.id));
          setQuestions(items);
        }
      },
      (failure) => {
        if (!cancelled)
          setLoadError(
            failure instanceof CommonWordsError
              ? failure.message
              : connectionMessage(
                  failure,
                  'Could not load words. Please try again.',
                ),
          );
      },
    );
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [active, questions, loadAttempt]);

  const next = useCallback(() => {
    if (savePending.current) return;
    answerLocked.current = false;
    setSelected(null);
    setSaveError('');
    setAlreadySaved(false);
    onStepChange?.();
    if (questions && index + 1 >= questions.length) {
      setPhase('complete');
    } else {
      setIndex((current) => current + 1);
      setPhase('question');
    }
  }, [index, questions, onStepChange]);

  // Pause automatic progression when another tab or route is visible.
  useFocusEffect(
    useCallback(() => {
      if (!active || phase !== 'correct') return;
      const timer = setTimeout(next, 800);
      return () => clearTimeout(timer);
    }, [active, phase, next]),
  );

  function choose(choice: number) {
    if (!active || !question || phase !== 'question' || answerLocked.current)
      return;
    answerLocked.current = true;
    setSelected(choice);
    if (choice === question.correctIndex) {
      setCorrectCount((current) => current + 1);
      setPhase('correct');
    } else {
      setPhase('reveal');
    }
    onStepChange?.();
  }

  async function save() {
    if (!active || !question || phase !== 'reveal' || savePending.current)
      return;
    savePending.current = true;
    setSaving(true);
    setSaveError('');
    try {
      let exists = savedWords.includes(question.word);
      if (!exists) {
        // Saving is explicit; generated questions do not change the word bank.
        const response = await authenticatedFetch('/words', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            word: question.word,
            english_explanation: question.explanation,
            example_sentence: question.example,
          }),
        });
        if (!response.ok && response.status !== 409)
          throw new Error('Save failed');
        exists = response.status === 409;
      }
      if (!mounted.current) return;
      onSaved(question.word);
      setAlreadySaved(exists);
      if (!exists)
        setBatchSaved((current) => [...new Set([...current, question.word])]);
      setPhase('saved');
      onStepChange?.();
    } catch (failure) {
      if (mounted.current)
        setSaveError(
          connectionMessage(
            failure,
            `Could not save “${question.word}”. Please retry.`,
          ),
        );
    } finally {
      savePending.current = false;
      if (mounted.current) setSaving(false);
    }
  }

  function restart() {
    answerLocked.current = false;
    setIndex(0);
    setSelected(null);
    setCorrectCount(0);
    setBatchSaved([]);
    setSaveError('');
    setAlreadySaved(false);
    setPhase('question');
    setQuestions(null);
    setLoadError('');
    setLoadAttempt((current) => current + 1);
    onStepChange?.();
  }

  return (
    <View style={styles.content}>
      {loadError ? (
        <View style={styles.card}>
          <ThemedText accessibilityRole="alert" style={styles.body}>
            {loadError}
          </ThemedText>
          <Action
            label="Try again"
            onPress={() => {
              setLoadError('');
              setLoadAttempt((current) => current + 1);
            }}
          />
        </View>
      ) : questions === null ? (
        <View
          accessibilityLabel="Loading common words"
          accessibilityState={{ busy: true }}
          style={styles.loadingStatus}
        >
          <View style={styles.loadingStatusRow}>
            <ActivityIndicator color={colors.primary} accessible={false} />
            <ThemedText
              accessibilityLiveRegion="polite"
              style={styles.loadingTitle}
            >
              Loading words…
            </ThemedText>
          </View>
          <ThemedText style={[styles.body, styles.center]}>
            Preparing your next questions. This may take a moment.
          </ThemedText>
        </View>
      ) : questions.length === 0 ? (
        <View style={styles.card}>
          <ThemedText accessibilityRole="header" style={styles.heading}>
            No common words available
          </ThemedText>
          <ThemedText style={styles.body}>
            Try again later, or search for a word in Vocab.
          </ThemedText>
          <Action label="Try again" onPress={restart} />
          <Action label="Back to Vocab" onPress={onBackToVocab} secondary />
        </View>
      ) : phase === 'complete' ? (
        <>
          <View style={[styles.card, styles.completeCard]}>
            <View style={styles.successMark}>
              <ThemedText style={styles.successIcon}>✓</ThemedText>
            </View>
            <ThemedText
              accessibilityRole="header"
              style={[styles.heading, styles.center]}
            >
              A little practice. Big progress.
            </ThemedText>
            <ThemedText style={[styles.body, styles.center]}>
              You explored {questions.length} everyday{' '}
              {questions.length === 1 ? 'word' : 'words'}.
            </ThemedText>
            <ThemedText
              accessibilityLiveRegion="polite"
              style={[styles.summary, styles.center]}
            >
              {correctCount} correct · {batchSaved.length}{' '}
              {batchSaved.length === 1 ? 'word' : 'words'} saved
            </ThemedText>
            <ThemedText style={[styles.body, styles.center]}>
              {batchSaved.length
                ? 'Your saved words are ready in Review.'
                : 'Keep exploring to find words you want to learn.'}
            </ThemedText>
          </View>
          <Action label="Practise more words" onPress={restart} />
          <Action label="Back to Vocab" onPress={onBackToVocab} secondary />
        </>
      ) : question ? (
        <>
          <View style={styles.progressRow}>
            <ThemedText style={styles.eyebrow}>EVERYDAY ENGLISH</ThemedText>
            <ThemedText
              accessibilityLiveRegion="polite"
              style={styles.progressLabel}
            >
              Word {index + 1} of {questions.length}
            </ThemedText>
          </View>
          <View
            accessibilityRole="progressbar"
            accessibilityLabel="Common word progress"
            accessibilityValue={{
              min: 0,
              max: questions.length,
              now: index,
              text: `Word ${index + 1} of ${questions.length}`,
            }}
            style={styles.progressTrack}
          >
            <View
              style={[
                styles.progressFill,
                { width: `${((index + 1) / questions.length) * 100}%` },
              ]}
            />
          </View>
          {phase === 'reveal' || phase === 'saved' ? (
            <>
              <View
                style={[
                  styles.banner,
                  phase === 'saved' ? styles.successBanner : styles.errorBanner,
                ]}
              >
                <ThemedText
                  accessibilityLiveRegion="polite"
                  style={[
                    styles.bannerText,
                    phase === 'saved' ? styles.successText : styles.errorText,
                  ]}
                >
                  {phase === 'saved'
                    ? alreadySaved
                      ? '✓ Already in your word bank'
                      : '✓ Word saved to your bank'
                    : 'Not quite — let’s learn this one'}
                </ThemedText>
              </View>
              <View style={[styles.card, styles.revealCard]}>
                <ThemedText style={[styles.eyebrow, styles.successText]}>
                  CORRECT ANSWER
                </ThemedText>
                <ThemedText accessibilityRole="header" style={styles.word}>
                  {question.word}
                </ThemedText>
                <ThemedText style={[styles.meaning, styles.successText]}>
                  {question.partOfSpeech} ·{' '}
                  {question.choices[question.correctIndex]}
                </ThemedText>
                <ThemedText style={styles.body}>
                  {question.explanation}
                </ThemedText>
                <ThemedText style={styles.body}>
                  “{question.example}”
                </ThemedText>
                {selected !== null && (
                  <ThemedText style={styles.previousAnswer}>
                    Your answer: {question.choices[selected]}
                  </ThemedText>
                )}
              </View>
              <View style={styles.savePrompt}>
                <ThemedText accessibilityRole="header" style={styles.heading}>
                  {phase === 'saved'
                    ? 'Ready for another word?'
                    : 'Save this word for later?'}
                </ThemedText>
                <ThemedText style={styles.body}>
                  {phase === 'saved'
                    ? `You can practise “${question.word}” in Review.`
                    : 'Add it to your bank and practise in Review.'}
                </ThemedText>
              </View>
              {!!saveError && (
                <ThemedText accessibilityRole="alert" style={styles.errorText}>
                  {saveError}
                </ThemedText>
              )}
              {phase === 'saved' ? (
                <Action label="Next word" onPress={next} />
              ) : (
                <>
                  <Action
                    label={
                      saving
                        ? 'Saving…'
                        : saveError
                          ? 'Retry save'
                          : savedWords.includes(question.word)
                            ? 'Already saved · Continue'
                            : 'Save word'
                    }
                    disabled={saving}
                    busy={saving}
                    onPress={() => void save()}
                  />
                  <Action
                    label="Skip · Next word"
                    disabled={saving}
                    onPress={next}
                    secondary
                  />
                </>
              )}
            </>
          ) : (
            <>
              <View style={styles.card}>
                <ThemedText style={styles.body}>
                  Choose the closest meaning
                </ThemedText>
                <ThemedText accessibilityRole="header" style={styles.word}>
                  {question.word}
                </ThemedText>
                <ThemedText style={styles.partOfSpeech}>
                  {question.partOfSpeech}
                </ThemedText>
                <ThemedText style={styles.body}>
                  “{question.example}”
                </ThemedText>
              </View>
              <View
                style={styles.choices}
                accessibilityLabel={`Answer choices for ${question.word}`}
              >
                {question.choices.map((choice, choiceIndex) => {
                  const correct =
                    phase === 'correct' && selected === choiceIndex;
                  return (
                    <Pressable
                      key={choice}
                      accessibilityRole="button"
                      accessibilityLabel={`${'ABCD'[choiceIndex]}. ${choice}`}
                      accessibilityState={{
                        disabled: phase !== 'question',
                        selected: selected === choiceIndex,
                      }}
                      disabled={phase !== 'question'}
                      onPress={() => choose(choiceIndex)}
                      style={({ pressed }) => [
                        styles.choice,
                        correct && styles.correctChoice,
                        pressed && styles.dimmed,
                      ]}
                    >
                      <View
                        style={[
                          styles.choiceLetter,
                          correct && styles.correctLetter,
                        ]}
                      >
                        <ThemedText
                          style={[
                            styles.letterText,
                            correct && styles.whiteText,
                          ]}
                        >
                          {correct ? '✓' : 'ABCD'[choiceIndex]}
                        </ThemedText>
                      </View>
                      <ThemedText
                        style={[
                          styles.choiceText,
                          correct && styles.successText,
                        ]}
                      >
                        {choice}
                      </ThemedText>
                    </Pressable>
                  );
                })}
              </View>
              <ThemedText
                accessibilityLiveRegion="polite"
                style={[styles.hint, phase === 'correct' && styles.successText]}
              >
                {phase === 'correct'
                  ? '✓ Correct! Moving to the next word…'
                  : 'Tap an answer to continue'}
              </ThemedText>
            </>
          )}
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  content: { gap: 12, paddingTop: 20 },
  revealCard: { gap: 8 },
  savePrompt: { gap: 6 },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 16,
    padding: 20,
    gap: 16,
  },
  body: {
    color: colors.secondary,
    fontSize: 13,
    lineHeight: 21,
    fontWeight: '400',
  },
  heading: {
    color: colors.text,
    fontSize: 19,
    lineHeight: 27,
    fontWeight: '700',
  },
  word: { color: colors.text, fontSize: 32, lineHeight: 40, fontWeight: '800' },
  meaning: { fontSize: 14, lineHeight: 22, fontWeight: '600' },
  partOfSpeech: {
    color: colors.primary,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '600',
    marginTop: -12,
  },
  eyebrow: {
    color: colors.primary,
    fontSize: 11,
    lineHeight: 17,
    fontWeight: '700',
  },
  progressRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  progressLabel: { color: colors.secondary, fontSize: 12, lineHeight: 18 },
  progressTrack: {
    height: 5,
    borderRadius: 3,
    backgroundColor: colors.border,
    overflow: 'hidden',
    marginTop: -6,
    marginBottom: 4,
  },
  progressFill: {
    height: '100%',
    backgroundColor: colors.primary,
    borderRadius: 3,
  },
  choices: { gap: 8 },
  choice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    minHeight: 48,
    paddingVertical: 9,
    paddingHorizontal: 12,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
  },
  choiceLetter: {
    width: 28,
    height: 28,
    borderRadius: 8,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  letterText: {
    color: colors.primary,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '700',
  },
  choiceText: {
    flex: 1,
    color: colors.text,
    fontSize: 13,
    lineHeight: 20,
    fontWeight: '600',
  },
  correctChoice: {
    backgroundColor: colors.successBackground,
    borderColor: colors.success,
  },
  correctLetter: { backgroundColor: colors.success },
  whiteText: { color: colors.surface },
  hint: {
    color: colors.secondary,
    fontSize: 12,
    lineHeight: 20,
    textAlign: 'center',
    paddingVertical: 4,
  },
  banner: { borderRadius: 12, padding: 14 },
  bannerText: { fontSize: 13, lineHeight: 21, fontWeight: '700' },
  successBanner: { backgroundColor: colors.successBackground },
  errorBanner: { backgroundColor: colors.errorBackground },
  successText: { color: colors.success },
  errorText: { color: colors.error, fontSize: 13, lineHeight: 21 },
  previousAnswer: {
    color: colors.secondary,
    fontSize: 12,
    lineHeight: 20,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: 12,
  },
  button: {
    minHeight: 48,
    borderRadius: 12,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 12,
  },
  buttonText: {
    color: colors.surface,
    fontSize: 14,
    lineHeight: 22,
    fontWeight: '700',
    textAlign: 'center',
  },
  primaryText: { color: colors.primary },
  secondaryButton: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
  },
  dimmed: { opacity: 0.65 },
  completeCard: {
    alignItems: 'center',
    paddingVertical: 32,
    gap: 24,
    marginTop: 10,
    marginBottom: 12,
  },
  center: { textAlign: 'center' },
  summary: {
    color: colors.primary,
    fontSize: 16,
    lineHeight: 25,
    fontWeight: '700',
  },
  successMark: {
    width: 73,
    height: 73,
    borderRadius: 24,
    backgroundColor: colors.successBackground,
    alignItems: 'center',
    justifyContent: 'center',
  },
  successIcon: {
    color: colors.success,
    fontSize: 35,
    lineHeight: 43,
    fontWeight: '700',
  },
  loadingStatus: { alignItems: 'center', gap: 8, paddingVertical: 16 },
  loadingStatusRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  loadingTitle: {
    color: colors.text,
    fontSize: 16,
    lineHeight: 24,
    fontWeight: '700',
  },
});
