import React from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react-native';
import AddWordScreen from '@/app/(app)/add-word';
import ReviewPreparationScreen from '@/app/(app)/review-preparation';
import ReviewScreen from '@/app/(app)/review';
import { authenticatedFetch } from '@/services/auth';

const fetchMock = jest.mocked(authenticatedFetch);
const reply = (body: unknown, status = 200) =>
  Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
const entry = {
  word: 'written',
  part_of_speech: 'verb',
  verb_forms: ['V3'],
  english_explanation: 'Past participle of write.',
  example_sentence: null,
  saved: false,
};
const prompts = [1, 2].map((id) => ({
  word_id: `word-${id}`,
  attempt_id: `attempt-${id}`,
  review_token: `token-${id}`,
  english_explanation: 'A greeting',
  example_sentence: null,
  prompt_sentence: `Sentence ${id}: Say _____.`,
}));

beforeEach(() => fetchMock.mockReset());

test('searches word forms, saves the selected form, and prevents duplicate saves', async () => {
  fetchMock.mockImplementation((path) =>
    String(path).startsWith('/words/search?')
      ? reply([entry])
      : reply({ id: 'saved-word' }, 201),
  );
  await render(<AddWordScreen />);
  await fireEvent.changeText(
    screen.getByPlaceholderText('Enter a word, e.g. create'),
    ' write ',
  );
  await fireEvent.press(screen.getByRole('button', { name: 'Search' }));
  await screen.findByRole('button', { name: 'Save written' });
  const query = new URLSearchParams(
    String(fetchMock.mock.calls[0][0]).split('?')[1],
  );
  expect(query.get('q')).toBe('write');
  expect(query.getAll('forms')).toEqual(['V1', 'V2', 'V3']);
  await fireEvent.press(screen.getByRole('button', { name: 'Save written' }));
  await screen.findByRole('button', { name: 'Saved written' });
  expect(fetchMock).toHaveBeenLastCalledWith(
    '/words',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        word: entry.word,
        english_explanation: entry.english_explanation,
        example_sentence: entry.example_sentence,
      }),
    }),
  );
  await fireEvent.press(screen.getByRole('button', { name: 'Saved written' }));
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test('prepares time and SM-2 selections and keeps topic review unavailable', async () => {
  fetchMock.mockImplementation(() =>
    reply({
      count: 2,
      matching_count: 2,
      saved_count: 2,
      due_count: 2,
      daily_remaining: 20,
    }),
  );
  await render(<ReviewPreparationScreen />);
  await screen.findByLabelText('Start review · 2 words');
  expect(String(fetchMock.mock.calls[0][0])).toContain('source=time');
  await fireEvent.press(screen.getByRole('radio', { name: 'Yesterday' }));
  await waitFor(() =>
    expect(String(fetchMock.mock.lastCall?.[0])).toContain('period=Yesterday'),
  );
  await screen.findByLabelText('Start review · 2 words');
  await fireEvent.press(screen.getByText('SM-2 recall'));
  await waitFor(() =>
    expect(String(fetchMock.mock.lastCall?.[0])).toContain('source=recall'),
  );
  await fireEvent(
    screen.getByLabelText('Include overdue words'),
    'valueChange',
    false,
  );
  await waitFor(() =>
    expect(String(fetchMock.mock.lastCall?.[0])).toContain(
      'include_overdue=false',
    ),
  );
  await screen.findByLabelText('Start review · 2 words');
  const calls = fetchMock.mock.calls.length;
  await fireEvent.press(screen.getByText('By topic'));
  expect(screen.getByText('Topic search is coming later.')).toBeOnTheScreen();
  expect(screen.queryByLabelText('Start review · 2 words')).toBeNull();
  expect(
    screen.getByRole('button', { name: 'Topic review coming later' }),
  ).toBeDisabled();
  await screen.findByText('2 words in your word bank');
  expect(fetchMock).toHaveBeenCalledTimes(calls + 1);
  expect(fetchMock).toHaveBeenLastCalledWith('/reviews/summary');
  await fireEvent.changeText(
    screen.getByLabelText('Topic search'),
    'Workplace communication',
  );
  expect(screen.getByLabelText('Topic search')).toHaveDisplayValue(
    'Workplace communication',
  );
  expect(fetchMock).toHaveBeenCalledTimes(calls + 1);
});

