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
  let dismissToast;
  class HTMLInputElement {}
  class HTMLTextAreaElement {}
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
  const formExports = {};
  runInNewContext(
    ts.transpileModule(
      readFileSync(
        new URL('../src/components/word-form.web.tsx', import.meta.url),
        'utf8',
      ),
      {
        compilerOptions: {
          module: ts.ModuleKind.CommonJS,
          jsx: ts.JsxEmit.ReactJSX,
        },
      },
    ).outputText,
    {
      exports: formExports,
      HTMLInputElement,
      HTMLTextAreaElement,
      require: (id) => dependencies[id],
    },
  );
  runInNewContext(outputText, {
    exports,
    performance,
    URLSearchParams,
    setTimeout: (callback) => {
      dismissToast = callback;
      return 1;
    },
    clearTimeout: () => {},
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
    input: () =>
      nodes().find(
        (n) =>
          n.type === 'Input' &&
          n.props.accessibilityLabel === 'Word to search (required)',
      ),
    text,
    enter: (overrides = {}) => {
      const form = nodes().find((n) => n.type === 'Form');
      const webForm = formExports.WordForm(form.props);
      webForm.props.onKeyDownCapture({
        target: new HTMLInputElement(),
        key: 'Enter',
        shiftKey: false,
        repeat: false,
        nativeEvent: {},
        preventDefault() {},
        stopPropagation() {},
        ...overrides,
      });
    },
    toast: () => tree.props.toast,
    dismissToast: () => dismissToast(),
    saveButton: (word) =>
      nodes().find(
        (n) =>
          n.type === 'Button' &&
          ['Save', 'Saved'].some(
            (label) => n.props.accessibilityLabel === `${label} ${word}`,
          ),
      ),
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

test('web Enter searches once and ignores composing or repeated key events', async () => {
  const calls = [];
  const h = harness(async (path) => {
    calls.push(path);
    return Response.json([]);
  });
  h.input().props.onChangeText(' create ');
  await h.flush();
  h.enter({ nativeEvent: { isComposing: true } });
  h.enter({ nativeEvent: { keyCode: 229 } });
  h.enter({ repeat: true });
  h.enter({ shiftKey: true });
  assert.equal(calls.length, 0);
  h.enter();
  await h.flush();
  assert.equal(calls.length, 1);
  assert.equal(
    new URL(calls[0], 'https://example.test').searchParams.get('q'),
    'create',
  );
  assert.match(h.text(), /No matching words/);
});

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
  assert.match(h.toast(), /already in your word bank/);
  assert.equal(h.button('Saved').props.disabled, true);
});

test('search marks existing words Saved and repeat attempts explain the duplicate without posting', async () => {
  let posts = 0;
  const h = harness(async (_, init) => {
    if (init) posts++;
    return Response.json([
      { ...entry, saved: true },
      { ...entry, word: 'create', saved: false },
    ]);
  });
  h.input().props.onChangeText('create');
  await h.flush();
  await h.button('Search').props.onPress();
  await h.flush();
  assert.equal(h.saveButton('created').props.disabled, true);
  assert.equal(
    h.saveButton('created').props.accessibilityLabel,
    'Saved created',
  );
  assert.equal(h.saveButton('create').props.disabled, false);
  await h.saveButton('created').props.onPress();
  await h.flush();
  assert.equal(posts, 0);
  assert.equal(h.toast(), '“created” is already in your word bank.');
});

test('saving one result shows a temporary confirmation and leaves other results unsaved', async () => {
  const calls = [];
  const h = harness(async (path, init) => {
    if (init) {
      calls.push(JSON.parse(init.body));
      return Response.json({}, { status: 201 });
    }
    return Response.json([
      entry,
      { ...entry, word: 'create', verb_forms: ['V1'] },
    ]);
  });
  h.input().props.onChangeText('create');
  await h.flush();
  await h.button('Search').props.onPress();
  await h.flush();
  await h.saveButton('create').props.onPress();
  await h.flush();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].word, 'create');
  assert.equal(h.saveButton('create').props.accessibilityLabel, 'Saved create');
  assert.equal(h.saveButton('create').props.disabled, true);
  assert.equal(
    h.saveButton('created').props.accessibilityLabel,
    'Save created',
  );
  assert.equal(h.saveButton('created').props.disabled, false);
  assert.equal(h.toast(), '“create” added to your word bank.');
  h.dismissToast();
  await h.flush();
  assert.equal(h.toast(), undefined);
  assert.equal(h.saveButton('create').props.disabled, true);
  await h.saveButton('created').props.onPress();
  await h.flush();
  assert.deepEqual(
    calls.map((call) => call.word),
    ['create', 'created'],
  );
  assert.equal(h.toast(), '“created” added to your word bank.');
});

