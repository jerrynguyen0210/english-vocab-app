import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

// Exercise the production service and platform adapters without loading native
// binaries in Node. Only fetch and the device's SecureStore bridge are replaced.
function loadModule(relativePath, dependencies) {
  const source = readFileSync(new URL(relativePath, import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const exports = {};
  runInNewContext(outputText, {
    exports,
    require: (id) => {
      if (!(id in dependencies))
        throw new Error(`Unexpected dependency: ${id}`);
      return dependencies[id];
    },
    Response,
    Headers,
    ...dependencies.globals,
  });
  return exports;
}

function harness({ native = true, saved = null, fetchImpl } = {}) {
  const values = new Map(saved ? [['wordrecall.refresh', saved]] : []);
  const writes = [];
  const calls = [];
  const secureStore = {
    getItemAsync: async (key) => values.get(key) ?? null,
    setItemAsync: async (key, value) => {
      writes.push({ key, value });
      values.set(key, value);
    },
    deleteItemAsync: async (key) => {
      values.delete(key);
    },
  };
  const storage = loadModule(
    `../src/services/refresh-storage${native ? '' : '.web'}.ts`,
    {
      'expo-secure-store': secureStore,
    },
  );
  const fetch = async (url, init) => {
    calls.push({
      url,
      ...init,
      json: init.body ? JSON.parse(init.body) : undefined,
    });
    return fetchImpl ? fetchImpl(url, init) : tokens();
  };
  const service = loadModule('../src/services/auth.ts', {
    '../constants/api': { getApiBaseUrl: () => 'https://api.example.com' },
    './refresh-storage': storage,
    globals: { fetch },
  });
  return { service, storage, values, writes, calls };
}

function tokens(access = 'test-access', refresh = 'test-refresh') {
  return Response.json({ access_token: access, refresh_token: refresh });
}

for (const native of [true, false]) {
  test(`${native ? 'native' : 'web'} sign-up and sign-in use auth endpoints and correct token storage`, async () => {
    const h = harness({ native });
    await h.service.register(
      'learner@example.com',
      'test-password-only',
      'Alex',
    );
    await h.service.signIn('learner@example.com', 'test-password-only');
    assert.deepEqual(
      h.calls.map((c) => c.url),
      [
        'https://api.example.com/api/v1/auth/register',
        'https://api.example.com/api/v1/auth/sign-in',
      ],
    );
    assert.deepEqual(h.calls[0].json, {
      email: 'learner@example.com',
      password: 'test-password-only',
      name: 'Alex',
    });
    assert.deepEqual(h.calls[1].json, {
      email: 'learner@example.com',
      password: 'test-password-only',
    });
    for (const call of h.calls) {
      assert.equal(call.method, 'POST');
      assert.equal(call.headers['Content-Type'], 'application/json');
      assert.equal(call.credentials, native ? 'omit' : 'include');
      assert.equal(
        call.headers['X-Auth-Platform'],
        native ? 'native' : undefined,
      );
    }
    assert.equal(h.writes.length, native ? 2 : 0);
    assert.equal(
      h.values.get('wordrecall.refresh'),
      native ? 'test-refresh' : undefined,
    );
    assert.ok(
      h.writes.every(
        ({ key, value }) =>
          key === 'wordrecall.refresh' && value === 'test-refresh',
      ),
    );
  });
}

test('native restores saved session once and stores the rotated refresh token', async () => {
  const h = harness({
    saved: 'test-saved-refresh',
    fetchImpl: async () => tokens('test-new-access', 'test-rotated-refresh'),
  });
  await Promise.all([h.service.refreshSession(), h.service.refreshSession()]);
  assert.equal(h.calls.length, 1);
  assert.deepEqual(h.calls[0].json, { refresh_token: 'test-saved-refresh' });
  assert.equal(h.values.get('wordrecall.refresh'), 'test-rotated-refresh');
});

test('web restores with an HttpOnly cookie and does not save response tokens in JavaScript storage', async () => {
  const h = harness({
    native: false,
    fetchImpl: async () => Response.json({ access_token: 'test-access' }),
  });
  await h.service.refreshSession();
  assert.equal(h.calls[0].credentials, 'include');
  assert.equal(h.calls[0].json.refresh_token, null);
  assert.equal(h.writes.length, 0);
  assert.equal(h.values.size, 0);
});

test('native rejects token responses missing a refresh token without storing access credentials', async () => {
  const h = harness({
    fetchImpl: async () => Response.json({ access_token: 'test-access' }),
  });
  await assert.rejects(
    h.service.signIn('learner@example.com', 'test-password-only'),
    /Missing refresh credential/,
  );
  assert.equal(h.writes.length, 0);
});

test('invalid refresh clears SecureStore; temporary network failure retains the saved credential', async () => {
  for (const status of [401, 503]) {
    const h = harness({
      saved: 'test-saved-refresh',
      fetchImpl: async () => new Response(null, { status }),
    });
    await assert.rejects(
      h.service.refreshSession(),
      (error) => error.status === status,
    );
    assert.equal(h.values.has('wordrecall.refresh'), status !== 401);
  }
  const h = harness({
    saved: 'test-saved-refresh',
    fetchImpl: async () => {
      throw new TypeError('Test network failure');
    },
  });
  await assert.rejects(h.service.refreshSession(), /Test network failure/);
  assert.equal(h.values.get('wordrecall.refresh'), 'test-saved-refresh');
});

for (const native of [true, false]) {
  test(`${native ? 'native' : 'web'} logout calls the backend and clears local refresh credentials`, async () => {
    const h = harness({
      native,
      saved: native ? 'test-saved-refresh' : null,
      fetchImpl: async () => new Response(null, { status: 204 }),
    });
    await h.service.signOut();
    assert.equal(h.calls[0].url, 'https://api.example.com/api/v1/auth/logout');
    assert.equal(h.calls[0].credentials, native ? 'omit' : 'include');
    assert.equal(
      h.calls[0].json.refresh_token,
      native ? 'test-saved-refresh' : null,
    );
    assert.equal(h.values.size, 0);
  });
}

test('already-expired logout clears SecureStore, while failed logout remains retryable', async () => {
  for (const status of [401, 503]) {
    const h = harness({
      saved: 'test-saved-refresh',
      fetchImpl: async () => new Response(null, { status }),
    });
    if (status === 401) await h.service.signOut();
    else
      await assert.rejects(
        h.service.signOut(),
        (error) => error.status === status,
      );
    assert.equal(h.values.has('wordrecall.refresh'), status !== 401);
  }
});

test('authenticated requests use the memory token and refresh/retry after expiry', async () => {
  let profiles = 0;
  const h = harness({
    fetchImpl: async (url) => {
      if (url.endsWith('/sign-in'))
        return tokens('test-first-access', 'test-first-refresh');
      if (url.endsWith('/refresh'))
        return tokens('test-next-access', 'test-next-refresh');
      if (url.endsWith('/auth/me'))
        return ++profiles === 1
          ? new Response(null, { status: 401 })
          : Response.json({ name: 'Alex' });
      throw new Error('Unexpected URL');
    },
  });
  await h.service.signIn('learner@example.com', 'test-password-only');
  const response = await h.service.authenticatedFetch('/auth/me');
  assert.equal(response.status, 200);
  assert.equal(
    h.calls[1].headers.get('Authorization'),
    'Bearer test-first-access',
  );
  assert.equal(h.calls[2].json.refresh_token, 'test-first-refresh');
  assert.equal(
    h.calls[3].headers.get('Authorization'),
    'Bearer test-next-access',
  );
  assert.equal(h.calls[3].credentials, 'omit');
  assert.equal(h.values.get('wordrecall.refresh'), 'test-next-refresh');
  assert.ok(h.writes.every(({ value }) => !value.includes('access')));
});

test('authenticated requests reject absolute URLs before attaching credentials', async () => {
  const h = harness();
  for (const path of ['https://example.com', '//example.com', 'auth/me']) {
    await assert.rejects(
      h.service.authenticatedFetch(path),
      /API-relative path/,
    );
  }
  assert.equal(h.calls.length, 0);
});

test('expired refresh notifies navigation, temporary errors do not, and unsubscribe works', async () => {
  for (const status of [401, 503]) {
    const h = harness({
      saved: 'test-saved-refresh',
      fetchImpl: async () => new Response(null, { status }),
    });
    let expired = 0;
    const unsubscribe = h.service.onSessionExpired(() => {
      expired++;
    });
    await assert.rejects(h.service.refreshSession());
    assert.equal(expired, status === 401 ? 1 : 0);
    unsubscribe();
    await assert.rejects(h.service.refreshSession());
    assert.equal(expired, status === 401 ? 1 : 0);
  }
});

test('a second unauthorized response expires the session instead of looping refreshes', async () => {
  const h = harness({
    fetchImpl: async (url) =>
      url.endsWith('/auth/me') ? new Response(null, { status: 401 }) : tokens(),
  });
  let expired = 0;
  h.service.onSessionExpired(() => {
    expired++;
  });
  await h.service.signIn('learner@example.com', 'test-password-only');
  await assert.rejects(
    h.service.authenticatedFetch('/auth/me'),
    (error) => error.status === 401,
  );
  assert.equal(
    h.calls.filter((call) => call.url.endsWith('/refresh')).length,
    1,
  );
  assert.equal(expired, 1);
  assert.equal(h.values.size, 0);
});

test('a late unauthorized response reuses the token rotated by another request', async () => {
  let release;
  let firstProfile = true;
  const h = harness({
    saved: 'test-saved-refresh',
    fetchImpl: async (url) => {
      if (url.endsWith('/sign-in'))
        return tokens('test-first-access', 'test-first-refresh');
      if (url.endsWith('/refresh'))
        return tokens('test-rotated-access', 'test-rotated-refresh');
      if (url.endsWith('/auth/me') && firstProfile) {
        firstProfile = false;
        return new Promise((resolve) => {
          release = () => resolve(new Response(null, { status: 401 }));
        });
      }
      return Response.json({ name: 'Alex' });
    },
  });
  await h.service.signIn('learner@example.com', 'test-password-only');
  const request = h.service.authenticatedFetch('/auth/me');
  await h.service.refreshSession();
  release();
  assert.equal((await request).status, 200);
  assert.equal(
    h.calls.filter((call) => call.url.endsWith('/refresh')).length,
    1,
  );
  assert.equal(
    h.calls.at(-1).headers.get('Authorization'),
    'Bearer test-rotated-access',
  );
});

test('an in-flight refresh cannot restore credentials after logout', async () => {
  let release;
  const h = harness({
    saved: 'test-saved-refresh',
    fetchImpl: async (url) => {
      if (url.endsWith('/refresh'))
        return new Promise((resolve) => {
          release = () =>
            resolve(tokens('test-stale-access', 'test-stale-refresh'));
        });
      return new Response(null, { status: 204 });
    },
  });
  const pending = h.service.refreshSession();
  const rejected = assert.rejects(pending, /Session changed/);
  await new Promise((resolve) => setTimeout(resolve, 0));
  await h.service.signOut();
  release();
  await rejected;
  assert.equal(h.values.size, 0);
});

test('native cold start without a saved credential returns signed out without a request', async () => {
  const h = harness();
  await assert.rejects(
    h.service.refreshSession(),
    (error) => error.status === 401,
  );
  assert.equal(h.calls.length, 0);
});

test('a late logout cannot clear a newer sign-in credential', async () => {
  let release;
  const h = harness({
    saved: 'test-old-refresh',
    fetchImpl: async (url) => {
      if (url.endsWith('/logout'))
        return new Promise((resolve) => {
          release = () => resolve(new Response(null, { status: 204 }));
        });
      return tokens('test-new-access', 'test-new-refresh');
    },
  });
  const pending = h.service.signOut();
  const rejected = assert.rejects(pending, /Session changed/);
  await new Promise((resolve) => setTimeout(resolve, 0));
  await h.service.signIn('learner@example.com', 'test-password-only');
  release();
  await rejected;
  assert.equal(h.values.get('wordrecall.refresh'), 'test-new-refresh');
});

for (const native of [true, false]) {
  test(`${native ? 'native' : 'web'} account deletion uses the authenticated endpoint and clears local credentials`, async () => {
    const h = harness({
      native,
      fetchImpl: async (url) =>
        url.endsWith('/account')
          ? new Response(null, { status: 204 })
          : tokens(),
    });
    await h.service.signIn('learner@example.com', 'test-password-only');
    await h.service.deleteAccount();
    const deletion = h.calls.find((call) => call.url.endsWith('/account'));
    assert.equal(deletion.method, 'DELETE');
    assert.equal(deletion.headers.get('Authorization'), 'Bearer test-access');
    assert.equal(deletion.credentials, native ? 'omit' : 'include');
    assert.equal(h.values.size, 0);
    assert.equal(
      h.calls.some((call) => call.url.endsWith('/logout')),
      false,
    );
    // There is no access credential left to use after deleting the account.
    const before = h.calls.length;
    if (native) {
      await assert.rejects(
        h.service.authenticatedFetch('/auth/me'),
        (error) => error.status === 401,
      );
      assert.equal(h.calls.length, before);
    }
  });
}

test('failed account deletion preserves credentials for a retry', async () => {
  let status = 503;
  const h = harness({
    fetchImpl: async (url) =>
      url.endsWith('/account') ? new Response(null, { status }) : tokens(),
  });
  await h.service.signIn('learner@example.com', 'test-password-only');
  await assert.rejects(
    h.service.deleteAccount(),
    (error) => error.status === 503,
  );
  assert.equal(h.values.get('wordrecall.refresh'), 'test-refresh');
  status = 204;
  await h.service.deleteAccount();
  assert.equal(h.values.size, 0);
});

test('account deletion refreshes an expired access token once before retrying', async () => {
  let deletions = 0;
  const h = harness({
    fetchImpl: async (url) => {
      if (url.endsWith('/account'))
        return new Response(null, { status: ++deletions === 1 ? 401 : 204 });
      return tokens();
    },
  });
  await h.service.signIn('learner@example.com', 'test-password-only');
  await h.service.deleteAccount();
  assert.equal(deletions, 2);
  assert.equal(
    h.calls.filter((call) => call.url.endsWith('/refresh')).length,
    1,
  );
  assert.equal(h.values.size, 0);
});