test.each(['typing', 'choice'] as const)(
  '%s mode submits, shows both feedback results, and advances to completion',
  async (mode) => {
    fetchMock.mockImplementation((path, options) => {
      const url = String(path);
      if (url.startsWith('/reviews/session?')) return reply(prompts);
      if (url.endsWith('/choices')) {
        const prompt = prompts.find((p) => url.includes(p.word_id))!;
        return reply({
          ...prompt,
          choices: ['Hello', 'World', 'Goodbye', 'Welcome'],
        });
      }
      const body = JSON.parse(String(options?.body));
      return reply({
        result: body.typed_answer === 'Hello' ? 'correct' : 'incorrect',
        correct_word: 'Hello',
      });
    });
    await render(<ReviewScreen />);
    await screen.findByLabelText('Your answer');
    expect(screen.queryByText('Hello')).toBeNull();
    expect(screen.getByRole('button', { name: 'Check answer' })).toBeDisabled();
    if (mode === 'choice') {
      await fireEvent.press(
        screen.getByRole('radio', { name: 'Multiple choice' }),
      );
      await screen.findByRole('radio', { name: 'A. Hello' });
    }
    for (const [index, answer] of ['Hello', 'World'].entries()) {
      await screen.findByText(`Sentence ${index + 1}: Say _____.`);
      if (mode === 'typing')
        await fireEvent.changeText(
          screen.getByLabelText('Your answer'),
          answer,
        );
      else
        await fireEvent.press(
          await screen.findByRole('radio', {
            name: answer === 'Hello' ? 'A. Hello' : 'B. World',
          }),
        );
      if (mode === 'typing') {
        await fireEvent.press(
          screen.getByRole('button', { name: 'Check answer' }),
        );
      } else {
        expect(
          screen.queryByRole('button', { name: 'Check answer' }),
        ).toBeNull();
      }
      const feedback = await screen.findByTestId('review-feedback');
      expect(
        within(feedback).getByText(
          index === 0 ? 'Correct answer!' : 'Incorrect answer',
        ),
      ).toBeOnTheScreen();
      expect(within(feedback).getByText('Hello')).toBeOnTheScreen();
      if (index === 1)
        expect(within(feedback).getByText('World')).toBeOnTheScreen();
      const call = fetchMock.mock.calls.find(
        ([path]) => path === `/reviews/word-${index + 1}/answer`,
      )!;
      expect(JSON.parse(String(call[1]?.body))).toEqual(
        expect.objectContaining({
          attempt_id: `attempt-${index + 1}`,
          review_token: `token-${index + 1}`,
          typed_answer: answer,
          time_taken_ms: expect.any(Number),
        }),
      );
      await fireEvent.press(screen.getByRole('button', { name: 'Next word' }));
      expect(screen.queryByTestId('review-feedback')).toBeNull();
    }
    expect(
      await screen.findByText('You reviewed all 2 words.'),
    ).toBeOnTheScreen();
    expect(screen.getByText('1 of 2 answers correct.')).toBeOnTheScreen();
    expect(
      fetchMock.mock.calls.filter(([path]) => String(path).endsWith('/answer')),
    ).toHaveLength(2);
  },
);

test('retains a failed save for retry and marks a duplicate response as saved', async () => {
  fetchMock
    .mockResolvedValueOnce({ ok: true, json: async () => [entry] } as Response)
    .mockRejectedValueOnce(new Error('Network failure'))
    .mockImplementationOnce(() => reply({}, 409));
  await render(<AddWordScreen />);
  await fireEvent.changeText(
    screen.getByPlaceholderText('Enter a word, e.g. create'),
    'write',
  );
  await fireEvent.press(screen.getByRole('button', { name: 'Search' }));
  await fireEvent.press(
    await screen.findByRole('button', { name: 'Save written' }),
  );
  const retry = await screen.findByRole('button', { name: 'Try again' });
  expect(screen.queryByRole('button', { name: 'Saved written' })).toBeNull();
  await fireEvent.press(retry);
  expect(
    await screen.findByRole('button', { name: 'Saved written' }),
  ).toBeOnTheScreen();
});

test('retries an uncertain review submission with the same answer and attempt', async () => {
  fetchMock
    .mockImplementationOnce(() => reply(prompts))
    .mockRejectedValueOnce(new Error('Network failure'))
    .mockImplementationOnce(() =>
      reply({ result: 'correct', correct_word: 'Hello' }),
    );
  await render(<ReviewScreen />);
  await fireEvent.changeText(
    await screen.findByLabelText('Your answer'),
    ' Hello ',
  );
  await fireEvent.press(screen.getByRole('button', { name: 'Check answer' }));
  const retry = await screen.findByRole('button', { name: 'Retry submission' });
  expect(screen.getByLabelText('Your answer')).toHaveDisplayValue(' Hello ');
  expect(screen.getByLabelText('Your answer')).toHaveProp('editable', false);
  await fireEvent.press(retry);
  expect(await screen.findByTestId('review-feedback')).toBeOnTheScreen();
  expect(fetchMock.mock.calls[2]).toEqual(fetchMock.mock.calls[1]);
});