test('editing filters preserves the word and searches again with updated selections', async () => {
  const calls = [];
  const h = harness(async (path) => {
    calls.push(new URL(path, 'https://example.test').searchParams);
    return Response.json([entry]);
  });
  h.input().props.onChangeText('create');
  await h.flush();
  await h.button('Search').props.onPress();
  await h.flush();
  assert.match(h.text(), /Search results/);

  for (const label of ['Include word family', 'Noun', 'V1 · Base']) {
    h.filter(label).props.onPress();
    await h.flush();
    assert.equal(h.input().props.value, 'create');
    assert.equal(calls.length, 1);
  }
  assert.doesNotMatch(h.text(), /Search results/);
  await h.button('Search').props.onPress();
  await h.flush();
  assert.equal(calls.length, 2);
  assert.equal(calls[1].get('q'), 'create');
  assert.equal(calls[1].get('include_family'), 'false');
  assert.deepEqual(calls[1].getAll('parts'), ['verb', 'adjective', 'adverb']);
  assert.deepEqual(calls[1].getAll('forms'), ['V2', 'V3']);
  assert.equal(h.input().props.value, 'create');
  assert.match(h.text(), /Search results/);
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

test('empty results preserve the word and all filters so the user can adjust and retry', async () => {
  const calls = [];
  const h = harness(async (path) => {
    calls.push(new URL(path, 'https://example.test').searchParams);
    return Response.json(calls.length === 1 ? [] : [entry]);
  });
  h.input().props.onChangeText('create');
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
  const selections = () => labels.map((label) => h.filter(label).props.checked);
  const before = selections();
  await h.button('Search').props.onPress();
  await h.flush();
  assert.match(
    h.text(),
    /No matching words found\. Try another word or change your filters\./,
  );
  assert.match(h.text(), /0 found/);
  assert.equal(h.input().props.value, 'create');
  assert.deepEqual(selections(), before);
  assert.equal(h.button('Search').props.disabled, false);

  h.filter('V1 · Base').props.onPress();
  await h.flush();
  await h.button('Search').props.onPress();
  await h.flush();
  assert.equal(calls[1].get('q'), 'create');
  assert.equal(calls[1].get('include_family'), 'false');
  assert.deepEqual(calls[1].getAll('parts'), ['verb', 'adjective', 'adverb']);
  assert.deepEqual(calls[1].getAll('forms'), ['V2', 'V3', 'V1']);
  assert.match(h.text(), /1 found/);
  assert.doesNotMatch(h.text(), /No matching words found/);
  assert.equal(h.input().props.value, 'create');
});

for (const failure of ['network', 'server']) {
  for (const action of ['search', 'save']) {
    test(`${action} ${failure} failure preserves inputs and unsaved results and offers Try again`, async () => {
      let failNext = false;
      const calls = [];
      const h = harness(async (path, init) => {
        calls.push({ path, init });
        if (failNext) {
          failNext = false;
          if (failure === 'network') throw new Error('offline');
          return new Response(null, { status: 503 });
        }
        return init
          ? Response.json({}, { status: 201 })
          : Response.json([
              entry,
              { ...entry, word: 'create', verb_forms: ['V1'] },
            ]);
      });
      h.input().props.onChangeText('create');
      h.filter('Include word family').props.onPress();
      h.filter('Noun').props.onPress();
      h.filter('V1 · Base').props.onPress();
      await h.flush();
      await h.button('Search').props.onPress();
      await h.flush();
      failNext = true;
      await (
        action === 'search' ? h.button('Search') : h.saveButton('created')
      ).props.onPress();
      await h.flush();
      assert.match(
        h.text(),
        action === 'search' ? /Could not search/ : /Could not save/,
      );
      assert.equal(h.input().props.value, 'create');
      assert.equal(h.filter('Include word family').props.checked, false);
      assert.equal(h.filter('Noun').props.checked, false);
      assert.equal(h.filter('V1 · Base').props.checked, false);
      assert.equal(h.saveButton('created').props.disabled, false);
      assert.equal(h.saveButton('create').props.disabled, false);
      assert.match(h.text(), /2 found/);
      await h.button('Try again').props.onPress();
      await h.flush();
      assert.equal(calls.length, 3);
      assert.equal(calls[2].path, calls[1].path);
      assert.deepEqual(calls[2].init, calls[1].init);
      assert.equal(h.button('Try again'), undefined);
      assert.equal(h.input().props.value, 'create');
      assert.equal(h.saveButton('create').props.disabled, false);
      assert.equal(h.saveButton('created').props.disabled, action === 'save');
    });
  }
}

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
