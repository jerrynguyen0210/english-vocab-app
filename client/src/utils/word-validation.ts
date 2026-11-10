// Match the API's Unicode-character limits, measured before trimming.
export const wordLimits = {
  word: 200,
  english_explanation: 5000,
  example_sentence: 5000,
} as const;
export type WordField = keyof typeof wordLimits;
export type WordDraft = Record<WordField, string>;
export type WordErrors = Partial<Record<WordField, string>>;

export function validateWord(values: WordDraft): WordErrors {
  const errors: WordErrors = {};
  if (!values.word.normalize('NFKC').trim()) errors.word = 'Word is required.';
  if (!values.english_explanation.normalize('NFKC').trim())
    errors.english_explanation = 'English explanation is required.';
  for (const field of Object.keys(wordLimits) as WordField[]) {
    if (Array.from(values[field]).length > wordLimits[field])
      errors[field] =
        `Use ${wordLimits[field].toLocaleString('en-US')} characters or fewer.`;
  }
  return errors;
}

export function wordPayload(values: WordDraft) {
  return {
    word: values.word.trim(),
    english_explanation: values.english_explanation.trim(),
    example_sentence: values.example_sentence.trim() || null,
  };
}
