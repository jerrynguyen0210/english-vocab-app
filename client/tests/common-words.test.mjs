import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const question = {
  id: 'q1',
  word: 'reliable',
  ipa: null,
  partOfSpeech: 'adjective',
  explanation: 'Able to be trusted.',
  example: null,
  question: 'What does reliable mean?',
  choices: ['Trusted', 'Slow', 'Broken', 'Expensive'],
};
function services(fetch) {
  const exports = {};
  const timers = new Map();
  const source = readFileSync(
    new URL('../src/services/common-words.ts', import.meta.url),
    'utf8',
  );
  runInNewContext(
    ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText,
    {
      exports,
      require: () => ({ authenticatedFetch: fetch }),
      AbortController,
      setTimeout: (callback, delay) => {
        const key = {};
        timers.set(key, { callback, delay });
        return key;
      },
      clearTimeout: (key) => timers.delete(key),
    },
  );
  return {
    ...exports,
    expire: () => {
      for (const { callback } of timers.values()) callback();
    },
  };
}

test('one batch request sends no exclusions and accepts answer-free questions', async () => {
  let calls = 0;
  const { loadCommonWords } = services(async (path, options, timeoutMs) => {
    assert.equal(timeoutMs, 300000);
    calls++;
    assert.equal(path, '/common-words/batch');
    assert.equal(options.body, '{}');
    return Response.json({ status: 'ready', questions: [question] });
  });
  assert.deepEqual(await loadCommonWords(), [question]);
  assert.equal(calls, 1);
});

test('completion returns no questions and performs no polling', async () => {
  assert.equal(
    (
      await services(async () =>
        Response.json({ status: 'complete', questions: [] }),
      ).loadCommonWords()
    ).length,
    0,
  );
});

test('server failure offers retry without automatically repeating generation', async () => {
  let calls = 0;
  const api = services(async () => {
    calls++;
    return new Response('', { status: 503 });
  });
  await assert.rejects(api.loadCommonWords(), /Could not prepare/);
  assert.equal(calls, 1);
});

for (const invalid of [
  null,
  {},
  { status: 'pending', questions: [] },
  { status: 'ready', questions: [] },
  { status: 'complete', questions: [question] },
  { status: 'ready', questions: [{ ...question, correctIndex: 0 }] },
  { status: 'ready', questions: [{ ...question, question: '' }] },
  {
    status: 'ready',
    questions: [{ ...question, choices: ['one', 'two', 'three', ' ONE '] }],
  },
  { status: 'ready', questions: [question, question] },
  {
    status: 'ready',
    questions: Array.from({ length: 11 }, (_, i) => ({
      ...question,
      id: String(i),
    })),
  },
])
  test(`reject invalid batch ${JSON.stringify(invalid).slice(0, 80)}`, async () => {
    await assert.rejects(
      services(async () => Response.json(invalid)).loadCommonWords(),
      /invalid/,
    );
  });

test('cancelled requests never start generation', async () => {
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    services(() => {
      throw new Error('Must not fetch');
    }).loadCommonWords(controller.signal),
    /cancelled/,
  );
});

test('total generation deadline aborts a stalled request', async () => {
  let signal;
  const api = services(async (_, options) => {
    signal = options.signal;
    return new Promise(() => {});
  });
  const pending = api.loadCommonWords();
  api.expire();
  await assert.rejects(pending, /still being prepared/);
  assert.equal(signal.aborted, true);
});

test('answer submission sends the actual selected choice and trusts server grading', async () => {
  const api = services(async (path, options) => {
    assert.equal(path, '/common-words/questions/q1/answer');
    assert.deepEqual(JSON.parse(options.body), { selected_index: 2 });
    return Response.json({
      result: 'incorrect',
      correctIndex: 0,
      explanation: 'Trusted',
    });
  });
  assert.equal((await api.answerCommonQuestion('q1', 2)).result, 'incorrect');
});

for (const invalid of [
  { result: 'correct', correctIndex: 2, explanation: 'Trusted' },
  { result: 'incorrect', correctIndex: 0, explanation: 'Trusted' },
  { result: 'correct', correctIndex: true },
  {},
]) {
  test('rejects inconsistent or malformed answer feedback', async () => {
    await assert.rejects(
      services(async () => Response.json(invalid)).answerCommonQuestion(
        'q1',
        0,
      ),
      /invalid answer/,
    );
  });
}
