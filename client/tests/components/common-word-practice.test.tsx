import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import AddWordScreen from '@/app/(app)/add-word';
import { CommonWordPractice } from '@/components/common-word-practice';
import { authenticatedFetch } from '@/services/auth';
import {
  loadCommonWords,
  CommonWordsError,
  type CommonWordQuestion,
} from '@/services/common-words';

jest.mock('@/services/common-words', () => ({
  ...jest.requireActual('@/services/common-words'),
  loadCommonWords: jest.fn(),
}));
const loadMock = jest.mocked(loadCommonWords);
const fetchMock = jest.mocked(authenticatedFetch);
const questions: readonly CommonWordQuestion[] = [
  {
    id: 'reliable',
    word: 'reliable',
    ipa: '/rɪˈlaɪəbl/',
    partOfSpeech: 'adjective',
    explanation: 'Someone or something you can depend on.',
    example: 'She is a reliable colleague.',
    question: 'What does reliable mean?',
    choices: [
      'Easy to forget',
      'Able to be trusted',
      'Very expensive',
      'Difficult to understand',
    ],
  },
  {
    id: 'eager',
    word: 'eager',
    partOfSpeech: 'adjective',
    explanation: 'Very interested and excited.',
    example: null,
    question: 'What does eager mean?',
    choices: [
      'Ready and excited',
      'Quiet and tired',
      'Hard to find',
      'Unwilling to help',
    ],
  },
];
const response = (body: unknown = {}, status = 200) =>
  ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }) as Response;
const onSaved = jest.fn();
const onBackToVocab = jest.fn();
function practice(active = true, savedWords: string[] = []) {
  return (
    <CommonWordPractice
      active={active}
      savedWords={savedWords}
      onSaved={onSaved}
      onBackToVocab={onBackToVocab}
    />
  );
}
async function choose(name = 'B. Able to be trusted') {
  await fireEvent.press(screen.getByRole('button', { name }));
}
async function advance() {
  await act(async () => {
    jest.advanceTimersByTime(800);
  });
}
function grade(path: string, options?: RequestInit) {
  if (path === '/words') return Promise.resolve(response({}, 201));
  const correctIndex = path.includes('/reliable/') ? 1 : 0;
  const selected = JSON.parse(String(options?.body)).selected_index;
  return Promise.resolve(
    response({
      result: selected === correctIndex ? 'correct' : 'incorrect',
      correctIndex,
      explanation: questions[path.includes('/reliable/') ? 0 : 1].explanation,
    }),
  );
}

beforeEach(() => {
  jest.useFakeTimers();
  loadMock.mockReset().mockResolvedValue(questions);
  fetchMock.mockReset().mockImplementation(grade);
  onSaved.mockClear();
  onBackToVocab.mockClear();
});
afterEach(() => jest.useRealTimers());

test('Common button triggers loading; Vocab stays default and inputs persist across tabs', async () => {
  await render(<AddWordScreen />);
  expect(loadMock).not.toHaveBeenCalled();
  await fireEvent.changeText(
    screen.getByPlaceholderText('Enter a word, e.g. create'),
    'create',
  );
  await fireEvent.press(screen.getByRole('tab', { name: 'Common' }));
  expect(screen.getByText('reliable')).toBeOnTheScreen();
  expect(loadMock).toHaveBeenCalledTimes(1);
  await fireEvent.press(screen.getByRole('tab', { name: 'Vocab' }));
  expect(screen.getByDisplayValue('create')).toBeOnTheScreen();
});

test('shows the word and IPA without revealing the explanation before answering', async () => {
  await render(practice());
  expect(screen.getByText('reliable')).toBeOnTheScreen();
  expect(
    screen.getByLabelText('IPA pronunciation: /rɪˈlaɪəbl/'),
  ).toBeOnTheScreen();
  expect(screen.queryByText(questions[0].explanation)).toBeNull();
  expect(screen.getAllByRole('button')).toHaveLength(4);
});

