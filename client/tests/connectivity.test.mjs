import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

function harness(fetch) {
  const exports = {};
  const { outputText } = ts.transpileModule(
    readFileSync(
      new URL('../src/services/connectivity.ts', import.meta.url),
      'utf8',
    ),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    },
  );
  runInNewContext(outputText, {
    exports,
    fetch,
    AbortController,
    setTimeout,
    clearTimeout,
  });
  return exports;
}

test('offline failures display connectivity state and never replay a write', async () => {
  let calls = 0;
  const api = harness(async () => {
    calls++;
    throw new TypeError('Failed to fetch');
  });
  await assert.rejects(
    api.reachableFetch('https://example.test', {
      method: 'POST',
      body: 'typed answer',
    }),
    api.ConnectivityError,
  );
  assert.equal(calls, 1);
  assert.match(
    api.connectionMessage(new api.ConnectivityError(), 'fallback'),
    /offline or the server is unreachable/,
  );
});

test('stalled requests time out, abort, and allow a manual retry', async () => {
  let signal;
  let calls = 0;
  const api = harness(async (_, init) => {
    signal = init.signal;
    if (++calls === 1) return new Promise(() => {});
    return new Response('ok');
  });
  await assert.rejects(
    api.reachableFetch('https://example.test', {}, 5),
    api.ConnectivityError,
  );
  assert.equal(signal.aborted, true);
  assert.equal((await api.reachableFetch('https://example.test')).status, 200);
});

test('unreachable gateway states differ from validation and session failures', async () => {
  for (const status of [502, 503, 504]) {
    const api = harness(async () => new Response('', { status }));
    await assert.rejects(
      api.reachableFetch('https://example.test'),
      api.ConnectivityError,
    );
  }
  for (const status of [401, 409, 422, 429, 500]) {
    const api = harness(async () => new Response('', { status }));
    assert.equal(
      (await api.reachableFetch('https://example.test')).status,
      status,
    );
  }
});
