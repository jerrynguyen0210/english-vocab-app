import { authenticatedFetch } from '@/services/auth';

// Only these fixed, client-owned messages may be shown directly in the UI.
export class CommonWordsError extends Error {}

export type CommonWordQuestion = {
  id: string;
  word: string;
  partOfSpeech: string;
  explanation: string;
  example: string;
  choices: readonly [string, string, string, string];
  correctIndex: number;
};

function isQuestion(value: unknown): value is CommonWordQuestion {
  if (!value || typeof value !== 'object') return false;
  const question = value as Record<string, unknown>;
  return (
    ['id', 'word', 'partOfSpeech', 'explanation', 'example'].every(
      (field) =>
        typeof question[field] === 'string' &&
        question[field].trim().length > 0,
    ) &&
    Array.isArray(question.choices) &&
    question.choices.length === 4 &&
    question.choices.every(
      (choice) => typeof choice === 'string' && choice.trim().length > 0,
    ) &&
    new Set(
      question.choices.map((choice: string) => choice.trim().toLowerCase()),
    ).size === 4 &&
    typeof question.correctIndex === 'number' &&
    Number.isInteger(question.correctIndex) &&
    question.correctIndex >= 0 &&
    question.correctIndex < 4
  );
}

function waitForGeneration(signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error('Request cancelled'));
      return;
    }
    const cancel = () => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', cancel);
      reject(new Error('Request cancelled'));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', cancel);
      resolve();
    }, 2000);
    signal?.addEventListener('abort', cancel, { once: true });
  });
}

/** The worker generates questions; short authenticated requests poll its durable job. */
export async function loadCommonWords(
  excludeIds: readonly string[] = [],
  signal?: AbortSignal,
): Promise<readonly CommonWordQuestion[]> {
  if (signal?.aborted) throw new Error('Request cancelled');
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener('abort', cancel, { once: true });
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      pollCommonWords(excludeIds, controller.signal),
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

async function pollCommonWords(
  excludeIds: readonly string[],
  signal: AbortSignal,
): Promise<readonly CommonWordQuestion[]> {
  const body = JSON.stringify({ exclude_ids: excludeIds.slice(-1000) });
  while (true) {
    if (signal?.aborted) throw new Error('Request cancelled');
    const response = await authenticatedFetch('/common-words/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      signal,
    });
    if (!response.ok)
      throw new CommonWordsError('Could not load common words.');
    const batch: unknown = await response.json();
    if (!batch || typeof batch !== 'object' || !('status' in batch))
      throw new CommonWordsError(
        'The server returned an invalid response. Please try again.',
      );
    if (batch.status === 'failed')
      throw new CommonWordsError(
        'Could not prepare new words. Please try again shortly.',
      );
    if (batch.status === 'ready') {
      if (
        !('questions' in batch) ||
        !Array.isArray(batch.questions) ||
        batch.questions.length > 10 ||
        !batch.questions.every(isQuestion) ||
        new Set(batch.questions.map((question) => question.id)).size !==
          batch.questions.length
      )
        throw new CommonWordsError(
          'The server returned invalid questions. Please try again.',
        );
      return batch.questions;
    }
    if (batch.status !== 'pending')
      throw new CommonWordsError(
        'The server returned an invalid response. Please try again.',
      );
    await waitForGeneration(signal);
  }
}
