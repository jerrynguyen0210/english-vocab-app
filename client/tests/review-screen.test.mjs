import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

// Drive the production screen's handlers with a minimal hook host. Native layout
// and screen readers still require device verification.
const previewModule = {};
runInNewContext(
  ts.transpileModule(
    readFileSync(
      new URL('../src/constants/review-preview.ts', import.meta.url),
      'utf8',
    ),
    {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    },
  ).outputText,
  { exports: previewModule },
);

function harness(fetch, params = {}) {
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
      if (!slots[i] || deps.some((v, j) => v !== slots[i][j]))
        effects.push(callback);
      slots[i] = deps;
    },
  };
  const jsx = (type, props) => ({ type, props });
  const dependencies = {
    react,
    'expo-router': { useLocalSearchParams: () => params },
    '@/constants/review-preview': previewModule,
    'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': {
      ActivityIndicator: 'Spinner',
      Pressable: 'Button',
      TextInput: 'Input',
      View: 'View',
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
      new URL('../src/app/(app)/review.tsx', import.meta.url),
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

test('preview filters source data and never calls the server through completion', async () => {
  const { selectPreviewWords } = previewModule;
  assert.equal(selectPreviewWords('time', 'Yesterday', '', true).length, 4);
  assert.equal(selectPreviewWords('time', 'Weekly', '', true).length, 10);
  assert.equal(selectPreviewWords('recall', 'Weekly', '', false).length, 9);
  assert.equal(
    selectPreviewWords('topic', 'Weekly', 'unknown', true).length,
    0,
  );
  const h = harness(
    () => {
      throw new Error('Preview must not call the server');
    },
    { preview: 'true', source: 'topic', topic: 'Travel' },
  );
  await h.flush();
  assert.match(h.text(), /Sample data/);
  h.button('A collaborate').props.onPress();
  await h.flush();
  await h.button('Check answer').props.onPress();
  await h.flush();
  assert.match(h.text(), /CORRECT WORDitinerary/);
  h.button('Next word').props.onPress();
  await h.flush();
  h.button('Typing').props.onPress();
  await h.flush();
  h.input().props.onChangeText('destination');
  await h.flush();
  await h.button('Check answer').props.onPress();
  await h.flush();
  h.button('Next word').props.onPress();
  await h.flush();
  assert.match(h.text(), /1 of 2 answers correct/);
});
