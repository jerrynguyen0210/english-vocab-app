import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const batchId = '00000000-0000-0000-0000-000000000001';
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
    poll: async () => {
      await new Promise((resolve) => setImmediate(resolve));
      for (const [key, { callback, delay }] of [...timers.entries()])
        if (delay === 3000) {
          timers.delete(key);
          callback();
        }
    },
    expire: () => {
      for (const { callback, delay } of [...timers.values()])
        if (delay === 300000) callback();
    },
  };
}

test('starts a resumable batch and accepts answer-free questions', async () => {
  let calls = 0;
  const { loadCommonWords } = services(async (path, options, timeoutMs) => {
    assert.equal(timeoutMs, undefined);
    calls++;
    assert.equal(path, '/common-words/batches');
    assert.equal(options.method, 'POST');
    return Response.json({
      id: batchId,
      status: 'ready',
      questions: [question],
    });
  });
  assert.deepEqual(await loadCommonWords(), [question]);
  assert.equal(calls, 1);
});

test('completion returns no questions and performs no polling', async () => {
  assert.equal(
    (
      await services(async () =>
        Response.json({ id: batchId, status: 'complete', questions: [] }),
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
  await assert.rejects(api.loadCommonWords(), /Could not check/);
  assert.equal(calls, 1);
});

for (const invalid of [
  null,
  {},
  { status: 'unknown', questions: [] },
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
      services(async () =>
        Response.json(
          invalid && typeof invalid === 'object'
            ? { id: batchId, ...invalid }
            : invalid,
        ),
      ).loadCommonWords(),
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
      services(async () =>
        Response.json(
          invalid && typeof invalid === 'object'
            ? { id: batchId, ...invalid }
            : invalid,
        ),
      ).answerCommonQuestion('q1', 0),
      /invalid answer/,
    );
  });
}

test('polls the same batch until ready without repeating POST', async () => {
  const calls = [];
  const api = services(async (path, options) => {
    calls.push([path, options.method]);
    return Response.json({
      id: batchId,
      status:
        calls.length === 1
          ? 'pending'
          : calls.length === 2
            ? 'generating'
            : 'ready',
      questions: calls.length === 3 ? [question] : [],
    });
  });
  const pending = api.loadCommonWords();
  await api.poll();
  await api.poll();
  assert.deepEqual(await pending, [question]);
  assert.deepEqual(calls, [
    ['/common-words/batches', 'POST'],
    [`/common-words/batches/${batchId}`, undefined],
    [`/common-words/batches/${batchId}`, undefined],
  ]);
});

test('cancelling a polling wait stops further status requests', async () => {
  let calls = 0;
  const api = services(async () => {
    calls++;
    return Response.json({ id: batchId, status: 'pending', questions: [] });
  });
  const controller = new AbortController();
  const pending = api.loadCommonWords(controller.signal);
  await new Promise((resolve) => setImmediate(resolve));
  controller.abort();
  await assert.rejects(pending, /cancelled/);
  await api.poll();
  assert.equal(calls, 1);
});

test('failed jobs stop polling and offer an explicit retry', async () => {
  const api = services(async () =>
    Response.json({ id: batchId, status: 'failed', questions: [] }),
  );
  await assert.rejects(api.loadCommonWords(), /preparation failed/);
});

test('timeout discards late results; next load resumes the saved batch', async () => {
  let finish;
  let calls = 0;
  const api = services(async () => {
    calls++;
    if (calls === 1)
      return new Promise((resolve) => {
        finish = resolve;
      });
    return Response.json({
      id: batchId,
      status: 'ready',
      questions: [question],
    });
  });
  const pending = api.loadCommonWords();
  api.expire();
  await assert.rejects(pending, /Check again/);
  finish(
    Response.json({ id: batchId, status: 'ready', questions: [question] }),
  );
  assert.deepEqual(await api.loadCommonWords(), [question]);
});
