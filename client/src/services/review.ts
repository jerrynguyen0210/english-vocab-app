export type ReviewSource = 'time' | 'recall' | 'topic';
export type ReviewPeriod = 'Yesterday' | 'Weekly' | 'Monthly';
export function reviewQuery(selection: {
  source?: string;
  period?: string;
  includeOverdue?: string;
  topic?: string;
}) {
  const query = new URLSearchParams({
    source: selection.source ?? 'recall',
    period: selection.period ?? 'Weekly',
    include_overdue: selection.includeOverdue ?? 'true',
  });
  if (selection.source === 'topic')
    query.set('topic', selection.topic?.trim() ?? '');
  return query.toString();
}

export type ReviewSummary = {
  saved_count: number;
  due_count: number;
  daily_remaining: number;
};
export type ReviewEmptyKind = 'empty_bank' | 'nothing_due' | 'no_matches';
export function reviewEmptyKind(
  summary: ReviewSummary,
  _matching = summary.due_count,
): ReviewEmptyKind {
  if (summary.saved_count === 0) return 'empty_bank';
  if (summary.due_count === 0) return 'nothing_due';
  return 'no_matches';
}
