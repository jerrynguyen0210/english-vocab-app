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
    partOfSpeech: 'adjective',
    explanation: 'Someone or something you can depend on.',
    example: 'She is a reliable colleague.',
    choices: [
      'Easy to forget',
      'Able to be trusted',
      'Very expensive',
      'Difficult to understand',
    ],
    correctIndex: 1,
  },
  {
    id: 'eager',
    word: 'eager',
    partOfSpeech: 'adjective',
    explanation: 'Very interested and excited about doing something.',
    example: 'He was eager to learn more.',
    choices: [
      'Ready and excited',
      'Quiet and tired',
      'Hard to find',
      'Unwilling to help',
    ],
    correctIndex: 0,
  },
];
const response = (status = 201) =>
  ({ ok: status >= 200 && status < 300, status }) as Response;
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
async function advance() {
  await act(async () => {
    jest.advanceTimersByTime(800);
  });
}

beforeEach(() => {
  jest.useFakeTimers();
  loadMock.mockReset().mockResolvedValue(questions);
  fetchMock.mockReset().mockResolvedValue(response());
  onSaved.mockClear();
  onBackToVocab.mockClear();
});
afterEach(() => jest.useRealTimers());

test.each(['correct', 'incorrect'])(
  'the question timer stops after a %s answer and resets for the next word',
  async (answer) => {
    await render(practice());
    expect(
      screen.getByLabelText(
        'Time spent on this question: 0 minutes, 0 seconds',
      ),
    ).toBeOnTheScreen();
    await act(async () => {
      jest.advanceTimersByTime(2250);
    });
    expect(
      screen.getByLabelText(
        'Time spent on this question: 0 minutes, 2 seconds',
      ),
    ).toBeOnTheScreen();
    await fireEvent.press(
      screen.getByRole('button', {
        name:
          answer === 'correct' ? 'B. Able to be trusted' : 'A. Easy to forget',
      }),
    );
    await act(async () => {
      jest.advanceTimersByTime(500);
    });
    if (answer === 'correct') {
      expect(
        screen.getByLabelText(
          'Time spent on this question: 0 minutes, 2 seconds',
        ),
      ).toBeOnTheScreen();
      await advance();
    } else {
      await act(async () => {
        jest.advanceTimersByTime(5000);
      });
      expect(screen.queryByLabelText(/Time spent on this question/)).toBeNull();
      await fireEvent.press(
        screen.getByRole('button', { name: 'Skip · Next word' }),
      );
    }
    expect(screen.getByText('Word 2 of 2')).toBeOnTheScreen();
    expect(
      screen.getByLabelText(
        'Time spent on this question: 0 minutes, 0 seconds',
      ),
    ).toBeOnTheScreen();
  },
);

test('the timer preserves elapsed time while Common is hidden and formats minutes', async () => {
  const view = await render(practice());
  await act(async () => {
    jest.advanceTimersByTime(1500);
  });
  await view.rerender(practice(false));
  await act(async () => {
    jest.advanceTimersByTime(10000);
  });
  expect(
    screen.getByLabelText('Time spent on this question: 0 minutes, 1 second'),
  ).toBeOnTheScreen();
  await view.rerender(practice());
  await act(async () => {
    jest.advanceTimersByTime(59500);
  });
  expect(
    screen.getByLabelText('Time spent on this question: 1 minute, 1 second'),
  ).toBeOnTheScreen();
  expect(
    screen.getByLabelText('Time spent on this question: 1 minute, 1 second'),
  ).toBeOnTheScreen();
});

test('shows the safe generation failure message instead of a generic load error', async () => {
  loadMock.mockRejectedValueOnce(
    new CommonWordsError(
      'Could not prepare new words. Please try again shortly.',
    ),
  );
  await render(practice());
  expect(screen.getByRole('alert')).toHaveTextContent(
    'Could not prepare new words. Please try again shortly.',
  );
});

