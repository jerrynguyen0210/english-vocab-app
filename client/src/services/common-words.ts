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

const BATCH_DEADLINE_MS = 5 * 60 * 1000;
const POLL_INTERVAL_MS = 3000;

function waitForBatch(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const cancel = () => {
      clearTimeout(timer);
      reject(new Error('Request cancelled'));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', cancel);
      resolve();
    }, POLL_INTERVAL_MS);
    signal.addEventListener('abort', cancel, { once: true });
    if (signal.aborted) cancel();
  });
}

/** Start/resume the account's batch, then read its status until ready. */
export async function loadCommonWords(
  signal?: AbortSignal,
): Promise<readonly CommonWordQuestion[]> {
  if (signal?.aborted) throw new Error('Request cancelled');
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener('abort', cancel, { once: true });
  let timer: ReturnType<typeof setTimeout> | undefined;
  let rejectCancelled: (() => void) | undefined;
  try {
    return await Promise.race([
      (async () => {
        let batchId: string | null = null;
        while (!controller.signal.aborted) {
          const response = await authenticatedFetch(
            batchId
              ? `/common-words/batches/${batchId}`
              : '/common-words/batches',
            batchId
              ? { signal: controller.signal }
              : { method: 'POST', signal: controller.signal },
          );
          if (!response.ok)
            throw new CommonWordsError(
              'Could not check question preparation. Please try again.',
            );
          const batch: unknown = await response.json();
          if (
            !batch ||
            typeof batch !== 'object' ||
            !('id' in batch) ||
            typeof batch.id !== 'string' ||
            !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
              batch.id,
            ) ||
            (batchId !== null && batch.id !== batchId) ||
            !('status' in batch) ||
            !('questions' in batch) ||
            !Array.isArray(batch.questions)
          )
            throw new CommonWordsError(
              'The server returned an invalid response. Please try again.',
            );
          batchId = batch.id;
          if (batch.status === 'failed')
            throw new CommonWordsError(
              'Question preparation failed. Please try again.',
            );
          if (batch.status === 'complete' && batch.questions.length === 0)
            return [];
          if (batch.status === 'ready') {
            if (
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
          }
          if (
            !['pending', 'generating'].includes(String(batch.status)) ||
            batch.questions.length !== 0
          )
            throw new CommonWordsError(
              'The server returned an invalid response. Please try again.',
            );
          await waitForBatch(controller.signal);
        }
        throw new Error('Request cancelled');
      })(),
      new Promise<never>((_, reject) => {
        rejectCancelled = () => reject(new Error('Request cancelled'));
        controller.signal.addEventListener('abort', rejectCancelled, {
          once: true,
        });
        timer = setTimeout(() => {
          reject(
            new CommonWordsError(
              'Words are still being prepared. Check again to resume this batch.',
            ),
          );
          controller.abort();
        }, BATCH_DEADLINE_MS);
      }),
    ]);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
    if (rejectCancelled)
      controller.signal.removeEventListener('abort', rejectCancelled);
    controller.abort();
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
