// Local-only preparation data until the new review sources are integrated.
export type ReviewSource = 'time' | 'recall' | 'topic';
export type ReviewPeriod = 'Yesterday' | 'Weekly' | 'Monthly';
const vocabulary = [
  [
    'resilience',
    'The ability to recover after difficulties.',
    'Despite the setbacks, her _____ helped her try again.',
    'Workplace communication',
  ],
  [
    'collaborate',
    'To work together towards a shared goal.',
    'Our teams _____ on every new project.',
    'Workplace communication',
  ],
  [
    'concise',
    'Expressing information clearly in few words.',
    'Keep your update clear and _____.',
    'Workplace communication',
  ],
  [
    'feedback',
    'Advice or comments about how something can improve.',
    'She asked for _____ after the presentation.',
    'Workplace communication',
  ],
  [
    'initiative',
    'The ability to act without being told what to do.',
    'He showed _____ by solving the problem early.',
    'Workplace communication',
  ],
  [
    'negotiate',
    'To discuss something to reach an agreement.',
    'We need to _____ a suitable deadline.',
    'Workplace communication',
  ],
  [
    'clarify',
    'To make something easier to understand.',
    'Could you _____ the instructions?',
    'Workplace communication',
  ],
  [
    'consensus',
    'An agreement shared by a group.',
    'The team reached a _____ on the plan.',
    'Workplace communication',
  ],
  [
    'itinerary',
    'A plan describing the route or schedule of a journey.',
    'Our _____ includes three cities.',
    'Travel',
  ],
  [
    'destination',
    'The place someone is travelling to.',
    'Our final _____ is by the sea.',
    'Travel',
  ],
  [
    'nourish',
    'To provide what is needed to grow and stay healthy.',
    'Fresh vegetables help _____ the body.',
    'Wellbeing',
  ],
  [
    'tranquil',
    'Calm and peaceful.',
    'The garden was quiet and _____.',
    'Wellbeing',
  ],
];
export const reviewPreviewWords = vocabulary.map(
  ([word, explanation, sentence, topic], index) => ({
    word_id: `preview-${index}`,
    attempt_id: `preview-attempt-${index}`,
    word,
    english_explanation: explanation,
    example_sentence: sentence,
    topic,
    daysAgo: index < 4 ? 1 : index < 10 ? 4 : 20,
    overdue: index < 3,
  }),
);
export function selectPreviewWords(
  source: ReviewSource,
  period: ReviewPeriod,
  topic: string,
  includeOverdue: boolean,
) {
  return reviewPreviewWords.filter((word) => {
    if (source === 'topic')
      return (
        !!topic.trim() &&
        word.topic.toLowerCase().includes(topic.trim().toLowerCase())
      );
    if (source === 'recall') return includeOverdue || !word.overdue;
    return period === 'Yesterday'
      ? word.daysAgo === 1
      : word.daysAgo <= (period === 'Weekly' ? 7 : 30);
  });
}
