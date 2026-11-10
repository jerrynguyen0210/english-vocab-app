import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

// Drive the production screen's handlers with a minimal hook host. Native layout
// and screen readers still require device verification.
const reviewModule = {};
runInNewContext(
  ts.transpileModule(
    readFileSync(new URL('../src/services/review.ts', import.meta.url), 'utf8'),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    },
  ).outputText,
  { exports: reviewModule, URLSearchParams },
);

function harness(fetch, params = {}, screen = 'review') {
  const timers = new Map();
  let timerId = 0;
  const slots = [];
  let cursor = 0;
  let effects = [];
  let tree;
  let signedIn = true;
  class AuthError extends Error {
    constructor(status) {
      super();
      this.status = status;
    }
  }
  const react = {
    useCallback(callback, deps) {
      const i = cursor++;
      if (!slots[i] || deps.some((value, j) => value !== slots[i].deps[j]))
        slots[i] = { callback, deps };
      return slots[i].callback;
    },
    useState(initial) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = initial;
      return [
        slots[i],
        (value) => {
          slots[i] = typeof value === 'function' ? value(slots[i]) : value;
        },
      ];
    },
    useRef(initial) {
      const i = cursor++;
      return (slots[i] ??= { current: initial });
    },
    useEffect(callback, deps) {
      const i = cursor++;
      const previous = slots[i];
      if (!previous || deps.some((value, j) => value !== previous.deps[j])) {
        effects.push(() => {
          previous?.cleanup?.();
          slots[i].cleanup = callback();
        });
        slots[i] = { deps };
      }
    },
  };
  const jsx = (type, props) => ({ type, props });
  const dependencies = {
    react,
    'expo-router': {
      useLocalSearchParams: () => params,
      useFocusEffect: (callback) => react.useEffect(callback, [callback]),
    },
    '@/services/review': reviewModule,
    'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': {
      ActivityIndicator: 'Spinner',
      Pressable: 'Button',
      TextInput: 'Input',
      View: 'View',
      Switch: 'Switch',
      Platform: { OS: 'web' },
      StyleSheet: { create: (s) => s },
      AccessibilityInfo: {},
    },
    'expo-image': { Image: 'Image' },
    '@/context/session': { useSession: () => ({ signedIn }) },
    '@/services/auth': { authenticatedFetch: fetch, AuthError },
    '@/services/connectivity': { connectionMessage: (_, fallback) => fallback },
    '@/components/app-screen': { AppScreen: 'Screen' },
    '@/components/navigation-link': { NavigationLink: 'Link' },
    '@/components/themed-text': { ThemedText: 'Text' },
    '@/constants/wordwell-theme': { WordwellColors: {} },
  };
  const { outputText } = ts.transpileModule(
    readFileSync(
      new URL(`../src/app/(app)/${screen}.tsx`, import.meta.url),
      'utf8',
    ),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
        target: ts.ScriptTarget.ES2022,
      },
    },
  );
  const exports = {};
  runInNewContext(outputText, {
    exports,
    performance,
    setTimeout: (callback) => {
      const id = ++timerId;
      timers.set(id, callback);
      return id;
    },
    clearTimeout: (id) => timers.delete(id),
    require: (id) => (id.endsWith('.svg') ? id : dependencies[id]),
  });
  function render() {
    cursor = 0;
    tree = exports.default();
    const pending = effects;
    effects = [];
    pending.forEach((fn) => fn());
  }
  function nodes(node = tree) {
    if (!node || typeof node !== 'object') return [];
    if (Array.isArray(node)) return node.flatMap(nodes);
    return [node, ...nodes(node.props?.children ?? null)];
  }
  function text(node = tree) {
    if (node == null || typeof node === 'boolean') return '';
    if (Array.isArray(node)) return node.map(text).join('');
    return typeof node === 'object'
      ? text(node.props?.children ?? null)
      : String(node);
  }
  render();
  return {
    AuthError,
    async flush() {
      await new Promise((resolve) => setImmediate(resolve));
      render();
    },
    async advance() {
      const pending = [...timers.values()];
      timers.clear();
      pending.forEach((callback) => callback());
      await new Promise((resolve) => setImmediate(resolve));
      render();
    },
    link: () =>
      nodes().find(
        (n) => n.type === 'Link' && n.props.label.startsWith('Start review'),
      ),
    radio: (title) =>
      nodes().find(
        (n) =>
          n.type === 'Button' &&
          n.props.accessibilityRole === 'radio' &&
          text(n).includes(title),
      ),
    toggle: () => nodes().find((n) => n.type === 'Switch'),
    input: () => nodes().find((n) => n.type === 'Input'),
    text,
    button: (label) =>
      nodes().find((n) => n.type === 'Button' && text(n) === label),
    setSignedIn(value) {
      signedIn = value;
      render();
    },
  };
}
const prompts = [
  {
    word_id: 'one',
    attempt_id: 'attempt-one',
    english_explanation: 'A greeting',
    example_sentence: null,
  },
];

