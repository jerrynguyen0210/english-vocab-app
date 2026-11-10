import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

// Drive the production screen's handlers with a minimal hook host. Native layout
// and screen readers still require device verification.
function harness(fetch) {
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
    'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': {
      ActivityIndicator: 'Spinner',
      Pressable: 'Button',
      TextInput: 'Input',
      View: 'View',
      Platform: { OS: 'web', select: (values) => values.web },
      StyleSheet: { create: (s) => s },
      AccessibilityInfo: {},
    },
    'expo-image': { Image: 'Image' },
    '@/context/session': { useSession: () => ({ signedIn }) },
    '@/services/auth': { authenticatedFetch: fetch, AuthError },
    '@/services/connectivity': { connectionMessage: (_, fallback) => fallback },
    '@/components/word-form': { WordForm: 'Form' },
    '@/components/app-screen': { AppScreen: 'Screen' },
    '@/components/navigation-link': { NavigationLink: 'Link' },
    '@/components/themed-text': { ThemedText: 'Text' },
    '@/constants/wordwell-theme': { WordwellColors: {} },
  };
  const { outputText } = ts.transpileModule(
    readFileSync(
      new URL('../src/app/(app)/add-word.tsx', import.meta.url),
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
    URLSearchParams,
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
    filter: (label) => nodes().find((n) => n.props?.label === label),
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

const entry = {
  word: 'created',
  part_of_speech: 'verb',
  verb_forms: ['V2', 'V3'],
  english_explanation: 'Verb form of create: make something',
  example_sentence: null,
};

test('required search and selected filters reach the API; results save and detect duplicates', async () => {
  const calls = [];
  const h = harness(async (path, init) => {
    calls.push({ path, init });
    return init ? new Response(null, { status: 409 }) : Response.json([entry]);
  });
  await h.button('Search').props.onPress();
  await h.flush();
  assert.match(h.text(), /Enter a word to search/);
  assert.equal(calls.length, 0);
  h.input().props.onChangeText(' create ');
  h.filter('Include word family').props.onPress();
  h.filter('V1 · Base').props.onPress();
  await h.flush();
  await h.button('Search').props.onPress();
  await h.flush();
  const query = new URL(calls[0].path, 'https://example.test').searchParams;
  assert.equal(query.get('q'), 'create');
  assert.equal(h.input().props.value, 'create');
  assert.equal(query.get('include_family'), 'false');
  assert.deepEqual(query.getAll('forms'), ['V2', 'V3']);
  assert.deepEqual(query.getAll('parts'), [
    'noun',
    'verb',
    'adjective',
    'adverb',
  ]);
  await h.button('Save').props.onPress();
  await h.flush();
  assert.equal(JSON.parse(calls[1].init.body).word, 'created');
  assert.match(h.text(), /already in your word bank/);
  assert.equal(h.button('Saved').props.disabled, true);
});

test('blank searches show validation and preserve every selected filter', async () => {
  const calls = [];
  const h = harness(async (path) => {
    calls.push(path);
    return Response.json([]);
  });
  h.filter('Include word family').props.onPress();
  h.filter('Noun').props.onPress();
  h.filter('V1 · Base').props.onPress();
  await h.flush();
  const labels = [
    'Include word family',
    'Noun',
    'Verb',
    'Adjective',
    'Adverb',
    'Other',
    'V1 · Base',
    'V2 · Past',
    'V3 · Past participle',
  ];
  const selected = () => labels.map((label) => h.filter(label).props.checked);
  const before = selected();
  for (const value of ['', ' \t\n ']) {
    h.input().props.onChangeText(value);
    await h.flush();
    await h.button('Search').props.onPress();
    await h.flush();
    assert.match(h.text(), /Enter a word to search\./);
    assert.equal(h.input().props['aria-invalid'], true);
    assert.equal(h.input().props.value, '');
    assert.deepEqual(selected(), before);
    assert.equal(calls.length, 0);
  }
});

test('search stays busy until matching forms and definitions arrive', async () => {
  let resolve;
  const h = harness(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  h.input().props.onChangeText('create');
  await h.flush();
  const pending = h.button('Search').props.onPress();
  await h.flush();
  assert.equal(h.button('Searching…').props.disabled, true);
  assert.equal(h.button('Searching…').props.accessibilityState.busy, true);
  assert.match(h.text(), /Fetching matching forms and definitions/);
  assert.doesNotMatch(
    h.text(),
    /No results yet|Enter a word and select Search/,
  );
  const entries = [
    { ...entry, word: 'create', verb_forms: ['V1'] },
    entry,
    { ...entry, word: 'creation', part_of_speech: 'noun', verb_forms: [] },
    { ...entry, word: 'creative', part_of_speech: 'adjective', verb_forms: [] },
    { ...entry, word: 'creatively', part_of_speech: 'adverb', verb_forms: [] },
  ].map((item) => ({
    ...item,
    english_explanation: `Definition of ${item.word}.`,
  }));
  resolve(Response.json(entries));
  await pending;
  await h.flush();
  assert.equal(h.button('Search').props.disabled, false);
  assert.doesNotMatch(h.text(), /Fetching matching/);
  for (const [word, label] of [
    ['create', 'Verb · V1'],
    ['created', 'Verb · V2/V3'],
    ['creation', 'Noun'],
    ['creative', 'Adjective'],
    ['creatively', 'Adverb'],
  ]) {
    assert.ok(h.text().includes(`${word}${label}Definition of ${word}.`));
  }
});

test('stale search responses are discarded when the query changes', async () => {
  let resolve;
  const h = harness(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  h.input().props.onChangeText('create');
  await h.flush();
  const pending = h.button('Search').props.onPress();
  h.input().props.onChangeText('write');
  await h.flush();
  resolve(Response.json([entry]));
  await pending;
  await h.flush();
  assert.match(h.text(), /No results yet/);
  assert.doesNotMatch(h.text(), /created/);
});

test('failed search can retry without losing query or filters', async () => {
  let count = 0;
  const h = harness(async () => {
    if (++count === 1) throw new Error('offline');
    return Response.json([]);
  });
  h.input().props.onChangeText('create');
  await h.flush();
  await h.button('Search').props.onPress();
  await h.flush();
  assert.match(h.text(), /Could not search/);
  assert.equal(h.input().props.value, 'create');
  await h.button('Search').props.onPress();
  await h.flush();
  assert.match(h.text(), /No matching words/);
});