test('correct answer is submitted to server once and advances only after persistence', async () => {
  let resolve!: (value: Response) => void;
  fetchMock.mockReturnValueOnce(
    new Promise((done) => {
      resolve = done;
    }),
  );
  await render(practice());
  await choose();
  expect(screen.getByText('Checking your answer…')).toBeOnTheScreen();
  expect(screen.queryByText(/Correct!/)).toBeNull();
  await choose();
  await advance();
  expect(screen.getByText('Word 1 of 2')).toBeOnTheScreen();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith(
    '/common-words/questions/reliable/answer',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selected_index: 1 }),
    },
  );
  await act(async () => {
    resolve(
      response({
        result: 'correct',
        correctIndex: 1,
        explanation: questions[0].explanation,
      }),
    );
  });
  await advance();
  expect(screen.getByText('Word 2 of 2')).toBeOnTheScreen();
  expect(onSaved).not.toHaveBeenCalled();
});

test('answer failure holds the question and retry sends exactly the same selected choice', async () => {
  fetchMock.mockRejectedValueOnce(new Error('offline'));
  await render(practice());
  await choose('A. Easy to forget');
  expect(screen.getByRole('alert')).toBeOnTheScreen();
  expect(screen.queryByText('Save this word for later?')).toBeNull();
  await advance();
  expect(screen.getByText('Word 1 of 2')).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole('button', { name: 'Retry answer' }));
  expect(screen.getByText('CORRECT ANSWER')).toBeOnTheScreen();
  expect(fetchMock.mock.calls[0][1]?.body).toBe(
    fetchMock.mock.calls[1][1]?.body,
  );
});

test('incorrect answer is graded on backend, reveals feedback, and Skip never saves', async () => {
  await render(practice());
  await choose('A. Easy to forget');
  expect(screen.getByText('CORRECT ANSWER')).toBeOnTheScreen();
  expect(screen.getByText('adjective · Able to be trusted')).toBeOnTheScreen();
  expect(screen.getByText('Save this word for later?')).toBeOnTheScreen();
  expect(screen.getByText('Your answer: Easy to forget')).toBeOnTheScreen();
  await fireEvent.press(
    screen.getByRole('button', { name: 'Skip · Next word' }),
  );
  expect(screen.getByText('Word 2 of 2')).toBeOnTheScreen();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(onSaved).not.toHaveBeenCalled();
});

test('Save is explicit, prevents duplicate taps, and blocks Skip while pending', async () => {
  await render(practice());
  await choose('A. Easy to forget');
  let resolve!: (value: Response) => void;
  fetchMock.mockReturnValueOnce(
    new Promise((done) => {
      resolve = done;
    }),
  );
  await fireEvent.press(screen.getByRole('button', { name: 'Save word' }));
  expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
  expect(
    screen.getByRole('button', { name: 'Skip · Next word' }),
  ).toBeDisabled();
  expect(fetchMock).toHaveBeenLastCalledWith('/words', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      word: 'reliable',
      english_explanation: questions[0].explanation,
      example_sentence: questions[0].example,
    }),
  });
  await act(async () => {
    resolve(response({}, 201));
  });
  expect(screen.getByText('✓ Word saved to your bank')).toBeOnTheScreen();
  expect(onSaved).toHaveBeenCalledWith('reliable');
  await fireEvent.press(screen.getByRole('button', { name: 'Next word' }));
  await choose('A. Ready and excited');
  await advance();
  expect(screen.getByText('1 correct · 1 word saved')).toBeOnTheScreen();
  await fireEvent.press(
    screen.getByRole('button', { name: 'Practise more words' }),
  );
  expect(loadMock).toHaveBeenCalledTimes(2);
});

test('save failure can retry without resubmitting the graded answer', async () => {
  await render(practice());
  await choose('A. Easy to forget');
  fetchMock.mockResolvedValueOnce(response({}, 503));
  await fireEvent.press(screen.getByRole('button', { name: 'Save word' }));
  expect(screen.getByRole('alert')).toHaveTextContent(/Could not save/);
  await fireEvent.press(screen.getByRole('button', { name: 'Retry save' }));
  expect(screen.getByText('✓ Word saved to your bank')).toBeOnTheScreen();
  expect(
    fetchMock.mock.calls.filter(([path]) => path.includes('/answer')),
  ).toHaveLength(1);
});

