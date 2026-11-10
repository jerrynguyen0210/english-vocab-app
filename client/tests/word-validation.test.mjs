import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  validateWord,
  wordPayload,
  wordLimits,
} from '../src/utils/word-validation.ts';

const valid = {
  word: 'resilience',
  english_explanation: 'Recovering from difficulty.',
  example_sentence: '',
};

test('required fields reject empty, whitespace, and compatibility whitespace', () => {
  for (const blank of ['', ' \n\t ', '\u3000', '\u00a0']) {
    const errors = validateWord({
      word: blank,
      english_explanation: blank,
      example_sentence: blank,
    });
    assert.ok(errors.word);
    assert.ok(errors.english_explanation);
    assert.equal(errors.example_sentence, undefined);
  }
});

test('limits accept their boundaries and reject oversized pasted text for every field', () => {
  for (const [field, limit] of Object.entries(wordLimits)) {
    assert.deepEqual(
      validateWord({ ...valid, [field]: 'a'.repeat(limit) }),
      {},
    );
    assert.ok(
      validateWord({ ...valid, [field]: 'a'.repeat(limit + 1) })[field],
    );
    assert.ok(
      validateWord({ ...valid, [field]: ' ' + 'a'.repeat(limit) })[field],
    );
    assert.deepEqual(
      validateWord({ ...valid, [field]: '🌱'.repeat(limit) }),
      {},
    );
  }
});

test('payload trims edges, preserves internal text, and omits blank optional text as null', () => {
  assert.deepEqual(
    wordPayload({
      word: '  resilient  ',
      english_explanation: '  Able to\nrecover.\t',
      example_sentence: '  She showed resilience.  ',
    }),
    {
      word: 'resilient',
      english_explanation: 'Able to\nrecover.',
      example_sentence: 'She showed resilience.',
    },
  );
  assert.equal(
    wordPayload({ ...valid, example_sentence: ' \n ' }).example_sentence,
    null,
  );
  assert.deepEqual(validateWord(valid), {});
});
