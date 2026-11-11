export type ReviewSource = 'time' | 'recall' | 'topic';
export type ReviewPeriod = 'Yesterday' | 'Weekly' | 'Monthly';
export function reviewQuery(selection: {
  source?: string;
  period?: string;
  includeOverdue?: string;
}) {
  return new URLSearchParams({
    source: selection.source ?? 'recall',
    period: selection.period ?? 'Weekly',
    include_overdue: selection.includeOverdue ?? 'true',
  }).toString();
}

export type ReviewSummary = {
  saved_count: number;
  due_count: number;
  daily_remaining: number;
};
export type ReviewEmptyKind =
  'empty_bank' | 'nothing_due' | 'no_matches' | 'daily_limit';
export function reviewEmptyKind(
  summary: ReviewSummary,
  matching = summary.due_count,
): ReviewEmptyKind {
  if (summary.saved_count === 0) return 'empty_bank';
  if (matching > 0 && summary.daily_remaining === 0) return 'daily_limit';
  if (summary.due_count === 0) return 'nothing_due';
  if (summary.daily_remaining === 0) return 'daily_limit';
  return 'no_matches';
}
