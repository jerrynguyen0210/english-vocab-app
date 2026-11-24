import { authenticatedFetch } from '@/services/auth';

// Only fixed client-owned messages may be shown directly in the UI.
export class CommonWordsError extends Error {}

export type CommonWordQuestion = {
  id: string;
  word: string;
  ipa?: string | null;
  partOfSpeech: string;
  explanation: string;
  example: string | null;
  question: string;
  choices: readonly [string, string, string, string];
};

export type CommonAnswer = {
  result: 'correct' | 'incorrect';
  correctIndex: number;
  explanation: string;
};

function isQuestion(value: unknown): value is CommonWordQuestion {
  if (!value || typeof value !== 'object') return false;
  const question = value as Record<string, unknown>;
  return (
    ['id', 'word', 'partOfSpeech', 'explanation', 'question'].every(
      (field) =>
        typeof question[field] === 'string' &&
        question[field].trim().length > 0,
    ) &&
    (question.example === null || typeof question.example === 'string') &&
    (question.ipa == null ||
      (typeof question.ipa === 'string' &&
        question.ipa.length <= 120 &&
        /^\/[^/\r\n]+\/$/.test(question.ipa))) &&
    !('correctIndex' in question) &&
    Array.isArray(question.choices) &&
    question.choices.length === 4 &&
    question.choices.every(
      (choice) => typeof choice === 'string' && choice.trim().length > 0,
    ) &&
    new Set(
      question.choices.map((choice: string) => choice.trim().toLowerCase()),
    ).size === 4
  );
}

/** One request selects bank words and generates questions; no background polling. */
export async function loadCommonWords(
  signal?: AbortSignal,
): Promise<readonly CommonWordQuestion[]> {
  if (signal?.aborted) throw new Error('Request cancelled');
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener('abort', cancel, { once: true });
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      (async () => {
        const response = await authenticatedFetch(
          '/common-words/batch',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
            signal: controller.signal,
          },
          5 * 60 * 1000,
        );
        if (!response.ok)
          throw new CommonWordsError(
            'Could not prepare new words. Please try again shortly.',
          );
        const batch: unknown = await response.json();
        if (
          !batch ||
          typeof batch !== 'object' ||
          !('status' in batch) ||
          !('questions' in batch) ||
          !Array.isArray(batch.questions)
        )
          throw new CommonWordsError(
            'The server returned an invalid response. Please try again.',
          );
        if (batch.status === 'complete' && batch.questions.length === 0)
          return [];
        if (
          batch.status !== 'ready' ||
          batch.questions.length < 1 ||
          batch.questions.length > 10 ||
          !batch.questions.every(isQuestion) ||
          new Set(batch.questions.map((item) => item.id)).size !==
            batch.questions.length
        )
          throw new CommonWordsError(
            'The server returned invalid questions. Please try again.',
          );
        return batch.questions;
      })(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () => {
            reject(
              new CommonWordsError(
                'Words are still being prepared. Please try again shortly.',
              ),
            );
            controller.abort();
          },
          5 * 60 * 1000,
        );
      }),
    ]);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}

export async function answerCommonQuestion(
  questionId: string,
  selectedIndex: number,
): Promise<CommonAnswer> {
  const response = await authenticatedFetch(
    `/common-words/questions/${questionId}/answer`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selected_index: selectedIndex }),
    },
  );
  if (!response.ok)
    throw new CommonWordsError('Could not check your answer. Please retry.');
  const result: unknown = await response.json();
  if (
    !result ||
    typeof result !== 'object' ||
    !('result' in result) ||
    !['correct', 'incorrect'].includes(String(result.result)) ||
    !('correctIndex' in result) ||
    !Number.isInteger(result.correctIndex) ||
    Number(result.correctIndex) < 0 ||
    Number(result.correctIndex) > 3 ||
    !('explanation' in result) ||
    typeof result.explanation !== 'string' ||
    (result.result === 'correct') !== (result.correctIndex === selectedIndex)
  )
    throw new CommonWordsError(
      'The server returned an invalid answer. Please retry.',
    );
  return result as CommonAnswer;
}
