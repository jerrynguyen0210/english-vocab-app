export type ReviewSource = 'time' | 'recall' | 'topic';
export type ReviewPeriod = 'Yesterday' | 'Weekly' | 'Monthly';
export function reviewQuery(selection: {
  source?: string;
  period?: string;
  topic?: string;
  includeOverdue?: string;
}) {
  return new URLSearchParams({
    source: selection.source ?? 'recall',
    period: selection.period ?? 'Weekly',
    topic: selection.topic ?? '',
    include_overdue: selection.includeOverdue ?? 'true',
  }).toString();
}