test('Vocab remains the default and switching tabs preserves search inputs and quiz progress', async () => {
  await render(<AddWordScreen />);
  expect(loadMock).not.toHaveBeenCalled();
  await fireEvent.changeText(
    screen.getByPlaceholderText('Enter a word, e.g. create'),
    'create',
  );
  await fireEvent.press(screen.getByRole('tab', { name: 'Common' }));
  expect(screen.getByRole('tab', { name: 'Common' })).toBeSelected();
  expect(screen.queryByPlaceholderText('Enter a word, e.g. create')).toBeNull();
  expect(screen.getAllByRole('button')).toHaveLength(4);
  await fireEvent.press(
    screen.getByRole('button', { name: 'B. Able to be trusted' }),
  );
  await fireEvent.press(screen.getByRole('tab', { name: 'Vocab' }));
  await advance();
  expect(
    screen.getByPlaceholderText('Enter a word, e.g. create'),
  ).toHaveDisplayValue('create');
  await fireEvent.press(screen.getByRole('tab', { name: 'Common' }));
  expect(screen.getByText('Word 1 of 2')).toBeOnTheScreen();
  expect(
    screen.getByText('✓ Correct! Moving to the next word…'),
  ).toBeOnTheScreen();
  await advance();
  expect(screen.getByText('Word 2 of 2')).toBeOnTheScreen();
  expect(loadMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).not.toHaveBeenCalled();
});

test('shows a loading state until the question source resolves', async () => {
  let resolve!: (items: readonly CommonWordQuestion[]) => void;
  loadMock.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  await render(practice());
  expect(screen.getByLabelText('Loading common words')).toBeBusy();
  expect(screen.queryAllByRole('button')).toHaveLength(0);
  await act(async () => {
    resolve(questions);
  });
  expect(screen.queryByLabelText('Loading common words')).toBeNull();
  expect(screen.getAllByRole('button')).toHaveLength(4);
});

test('correct answers lock all choices, advance automatically, and count each answer once', async () => {
  await render(practice());
  const answer = screen.getByRole('button', { name: 'B. Able to be trusted' });
  await fireEvent.press(answer);
  expect(
    screen.getByText('✓ Correct! Moving to the next word…'),
  ).toBeOnTheScreen();
  for (const choice of screen.getAllByRole('button'))
    expect(choice).toBeDisabled();
  await fireEvent.press(answer);
  await advance();
  expect(screen.getByText('Word 2 of 2')).toBeOnTheScreen();
  await fireEvent.press(
    screen.getByRole('button', { name: 'A. Ready and excited' }),
  );
  await advance();
  expect(screen.getByText('2 correct · 0 words saved')).toBeOnTheScreen();
  expect(fetchMock).not.toHaveBeenCalled();
});

test('a missed answer reveals the meaning and example, and Skip never saves', async () => {
  await render(practice());
  await fireEvent.press(
    screen.getByRole('button', { name: 'A. Easy to forget' }),
  );
  expect(screen.getByText('CORRECT ANSWER')).toBeOnTheScreen();
  expect(screen.getByText('adjective · Able to be trusted')).toBeOnTheScreen();
  expect(screen.getByText('Your answer: Easy to forget')).toBeOnTheScreen();
  expect(screen.getByText('“She is a reliable colleague.”')).toBeOnTheScreen();
  await advance();
  expect(screen.getByText('Word 1 of 2')).toBeOnTheScreen();
  await fireEvent.press(
    screen.getByRole('button', { name: 'Skip · Next word' }),
  );
  expect(screen.getByText('Word 2 of 2')).toBeOnTheScreen();
  expect(fetchMock).not.toHaveBeenCalled();
});

