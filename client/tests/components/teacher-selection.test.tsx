import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import { TeacherSelection } from '@/components/teacher-selection';
import { TeacherSelectionProvider } from '@/context/teacher-selection';
import { authenticatedFetch } from '@/services/auth';

const fetchMock = jest.mocked(authenticatedFetch);
const options = {
  teachers: [
    {
      id: 'teacher-01',
      name: 'Emma Wilson',
      model: 'openai/gpt-oss-20b',
    },
    {
      id: 'teacher-02',
      name: 'James Bennett',
      model: 'openai/gpt-oss-120b',
    },
    {
      id: 'teacher-03',
      name: 'Phuoc Ba',
      model: 'tencent/hy4-flash',
    },
  ],
  selected_teacher_id: 'teacher-01',
};
const reply = (body: unknown, status = 200) =>
  Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
const tree = (session = 0, page = 0) => (
  <TeacherSelectionProvider key={session}>
    <TeacherSelection key={page} />
  </TeacherSelectionProvider>
);
const open = async () =>
  fireEvent.press(
    await screen.findByRole('button', {
      name: 'Teacher name: Emma Wilson',
    }),
  );

beforeEach(() => fetchMock.mockReset());

test('shows the backend empty directory and disables selection', async () => {
  fetchMock.mockImplementation(() =>
    reply({ teachers: [], selected_teacher_id: null }),
  );
  await render(tree());
  expect(
    await screen.findByRole('button', {
      name: 'Teacher name: No teachers available yet',
    }),
  ).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledWith(
    '/teachers',
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
});

test.each(options.teachers.slice(1))(
  'only selects $name after a confirmed save',
  async (teacher) => {
    let finishSave!: (response: Response) => void;
    fetchMock
      .mockImplementationOnce(() => reply(options))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishSave = resolve;
          }),
      );
    await render(tree());
    await open();
    await fireEvent.press(screen.getByRole('button', { name: teacher.name }));
    expect(
      screen.getByRole('button', { name: 'Teacher name: Emma Wilson' }),
    ).toBeDisabled();
    expect(screen.getByRole('button', { name: teacher.name })).toBeDisabled();
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/teachers/selection',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ teacher_id: teacher.id }),
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    await act(async () => finishSave(await reply({ teacher_id: teacher.id })));
    expect(
      await screen.findByRole('button', {
        name: `Teacher name: ${teacher.name}`,
      }),
    ).toBeEnabled();
    expect(screen.queryByRole('button', { name: teacher.name })).toBeNull();
  },
);

test.each([422, 500])(
  'a %s save response preserves the confirmed selection and allows retry',
  async (status) => {
    fetchMock
      .mockImplementationOnce(() => reply(options))
      .mockImplementationOnce(() => reply({ detail: 'server text' }, status))
      .mockImplementationOnce(() => reply({ teacher_id: 'teacher-02' }));
    await render(tree());
    await open();
    await fireEvent.press(
      screen.getByRole('button', { name: 'James Bennett' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unable to save your teacher. Please try again.',
    );
    expect(
      screen.getByRole('button', { name: 'Teacher name: Emma Wilson' }),
    ).toBeEnabled();
    await fireEvent.press(
      screen.getByRole('button', { name: 'James Bennett' }),
    );
    await screen.findByRole('button', {
      name: 'Teacher name: James Bennett',
    });
  },
);

test('retries a failed directory load and rejects malformed data', async () => {
  fetchMock
    .mockRejectedValueOnce(new Error('Network failure'))
    .mockImplementationOnce(() =>
      reply({ teachers: [null], selected_teacher_id: null }),
    )
    .mockImplementationOnce(() => reply(options));
  await render(tree());
  await screen.findByRole('alert');
  expect(
    screen.getByRole('button', { name: 'Teacher name: Teachers unavailable' }),
  ).toBeDisabled();
  await fireEvent.press(
    screen.getByRole('button', { name: 'Retry loading teachers' }),
  );
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  await screen.findByRole('alert');
  await fireEvent.press(
    screen.getByRole('button', { name: 'Retry loading teachers' }),
  );
  await screen.findByRole('button', {
    name: 'Teacher name: Emma Wilson',
  });
});

test('caches across screen remounts and reloads for a new session', async () => {
  fetchMock
    .mockImplementationOnce(() => reply(options))
    .mockImplementationOnce(() =>
      reply({ ...options, selected_teacher_id: 'teacher-03' }),
    );
  const view = await render(tree());
  await screen.findByRole('button', {
    name: 'Teacher name: Emma Wilson',
  });
  await view.rerender(tree(0, 1));
  expect(
    screen.getByRole('button', { name: 'Teacher name: Emma Wilson' }),
  ).toBeOnTheScreen();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  await view.rerender(tree(1, 0));
  await screen.findByRole('button', {
    name: 'Teacher name: Phuoc Ba',
  });
  expect(fetchMock).toHaveBeenCalledTimes(2);
});
