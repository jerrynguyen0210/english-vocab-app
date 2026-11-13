import React from 'react';
import { render, screen } from '@testing-library/react-native';
import { LearningStatistics } from '@/components/learning-statistics';
import HomeScreen from '@/app/(app)/index';
import { authenticatedFetch } from '@/services/auth';

const summary = {
  due_count: 19,
  saved_count: 24,
  learned_count: 8,
  total_count: 30,
  daily_remaining: 50,
};

test('shows actual counts with proportional column heights', async () => {
  await render(<LearningStatistics summary={summary} />);
  expect(
    screen.getByLabelText(
      /Words due today: 19. Saved: 24. Learned: 8. Total: 30/,
    ),
  ).toBeTruthy();
  expect(screen.getByTestId('bar-Saved')).toHaveStyle({ height: 135 });
  expect(screen.getByTestId('bar-Learned')).toHaveStyle({ height: 45 });
});

test('keeps zero counts at zero height with a valid axis', async () => {
  await render(
    <LearningStatistics
      summary={{
        ...summary,
        due_count: 0,
        saved_count: 0,
        learned_count: 0,
        total_count: 0,
      }}
    />,
  );
  expect(screen.getByTestId('bar-Total')).toHaveStyle({ height: 0 });
  expect(screen.getByText('4')).toBeTruthy();
});

test('loads home statistics even when the saved bank is empty', async () => {
  jest.mocked(authenticatedFetch).mockResolvedValueOnce({
    ok: true,
    json: async () => ({ ...summary, due_count: 0, saved_count: 0 }),
  } as Response);
  await render(<HomeScreen />);
  await screen.findByLabelText(
    /Words due today: 0. Saved: 0. Learned: 8. Total: 30/,
  );
  expect(authenticatedFetch).toHaveBeenCalledWith('/reviews/summary');
});
