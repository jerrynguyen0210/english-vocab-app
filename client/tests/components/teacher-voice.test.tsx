import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import * as Speech from 'expo-speech';
import { PronunciationButton } from '@/components/pronunciation-button';
import { TeacherSelection } from '@/components/teacher-selection';
import { TeacherSelectionProvider } from '@/context/teacher-selection';
import { authenticatedFetch } from '@/services/auth';
import { selectPronunciationVoice } from '@/services/pronunciation-voice';

jest.mock('expo-speech', () => ({
  VoiceQuality: { Default: 'Default' },
  speak: jest.fn(),
  stop: jest.fn(() => Promise.resolve()),
  getAvailableVoicesAsync: jest.fn(),
}));
const voices = [
  {
    identifier: 'device-samantha',
    name: 'Samantha',
    language: 'en-US',
    quality: Speech.VoiceQuality.Default,
  },
  {
    identifier: 'device-daniel',
    name: 'Daniel',
    language: 'en-GB',
    quality: Speech.VoiceQuality.Default,
  },
  {
    identifier: 'device-fiona',
    name: 'Fiona',
    language: 'en-GB',
    quality: Speech.VoiceQuality.Default,
  },
];
const teachers = [
  { id: 'emma', name: 'Emma', model: 'model-a', gender: 'female' },
  { id: 'james', name: 'James', model: 'model-b', gender: 'male' },
];
const reply = (body: unknown) =>
  Promise.resolve({ ok: true, json: async () => body } as Response);
const tree = (autoSpeak = false, active = true) => (
  <TeacherSelectionProvider>
    <TeacherSelection />
    <PronunciationButton word="journey" active={active} autoSpeak={autoSpeak} />
  </TeacherSelectionProvider>
);
const play = () =>
  fireEvent.press(
    screen.getByRole('button', { name: 'Play pronunciation of journey' }),
  );

beforeEach(() => {
  jest.mocked(Speech.speak).mockReset();
  jest.mocked(Speech.stop).mockClear();
  jest
    .mocked(Speech.getAvailableVoicesAsync)
    .mockReset()
    .mockResolvedValue(voices);
  jest
    .mocked(authenticatedFetch)
    .mockReset()
    .mockImplementation((path) =>
      reply(
        path === '/teachers'
          ? { teachers, selected_teacher_id: 'emma' }
          : { teacher_id: 'james' },
      ),
    );
});

test('matches gender and prefers British English without treating female as male', () => {
  expect(selectPronunciationVoice(voices, 'female')?.identifier).toBe(
    'device-fiona',
  );
  expect(selectPronunciationVoice(voices, 'male')?.identifier).toBe(
    'device-daniel',
  );
  expect(selectPronunciationVoice([voices[0]], 'female')?.identifier).toBe(
    'device-samantha',
  );
  expect(
    selectPronunciationVoice(
      [{ ...voices[0], name: 'English female', identifier: 'opaque' }],
      'male',
    ),
  ).toBeUndefined();
  expect(
    selectPronunciationVoice([{ ...voices[1], language: 'de-DE' }], 'male'),
  ).toBeUndefined();
});

test('manual pronunciation follows the confirmed selected teacher and displays gender', async () => {
  await render(tree());
  expect(screen.getByText('Gender: Female')).toBeOnTheScreen();
  await play();
  expect(Speech.speak).toHaveBeenCalledTimes(1);
  expect(Speech.speak).toHaveBeenLastCalledWith(
    'journey',
    expect.objectContaining({ voice: 'device-fiona', language: 'en-GB' }),
  );
  await act(async () => {
    (jest.mocked(Speech.speak).mock.calls[0][1]?.onDone as () => void)();
  });
  await fireEvent.press(
    screen.getByRole('button', { name: 'Teacher name: Emma' }),
  );
  await fireEvent.press(screen.getByRole('button', { name: 'James' }));
  expect(screen.getByText('Gender: Male')).toBeOnTheScreen();
  await play();
  expect(Speech.speak).toHaveBeenLastCalledWith(
    'journey',
    expect.objectContaining({ voice: 'device-daniel' }),
  );
});

test.each(['empty', 'failure'])(
  'voice discovery %s falls back to default pronunciation',
  async (mode) => {
    if (mode === 'empty')
      jest.mocked(Speech.getAvailableVoicesAsync).mockResolvedValue([]);
    else
      jest
        .mocked(Speech.getAvailableVoicesAsync)
        .mockRejectedValue(new Error('Unavailable'));
    await render(tree());
    await play();
    expect(Speech.speak).toHaveBeenCalledWith(
      'journey',
      expect.objectContaining({ language: 'en-GB' }),
    );
    expect(jest.mocked(Speech.speak).mock.calls[0][1]).not.toHaveProperty(
      'voice',
    );
  },
);

test('automatic pronunciation uses the selected gender and ignores stale voice lookup after hiding', async () => {
  const view = await render(tree(true));
  expect(Speech.speak).toHaveBeenLastCalledWith(
    'journey',
    expect.objectContaining({ voice: 'device-fiona' }),
  );
  await view.rerender(tree(true, false));
  let finish!: (result: Speech.Voice[]) => void;
  jest.mocked(Speech.getAvailableVoicesAsync).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  jest.mocked(Speech.speak).mockClear();
  await view.rerender(tree(true));
  await view.rerender(tree(true, false));
  await act(async () => finish(voices));
  expect(Speech.speak).not.toHaveBeenCalled();
});