test('saving posts the revealed word once, blocks Skip while pending, and shows confirmation before continuing', async () => {
  let resolve!: (value: Response) => void;
  fetchMock.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  await render(practice());
  await fireEvent.press(
    screen.getByRole('button', { name: 'A. Easy to forget' }),
  );
  await fireEvent.press(screen.getByRole('button', { name: 'Save word' }));
  expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
  expect(
    screen.getByRole('button', { name: 'Skip · Next word' }),
  ).toBeDisabled();
  await fireEvent.press(screen.getByRole('button', { name: 'Saving…' }));
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith('/words', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      word: 'reliable',
      english_explanation: questions[0].explanation,
      example_sentence: questions[0].example,
    }),
  });
  await act(async () => {
    resolve(response());
  });
  expect(screen.getByText('✓ Word saved to your bank')).toBeOnTheScreen();
  expect(onSaved).toHaveBeenCalledWith('reliable');
  await advance();
  expect(screen.getByText('Word 1 of 2')).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole('button', { name: 'Next word' }));
  await fireEvent.press(
    screen.getByRole('button', { name: 'A. Ready and excited' }),
  );
  await advance();
  expect(screen.getByText('1 correct · 1 word saved')).toBeOnTheScreen();
  await fireEvent.press(
    screen.getByRole('button', { name: 'Practise more words' }),
  );
  expect(screen.getByText('Word 1 of 2')).toBeOnTheScreen();
  expect(screen.getAllByRole('button')).toHaveLength(4);
  expect(loadMock).toHaveBeenCalledTimes(2);
  expect(loadMock.mock.calls[1][0]).toEqual(['reliable', 'eager']);
});

test.each(['network', 'server'])(
  'save %s failure stays on the revealed word and supports retry',
  async (failure) => {
    if (failure === 'network')
      fetchMock.mockRejectedValueOnce(new Error('offline'));
    else fetchMock.mockResolvedValueOnce(response(503));
    await render(practice());
    await fireEvent.press(
      screen.getByRole('button', { name: 'A. Easy to forget' }),
    );
    await fireEvent.press(screen.getByRole('button', { name: 'Save word' }));
    expect(screen.getByRole('alert')).toHaveTextContent(
      /Could not save|connection|offline/i,
    );
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByText('CORRECT ANSWER')).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole('button', { name: 'Retry save' }));
    expect(screen.getByText('✓ Word saved to your bank')).toBeOnTheScreen();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  },
);

test.each(['known', 'conflict'])(
  'already saved words (%s) show an honest confirmation and do not increase saved counts',
  async (kind) => {
    fetchMock.mockResolvedValue(response(409));
    await render(practice(true, kind === 'known' ? ['reliable'] : []));
    await fireEvent.press(
      screen.getByRole('button', { name: 'A. Easy to forget' }),
    );
    await fireEvent.press(
      screen.getByRole('button', {
        name: kind === 'known' ? 'Already saved · Continue' : 'Save word',
      }),
    );
    expect(screen.getByText('✓ Already in your word bank')).toBeOnTheScreen();
    expect(fetchMock).toHaveBeenCalledTimes(kind === 'known' ? 0 : 1);
    await fireEvent.press(screen.getByRole('button', { name: 'Next word' }));
    await fireEvent.press(
      screen.getByRole('button', { name: 'B. Quiet and tired' }),
    );
    await fireEvent.press(
      screen.getByRole('button', { name: 'Skip · Next word' }),
    );
    expect(screen.getByText('0 correct · 0 words saved')).toBeOnTheScreen();
    await fireEvent.press(
      screen.getByRole('button', { name: 'Back to Vocab' }),
    );
    expect(onBackToVocab).toHaveBeenCalledTimes(1);
  },
);

test('question loading failures and an empty bank provide retry and a route back to Vocab', async () => {
  loadMock.mockRejectedValueOnce(new Error('failed')).mockResolvedValueOnce([]);
  await render(practice());
  expect(screen.getByRole('alert')).toHaveTextContent(/Could not load words/);
  await fireEvent.press(screen.getByRole('button', { name: 'Try again' }));
  expect(screen.getByText('No common words available')).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole('button', { name: 'Back to Vocab' }));
  expect(onBackToVocab).toHaveBeenCalledTimes(1);
  await fireEvent.press(screen.getByRole('button', { name: 'Try again' }));
  expect(screen.getByText('Word 1 of 2')).toBeOnTheScreen();
});

test('late question loads are discarded after the Common tab is hidden', async () => {
  let resolve!: (items: readonly CommonWordQuestion[]) => void;
  loadMock.mockReturnValueOnce(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const view = await render(practice());
  await view.rerender(practice(false));
  expect(loadMock.mock.calls[0][1]?.aborted).toBe(true);
  await act(async () => {
    resolve(questions);
  });
  expect(screen.queryByText('Word 1 of 2')).toBeNull();
  await view.rerender(practice());
  expect(screen.getByText('Word 1 of 2')).toBeOnTheScreen();
});