test('lost submit response retains draft and exact retry; snapshot finishes with count', async () => {
  const bodies = [];
  let loads = 0;
  const h = harness(async (path, init) => {
    if (!init) {
      loads++;
      return Response.json(prompts);
    }
    bodies.push(init.body);
    if (bodies.length === 1) throw new Error('response lost');
    return Response.json({ result: 'correct', correct_word: 'Hello' });
  });
  await h.flush();
  h.input().props.onChangeText(' Hello ');
  await h.flush();
  await h.button('Submit answer').props.onPress();
  await h.flush();
  assert.equal(h.input().props.value, ' Hello ');
  assert.equal(h.input().props.editable, false);
  await h.button('Retry submission').props.onPress();
  await h.flush();
  assert.equal(bodies[0], bodies[1]);
  h.button('Next word').props.onPress();
  await h.flush();
  assert.match(h.text(), /Review finished/);
  assert.match(h.text(), /1 of 1 answers correct/);
  assert.equal(loads, 1); // Words added remotely cannot extend this session.
});

test('expiry retains answer and allows retry after same-account sign-in', async () => {
  let fail = true;
  const h = harness(async (_, init) => {
    if (!init) return Response.json(prompts);
    if (fail) throw new h.AuthError(401);
    return Response.json({ result: 'incorrect', correct_word: 'Hello' });
  });
  await h.flush();
  h.input().props.onChangeText('helo');
  await h.flush();
  await h.button('Submit answer').props.onPress();
  await h.flush();
  h.setSignedIn(false);
  assert.equal(h.input().props.value, 'helo');
  assert.equal(h.button('Retry submission').props.disabled, true);
  fail = false;
  h.setSignedIn(true);
  await h.button('Retry submission').props.onPress();
  await h.flush();
  assert.match(h.text(), /YOU TYPEDheloCORRECT WORDHello/);
});

test('empty session shows nothing due without an answer field', async () => {
  const h = harness(async () => Response.json([]));
  await h.flush();
  assert.match(h.text(), /Nothing due/);
  assert.equal(h.input(), undefined);
});

test('selected source loads a live session; answer modes share the signed submission', async () => {
  const requests = [];
  const h = harness(
    async (path, init) => {
      requests.push({ path, init });
      if (!init)
        return Response.json([
          {
            ...prompts[0],
            review_token: 'signed-session',
            choices: ['Hello', 'Goodbye'],
          },
        ]);
      return Response.json({ result: 'correct', correct_word: 'Hello' });
    },
    { source: 'topic', topic: 'Work & travel', includeOverdue: 'false' },
  );
  await h.flush();
  assert.match(requests[0].path, /source=topic/);
  assert.equal(
    new URLSearchParams(requests[0].path.split('?')[1]).get('topic'),
    'Work & travel',
  );
  h.button('A Hello').props.onPress();
  await h.flush();
  h.button('Typing').props.onPress();
  await h.flush();
  assert.equal(h.input().props.value, '');
  h.input().props.onChangeText('Hello');
  await h.flush();
  await h.button('Submit answer').props.onPress();
  await h.flush();
  assert.equal(
    JSON.parse(requests[1].init.body).review_token,
    'signed-session',
  );
  h.button('Next word').props.onPress();
  await h.flush();
  assert.match(h.text(), /1 of 1 answers correct/);
});

test('preparation loads live counts, rejects stale responses and passes selected filters', async () => {
  let resolveOld;
  const paths = [];
  const h = harness(
    async (path) => {
      paths.push(path);
      if (new URLSearchParams(path.split('?')[1]).get('period') === 'Weekly')
        return new Promise((resolve) => {
          resolveOld = resolve;
        });
      return Response.json({ count: 4, matching_count: 4 });
    },
    {},
    'review-preparation',
  );
  assert.equal(h.link(), undefined);
  await h.advance();
  h.radio('Yesterday').props.onPress();
  await h.flush();
  await h.advance();
  assert.match(h.text(), /4 words ready/);
  assert.equal(h.link().props.href.params.period, 'Yesterday');
  resolveOld(Response.json({ count: 99, matching_count: 99 }));
  await h.flush();
  assert.match(h.text(), /4 words ready/);
  assert.doesNotMatch(h.text(), /99 words/);
  h.radio('SM-2 recall').props.onPress();
  await h.flush();
  h.toggle().props.onValueChange(false);
  await h.flush();
  await h.advance();
  assert.equal(h.link().props.href.params.includeOverdue, 'false');
  assert.ok(paths.some((path) => path.includes('include_overdue=false')));
});

test('preparation retries failed counts, searches saved tags and disables empty results', async () => {
  let fail = true;
  const paths = [];
  const h = harness(
    async (path) => {
      paths.push(path);
      if (fail) throw new Error('offline');
      if (path.startsWith('/words/topics')) return Response.json(['workplace']);
      const params = new URLSearchParams(path.split('?')[1]);
      return Response.json({
        count: params.get('topic') === 'missing' ? 0 : 2,
        matching_count: 2,
      });
    },
    {},
    'review-preparation',
  );
  await h.advance();
  assert.match(h.text(), /Could not load ready words/);
  assert.equal(h.link(), undefined);
  fail = false;
  h.button('Try again').props.onPress();
  await h.flush();
  await h.advance();
  assert.match(h.text(), /2 words ready/);
  h.radio('By topic').props.onPress();
  await h.flush();
  await h.advance();
  assert.equal(h.link(), undefined);
  h.input().props.onChangeText('work');
  await h.flush();
  await h.advance();
  h.button('workplace').props.onPress();
  await h.flush();
  await h.advance();
  assert.equal(h.link().props.href.params.topic, 'workplace');
  h.input().props.onChangeText('missing');
  await h.flush();
  await h.advance();
  assert.equal(h.link(), undefined);
  assert.match(h.text(), /No words to review/);
  assert.ok(paths.some((path) => path === '/words/topics?q=work'));
});