test.each(['known', 'conflict'])(
  'already saved words (%s) do not inflate saved counts',
  async (kind) => {
    await render(practice(true, kind === 'known' ? ['reliable'] : []));
    await choose('A. Easy to forget');
    if (kind === 'conflict') fetchMock.mockResolvedValueOnce(response({}, 409));
    await fireEvent.press(
      screen.getByRole('button', {
        name: kind === 'known' ? 'Already saved · Continue' : 'Save word',
      }),
    );
    expect(screen.getByText('✓ Already in your word bank')).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole('button', { name: 'Next word' }));
    await choose('B. Quiet and tired');
    await fireEvent.press(
      screen.getByRole('button', { name: 'Skip · Next word' }),
    );
    expect(screen.getByText('0 correct · 0 words saved')).toBeOnTheScreen();
  },
);

test('generation failure offers retry and all-learned completion is explicit', async () => {
  loadMock
    .mockRejectedValueOnce(
      new CommonWordsError(
        'Could not prepare new words. Please try again shortly.',
      ),
    )
    .mockResolvedValueOnce([]);
  await render(practice());
  expect(screen.getByRole('alert')).toHaveTextContent(
    /Could not prepare new words/,
  );
  await fireEvent.press(screen.getByRole('button', { name: 'Try again' }));
  expect(screen.getByText('All Common words learned')).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole('button', { name: 'Back to Vocab' }));
  expect(onBackToVocab).toHaveBeenCalledTimes(1);
});

test('late batch loads are discarded after tab is hidden', async () => {
  let resolve!: (items: readonly CommonWordQuestion[]) => void;
  loadMock.mockReturnValueOnce(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const view = await render(practice());
  await view.rerender(practice(false));
  expect(loadMock.mock.calls[0][0]?.aborted).toBe(true);
  await act(async () => {
    resolve(questions);
  });
  expect(screen.queryByText('Word 1 of 2')).toBeNull();
  await view.rerender(practice());
  expect(screen.getByText('Word 1 of 2')).toBeOnTheScreen();
});

test('correct-answer progression pauses while tab is hidden', async () => {
  const view = await render(practice());
  await choose();
  await view.rerender(practice(false));
  await advance();
  expect(screen.getByText('Word 1 of 2')).toBeOnTheScreen();
  await view.rerender(practice());
  await advance();
  expect(screen.getByText('Word 2 of 2')).toBeOnTheScreen();
});

test('timer stops while grading and resets for the next question', async () => {
  await render(practice());
  await act(async () => {
    jest.advanceTimersByTime(2250);
  });
  expect(
    screen.getByLabelText('Time spent on this question: 0 minutes, 2 seconds'),
  ).toBeOnTheScreen();
  await choose('A. Easy to forget');
  await act(async () => {
    jest.advanceTimersByTime(5000);
  });
  expect(
    screen.getByLabelText('Time spent on this question: 0 minutes, 2 seconds'),
  ).toBeOnTheScreen();
  await fireEvent.press(
    screen.getByRole('button', { name: 'Skip · Next word' }),
  );
  expect(
    screen.getByLabelText('Time spent on this question: 0 minutes, 0 seconds'),
  ).toBeOnTheScreen();
});

test('timeout offers Check again and displays the resumed batch', async () => {
  loadMock
    .mockRejectedValueOnce(
      new CommonWordsError(
        'Words are still being prepared. Check again to resume this batch.',
      ),
    )
    .mockResolvedValueOnce(questions);
  await render(practice());
  expect(screen.queryByLabelText('Loading common words')).toBeNull();
  await fireEvent.press(screen.getByRole('button', { name: 'Check again' }));
  expect(screen.getByText('Word 1 of 2')).toBeOnTheScreen();
  expect(loadMock).toHaveBeenCalledTimes(2);
});
