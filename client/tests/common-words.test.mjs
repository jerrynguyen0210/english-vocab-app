import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const question = {
  id: '19be59ac-9db2-405f-a789-1e7509b90cd8',
  word: 'reliable',
  partOfSpeech: 'adjective',
  explanation: 'Able to be trusted.',
  example: 'She is a reliable colleague.',
  choices: [
    'Easy to forget',
    'Able to be trusted',
    'Very expensive',
    'Difficult to use',
  ],
  correctIndex: 1,
};
function loader(fetch) {
  const exports = {};
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
      setTimeout: (callback) => setImmediate(callback),
      clearTimeout: clearImmediate,
    },
  );
  return exports.loadCommonWords;
}
const response = (body, status = 200) => Response.json(body, { status });

test('Common fetch polls a durable job and keeps exclusions and cancellation on every request', async () => {
  const calls = [];
  const controller = new AbortController();
  const load = loader(async (path, options) => {
    calls.push({ path, options });
    return calls.length < 3
      ? response({ status: 'pending', questions: [] }, 202)
      : response({ status: 'ready', questions: [question] });
  });
  assert.deepEqual(await load(['previous-id'], controller.signal), [question]);
  assert.equal(calls.length, 3);
  for (const { path, options } of calls) {
    assert.equal(path, '/common-words/batch');
    assert.equal(options.method, 'POST');
    assert.deepEqual(JSON.parse(options.body), {
      exclude_ids: ['previous-id'],
    });
    assert.equal(options.signal, controller.signal);
  }
});

test('failed generation is surfaced without sample fallback or repeated model requests', async () => {
  let calls = 0;
  const load = loader(async () => {
    calls++;
    return response({ status: 'failed', questions: [] });
  });
  await assert.rejects(load(), /Could not prepare new words/);
  assert.equal(calls, 1);
});

test('network failure and non-successful responses are not replayed automatically', async () => {
  for (const failure of [
    new Error('network failure'),
    response({}, 401),
    response({}, 422),
  ]) {
    let calls = 0;
    const load = loader(async () => {
      calls++;
      if (failure instanceof Error) throw failure;
      return failure;
    });
    await assert.rejects(load());
    assert.equal(calls, 1);
  }
});

test('hiding the screen cancels pending polling', async () => {
  let calls = 0;
  const controller = new AbortController();
  const load = loader(async () => {
    calls++;
    queueMicrotask(() => controller.abort());
    return response({ status: 'pending' }, 202);
  });
  await assert.rejects(load([], controller.signal), /cancelled/);
  assert.equal(calls, 1);
});

test('an already aborted screen makes no API call', async () => {
  const controller = new AbortController();
  controller.abort();
  const load = loader(() => {
    throw new Error('Must not call');
  });
  await assert.rejects(load([], controller.signal), /cancelled/);
});

test('pending generation has a bounded wait and can be retried by the user', async () => {
  let calls = 0;
  const load = loader(async () => {
    calls++;
    return response({ status: 'pending' }, 202);
  });
  await assert.rejects(load(), /still being prepared/);
  assert.equal(calls, 240);
});

for (const invalid of [
  null,
  {},
  { status: 'unknown' },
  { status: 'ready' },
  { status: 'ready', questions: [{ ...question, correctIndex: 4 }] },
  { status: 'ready', questions: [{ ...question, correctIndex: true }] },
  {
    status: 'ready',
    questions: [{ ...question, choices: ['One', 'Two', 'Three'] }],
  },
  {
    status: 'ready',
    questions: [{ ...question, choices: ['One', 'Two', 'Three', ' one '] }],
  },
  { status: 'ready', questions: [{ ...question, explanation: '' }] },
  { status: 'ready', questions: [question, question] },
  {
    status: 'ready',
    questions: Array.from({ length: 11 }, (_, i) => ({
      ...question,
      id: String(i),
    })),
  },
]) {
  test(`rejects malformed Common response: ${JSON.stringify(invalid).slice(0, 110)}`, async () => {
    await assert.rejects(loader(async () => response(invalid))(), /invalid/i);
  });
}

test('limits exclusions to the latest 1000 loaded questions', async () => {
  let body;
  const load = loader(async (_, options) => {
    body = JSON.parse(options.body);
    return response({ status: 'ready', questions: [] });
  });
  await load(Array.from({ length: 1005 }, (_, i) => String(i)));
  assert.equal(body.exclude_ids.length, 1000);
  assert.equal(body.exclude_ids[0], '5');
});
