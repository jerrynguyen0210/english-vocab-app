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

function harness(fetch, params = {}, screen = 'review', platform = 'web') {
  const announcements = [];
  const timers = new Map();
  let timerId = 0;
  const slots = [];
  let cursor = 0;
  let effects = [];
  let tree;
  let focusCalls = 0;
  let previousInputRef;
  let signedIn = true;
  let focusCallback;
  let focusCleanup;
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
  const jsx = (type, props) =>
    typeof type === 'function' ? type(props) : { type, props };
  const dependencies = {
    react,
    'expo-router': {
      useLocalSearchParams: () => params,
      useFocusEffect: (callback) => {
        focusCallback = callback;
        react.useEffect(() => {
          focusCleanup = callback();
          return () => focusCleanup?.();
        }, [callback]);
      },
    },
    '@/services/review': reviewModule,
    'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
    'react-native': {
      ActivityIndicator: 'Spinner',
      Pressable: 'Button',
      TextInput: 'Input',
      View: 'View',
      Switch: 'Switch',
      Platform: {
        OS: platform,
        select: (values) => values[platform] ?? values.default,
      },
      StyleSheet: { create: (s) => s },
      AccessibilityInfo: {
        announceForAccessibility: (message) => announcements.push(message),
      },
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
  const emptyModule = {};
  runInNewContext(
    ts.transpileModule(
      readFileSync(
        new URL('../src/components/review-empty-state.tsx', import.meta.url),
        'utf8',
      ),
      {
        compilerOptions: {
          module: ts.ModuleKind.CommonJS,
          jsx: ts.JsxEmit.ReactJSX,
          target: ts.ScriptTarget.ES2022,
        },
      },
    ).outputText,
    {
      exports: emptyModule,
      require: (id) => (id.endsWith('.svg') ? id : dependencies[id]),
    },
  );
  dependencies['@/components/review-empty-state'] = emptyModule;
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
    if (previousInputRef) previousInputRef.current = null;
    const inputNode = nodes().find((node) => node.type === 'Input');
    previousInputRef = inputNode?.props.ref;
    if (previousInputRef)
      previousInputRef.current = {
        focus: () => {
          focusCalls++;
        },
      };
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
    announcements: () => announcements,
    liveRegion: () =>
      nodes().find(
        (node) =>
          node.type === 'Text' &&
          node.props.accessibilityLiveRegion === 'polite',
      ),
    feedback: () =>
      nodes().find((node) => node.props?.testID === 'review-feedback'),
    feedbackText: () =>
      text(nodes().find((node) => node.props?.testID === 'review-feedback')),
    focusCalls: () => focusCalls,
    refocus() {
      focusCleanup?.();
      focusCleanup = focusCallback?.();
      render();
    },
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
    navigation: (label) =>
      nodes().find(
        (node) => node.type === 'Link' && node.props.label === label,
      ),
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
    progress: () =>
      nodes().find((node) =>
        node.props?.accessibilityLabel?.startsWith('Word '),
      ),
    sentence: () =>
      nodes().find(
        (node) =>
          node.type === 'Text' &&
          node.props.children === 'She said _____ when we met.',
      ),
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
    prompt_sentence: 'She said _____ when we met.',
  },
];

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
  await h.button('Check answer').props.onPress();
  await h.flush();
  h.setSignedIn(false);
  assert.equal(h.input().props.value, 'helo');
  assert.equal(h.button('Retry submission').props.disabled, true);
  fail = false;
  h.setSignedIn(true);
  await h.button('Retry submission').props.onPress();
  await h.flush();
  assert.match(h.text(), /YOUR ANSWERheloCORRECT WORDHello/);
});

test('empty session shows nothing due without an answer field', async () => {
  const h = harness(async (path) =>
    Response.json(
      path.startsWith('/reviews/preparation')
        ? {
            saved_count: 1,
            due_count: 0,
            daily_remaining: 20,
            count: 0,
            matching_count: 0,
          }
        : [],
    ),
  );
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
            choices: ['Hello', 'Goodbye', 'Welcome', 'Farewell'],
          },
        ]);
      return Response.json({ result: 'correct', correct_word: 'Hello' });
    },
    { source: 'time', period: 'Monthly', includeOverdue: 'false' },
  );
  await h.flush();
  assert.match(requests[0].path, /source=time/);
  assert.equal(
    new URLSearchParams(requests[0].path.split('?')[1]).get('period'),
    'Monthly',
  );
  h.button('Multiple choice').props.onPress();
  await h.flush();
  h.button('Typing').props.onPress();
  await h.flush();
  assert.equal(h.input().props.value, '');
  h.input().props.onChangeText('Hello');
  await h.flush();
  await h.button('Check answer').props.onPress();
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

test('topic searches only on submit and passes the searched topic into review', async () => {
  let fail = true;
  const paths = [];
  const h = harness(
    async (path) => {
      paths.push(path);
      if (fail) throw new Error('offline');
      return Response.json({ count: 2, matching_count: 2, saved_count: 12 });
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
  const requestsBeforeTopic = paths.length;
  h.radio('By topic').props.onPress();
  await h.flush();
  await h.advance();
  assert.equal(h.link(), undefined);
  h.input().props.onChangeText('Workplace communication');
  await h.flush();
  await h.advance();
  assert.equal(h.input().props.value, 'Workplace communication');
  assert.match(h.text(), /Search your saved words by meaning/);
  assert.match(h.text(), /12 words in your word bank/);
  assert.equal(h.button('Search a topic to begin').props.disabled, true);
  assert.equal(paths.length, requestsBeforeTopic + 1);
  assert.equal(paths.at(-1), '/reviews/summary');
  h.input().props.onSubmitEditing();
  await h.flush();
  assert.equal(h.link(), undefined);
  await h.advance();
  assert.match(h.text(), /2 matching words/);
  assert.equal(h.link().props.href.params.topic, 'Workplace communication');
  assert.equal(
    new URLSearchParams(paths.at(-1).split('?')[1]).get('topic'),
    'Workplace communication',
  );
  h.input().props.onChangeText('A different topic');
  await h.flush();
  assert.equal(h.link(), undefined);
  h.radio('By time').props.onPress();
  await h.flush();
  h.radio('By topic').props.onPress();
  await h.flush();
  assert.equal(h.input().props.value, 'A different topic');
});

test('topic summary retries, refreshes on focus and ignores responses after switching sources', async () => {
  let summaryReply = () => Response.json({}, { status: 503 });
  const h = harness(
    async (path) =>
      path === '/reviews/summary'
        ? summaryReply()
        : Response.json({ count: 3, matching_count: 3 }),
    {},
    'review-preparation',
  );
  h.radio('By topic').props.onPress();
  await h.flush();
  assert.match(h.text(), /Loading word bank/);
  assert.equal(h.button('Search a topic to begin').props.disabled, true);
  await h.advance();
  assert.match(h.text(), /Could not load topic matches/);
  assert.doesNotMatch(h.text(), /0 words in your word bank/);
  summaryReply = () => Response.json({ saved_count: 0 });
  h.button('Try again').props.onPress();
  await h.flush();
  await h.advance();
  assert.match(h.text(), /0 words in your word bank/);
  assert.equal(h.link(), undefined);
  summaryReply = () => Response.json({ saved_count: 7 });
  h.refocus();
  await h.advance();
  assert.match(h.text(), /7 words in your word bank/);
  let resolveSummary;
  summaryReply = () => new Promise((resolve) => (resolveSummary = resolve));
  h.refocus();
  await h.advance();
  h.radio('By time').props.onPress();
  await h.flush();
  await h.advance();
  resolveSummary(Response.json({ saved_count: 99 }));
  await h.flush();
  assert.match(h.text(), /3 words ready/);
  assert.doesNotMatch(h.text(), /99 words/);
  assert.ok(h.link());
});

test('topic search handles pending indexing, retry, no matches and stale responses', async () => {
  const paths = [];
  let reply = () => Response.json({}, { status: 409 });
  const h = harness(
    async (path) => {
      paths.push(path);
      return path === '/reviews/summary'
        ? Response.json({ saved_count: 5 })
        : reply();
    },
    {},
    'review-preparation',
  );
  h.radio('By topic').props.onPress();
  await h.flush();
  await h.advance();
  h.input().props.onChangeText('   ');
  await h.flush();
  h.input().props.onSubmitEditing();
  await h.flush();
  await h.advance();
  assert.equal(paths.filter((path) => path.includes('source=topic')).length, 0);
  h.input().props.onChangeText('work');
  await h.flush();
  h.button('Search').props.onPress();
  await h.flush();
  await h.advance();
  assert.match(h.text(), /being prepared/);
  assert.equal(h.link(), undefined);
  reply = () =>
    Response.json({
      count: 0,
      matching_count: 0,
      saved_count: 5,
      due_count: 0,
    });
  h.button('Try again').props.onPress();
  await h.flush();
  await h.advance();
  assert.match(h.text(), /No words match this review/);
  assert.doesNotMatch(h.text(), /Nothing due/);
  let resolveOld;
  reply = () =>
    new Promise((resolve) => {
      resolveOld = resolve;
    });
  h.input().props.onSubmitEditing();
  await h.flush();
  await h.advance();
  h.input().props.onChangeText('travel');
  await h.flush();
  resolveOld(Response.json({ count: 10, matching_count: 10, saved_count: 5 }));
  await h.flush();
  await h.advance();
  assert.equal(h.link(), undefined);
  assert.doesNotMatch(h.text(), /10 matching words/);
});

test('multiple choice renders exactly the server options in order and submits the selection', async () => {
  const choices = ['Farewell', 'Welcome', 'Hello', 'Goodbye'];
  let submitted;
  const h = harness(async (_, init) => {
    if (!init) return Response.json([{ ...prompts[0], choices }]);
    submitted = JSON.parse(init.body);
    return Response.json({ result: 'correct', correct_word: 'Hello' });
  });
  await h.flush();
  h.button('Multiple choice').props.onPress();
  await h.flush();
  assert.equal(h.input(), undefined);
  assert.equal(h.button('Check answer'), undefined);
  choices.forEach((value, index) =>
    assert.ok(h.button(`${String.fromCharCode(65 + index)}. ${value}`)),
  );
  h.button('C. Hello').props.onPress();
  await h.flush();
  assert.equal(h.button('Check answer'), undefined);
  assert.equal(submitted.typed_answer, 'Hello');
});

for (const choices of [
  [],
  ['Hello', 'Goodbye', 'Welcome'],
  ['Hello', 'Goodbye', 'Welcome', 'Farewell', 'Hi'],
  ['Hello', 'Hello', 'Goodbye', 'Welcome'],
  ['Hello', '', 'Goodbye', 'Welcome'],
]) {
  test(`invalid server option list uses typing without inventing answers: ${JSON.stringify(choices)}`, async () => {
    const h = harness(async () => Response.json([{ ...prompts[0], choices }]));
    await h.flush();
    assert.ok(h.input());
    assert.equal(h.button('Multiple choice').props.disabled, true);
    assert.match(h.text(), /Spelling matters · Enter to submit/);
    assert.equal(h.button('A. Hello'), undefined);
  });
}

test('typing auto-focuses with spelling assistance off and Enter uses the exact D2 draft once', async () => {
  const requests = [];
  const h = harness(async (path, init) => {
    requests.push({ path, init });
    if (!init)
      return Response.json([
        { ...prompts[0], review_token: 'signed' },
        {
          ...prompts[0],
          word_id: 'two',
          attempt_id: 'attempt-two',
          review_token: 'signed-two',
        },
      ]);
    return Response.json({ result: 'correct', correct_word: 'Hello' });
  });
  await h.flush();
  assert.match(requests[0].path, /answer_mode=typing/);
  assert.equal(requests.length, 1);
  assert.equal(h.input().props.autoCorrect, false);
  assert.equal(h.input().props.autoCapitalize, 'none');
  assert.equal(h.input().props.autoComplete, 'off');
  assert.equal(h.input().props.spellCheck, false);
  assert.ok(h.focusCalls() > 0);
  assert.match(h.text(), /Spelling matters · Enter to submit/);
  h.input().props.onChangeText(' HeLLo ');
  await h.flush();
  h.input().props.onSubmitEditing();
  h.input().props.onSubmitEditing();
  await h.flush();
  assert.equal(requests.length, 2);
  assert.equal(JSON.parse(requests[1].init.body).typed_answer, ' HeLLo ');
  const beforeNext = h.focusCalls();
  h.button('Next word').props.onPress();
  await h.flush();
  assert.equal(h.input().props.value, '');
  assert.ok(h.focusCalls() > beforeNext);
});

test('typing loads no choices; switching modes fetches only the current item and preserves progress', async () => {
  const requests = [];
  const prompt = { ...prompts[0], review_token: 'signed' };
  const h = harness(async (path, init) => {
    requests.push({ path, init });
    if (!init) return Response.json([prompt]);
    if (path.endsWith('/choices'))
      return Response.json({
        ...prompt,
        choices: ['Hello', 'Goodbye', 'Welcome', 'Farewell'],
      });
    throw new Error('No answer should be submitted');
  });
  await h.flush();
  assert.equal(requests.length, 1);
  assert.doesNotMatch(h.text(), /Hello/);
  assert.ok(h.input());
  assert.ok(h.sentence());
  const progress = h.progress().props.accessibilityLabel;
  await h.button('Multiple choice').props.onPress();
  await h.flush();
  assert.equal(requests[1].path, '/reviews/one/choices');
  assert.deepEqual(JSON.parse(requests[1].init.body), {
    attempt_id: 'attempt-one',
    review_token: 'signed',
  });
  assert.ok(h.button('A. Hello'));
  assert.equal(h.progress().props.accessibilityLabel, progress);
  assert.ok(h.sentence());
  const beforeTyping = h.focusCalls();
  h.button('Typing').props.onPress();
  await h.flush();
  assert.doesNotMatch(h.text(), /Hello/);
  assert.ok(h.focusCalls() > beforeTyping);
  assert.equal(requests.length, 2);
  assert.ok(h.sentence());
});

test('multiple-choice mode loads each next snapshot item without restarting the session', async () => {
  const items = [
    { ...prompts[0], review_token: 'signed-one' },
    {
      ...prompts[0],
      word_id: 'two',
      attempt_id: 'attempt-two',
      review_token: 'signed-two',
    },
  ];
  const paths = [];
  const h = harness(async (path, init) => {
    paths.push(path);
    if (!init) return Response.json(items);
    if (path.endsWith('/choices')) {
      const item = path.includes('/two/') ? items[1] : items[0];
      return Response.json({
        ...item,
        choices: ['Hello', 'Goodbye', 'Welcome', 'Farewell'],
      });
    }
    return Response.json({ result: 'correct', correct_word: 'Hello' });
  });
  await h.flush();
  await h.button('Multiple choice').props.onPress();
  await h.flush();
  h.button('A. Hello').props.onPress();
  await h.flush();
  h.button('Next word').props.onPress();
  await h.flush();
  assert.ok(h.button('A. Hello'));
  assert.equal(h.input(), undefined);
  assert.equal(
    h.progress().props.accessibilityLabel,
    'Word 2 of 2, 100% complete',
  );
  assert.equal(
    paths.filter((path) => path.startsWith('/reviews/session')).length,
    1,
  );
  assert.ok(paths.includes('/reviews/two/choices'));
});

test('option load failure returns to focused typing and can retry the current prompt', async () => {
  let fail = true;
  let resolveOptions;
  const prompt = { ...prompts[0], review_token: 'signed' };
  const h = harness(async (path) => {
    if (path.startsWith('/reviews/session')) return Response.json([prompt]);
    if (fail)
      return new Promise((resolve) => {
        resolveOptions = resolve;
      });
    return Response.json({
      ...prompt,
      choices: ['Hello', 'Goodbye', 'Welcome', 'Farewell'],
    });
  });
  await h.flush();
  const before = h.focusCalls();
  h.button('Multiple choice').props.onPress();
  await h.flush();
  assert.equal(h.input().props.editable, false);
  resolveOptions(Response.json({}, { status: 503 }));
  await h.flush();
  assert.ok(h.input());
  assert.ok(h.focusCalls() > before);
  assert.match(h.text(), /Could not load answer options/);
  fail = false;
  await h.button('Multiple choice').props.onPress();
  await h.flush();
  assert.ok(h.button('A. Hello'));
  assert.doesNotMatch(h.text(), /Could not load answer options/);
});

// Web covers every mode/result pair; native cases cover each announcement outcome.
for (const [platform, mode, result] of [
  ['web', 'typing', 'correct'],
  ['web', 'typing', 'incorrect'],
  ['web', 'choice', 'correct'],
  ['web', 'choice', 'incorrect'],
  ['android', 'typing', 'correct'],
  ['android', 'choice', 'incorrect'],
  ['ios', 'typing', 'correct'],
  ['ios', 'choice', 'incorrect'],
]) {
  test(`${platform} ${mode} ${result} feedback reveals labeled answers, announces and clears on Next word`, async () => {
    const items = [
      { ...prompts[0], review_token: 'signed-one' },
      {
        ...prompts[0],
        word_id: 'two',
        attempt_id: 'attempt-two',
        review_token: 'signed-two',
      },
    ];
    const h = harness(
      async (path, init) => {
        if (!init) return Response.json(items);
        if (path.endsWith('/choices'))
          return Response.json({
            ...items[path.includes('/two/') ? 1 : 0],
            choices: ['Hello', 'Goodbye', 'Welcome', 'Farewell'],
          });
        return Response.json({ result, correct_word: 'Hello' });
      },
      {},
      'review',
      platform,
    );
    await h.flush();
    assert.equal(h.feedback(), undefined);
    assert.equal(h.button('Next word'), undefined);
    assert.equal(h.liveRegion().props.children, '');
    const draft =
      result === 'correct' ? 'Hello' : mode === 'choice' ? 'Goodbye' : 'helo';
    if (mode === 'choice') {
      h.button('Multiple choice').props.onPress();
      await h.flush();
      h.button(
        result === 'correct' ? 'A. Hello' : 'B. Goodbye',
      ).props.onPress();
    } else {
      h.input().props.onChangeText(draft);
    }
    await h.flush();
    if (mode === 'typing') h.button('Check answer').props.onPress();
    await h.flush();
    assert.ok(h.feedback());
    if (result === 'correct') {
      assert.match(h.feedbackText(), /Correct answer!CORRECT WORDHello/);
      assert.equal(
        h.liveRegion().props.children,
        'Correct answer! The word is Hello.',
      );
    } else {
      assert.match(h.feedbackText(), /Incorrect answer/);
      assert.ok(
        h.feedbackText().includes(`YOUR ANSWER${draft}CORRECT WORDHello`),
      );
      assert.equal(
        h.liveRegion().props.children,
        `Incorrect answer. Your answer: ${draft}. Correct word: Hello.`,
      );
    }
    assert.equal(h.liveRegion().props.accessibilityLiveRegion, 'polite');
    if (platform === 'web')
      assert.equal(h.liveRegion().props.accessibilityRole, 'status');
    if (platform === 'ios')
      assert.deepEqual(h.announcements(), [h.liveRegion().props.children]);
    assert.equal(h.input(), undefined);
    assert.ok(h.button('Next word'));
    assert.equal(h.button('Check answer'), undefined);
    h.button('Next word').props.onPress();
    await h.flush();
    assert.equal(h.feedback(), undefined);
    assert.equal(h.liveRegion().props.children, '');
    assert.equal(h.button('Next word'), undefined);
    assert.ok(h.sentence());
  });
}

for (const screen of ['index', 'review-preparation']) {
  for (const state of [
    {
      name: 'empty bank',
      saved_count: 0,
      due_count: 0,
      daily_remaining: 20,
      matching_count: 0,
      count: 0,
      title: 'Empty word bank',
      action: 'Add your first word',
    },
    {
      name: 'nothing due',
      saved_count: 3,
      due_count: 0,
      daily_remaining: 20,
      matching_count: 0,
      count: 0,
      title: "You're all caught up",
      action: 'Add word',
    },
  ]) {
    test(`${screen} distinguishes ${state.name} and links to Add word`, async () => {
      const h = harness(async () => Response.json(state), {}, screen);
      assert.doesNotMatch(
        h.text(),
        /Empty word bank|You're all caught up|Daily review limit reached/,
      );
      if (screen === 'index') await h.flush();
      else await h.advance();
      assert.ok(h.text().includes(state.title));
      assert.equal(h.navigation(state.action).props.href, '/add-word');
      assert.doesNotMatch(h.text(), /Sample data/);
    });
  }
}

test('preparation distinguishes a filter with no matches from being caught up', async () => {
  const h = harness(
    async () =>
      Response.json({
        count: 0,
        matching_count: 0,
        saved_count: 3,
        due_count: 2,
        daily_remaining: 20,
      }),
    {},
    'review-preparation',
  );
  await h.advance();
  assert.match(h.text(), /No words match this review/);
  assert.doesNotMatch(h.text(), /You're all caught up/);
  assert.equal(h.navigation('Add word').props.href, '/add-word');
  assert.equal(h.link(), undefined);
});

for (const screen of ['index', 'review-preparation']) {
  test(`${screen} refreshes after returning from Add word`, async () => {
    let saved = 0;
    const h = harness(
      async () =>
        Response.json({
          saved_count: saved,
          due_count: saved,
          daily_remaining: 20,
          count: saved,
          matching_count: saved,
        }),
      {},
      screen,
    );
    if (screen === 'index') await h.flush();
    else await h.advance();
    assert.match(h.text(), /Empty word bank/);
    saved = 1;
    h.refocus();
    if (screen === 'index') await h.flush();
    else await h.advance();
    assert.doesNotMatch(h.text(), /Empty word bank/);
    if (screen === 'index') assert.match(h.text(), /1 saved words/);
    else assert.match(h.text(), /1 words ready/);
  });
}

test('Home retries a network failure without displaying a false empty state', async () => {
  let fail = true;
  const h = harness(
    async () => {
      if (fail) throw new Error('offline');
      return Response.json({
        saved_count: 0,
        due_count: 0,
        daily_remaining: 20,
      });
    },
    {},
    'index',
  );
  await h.flush();
  assert.match(h.text(), /Could not load your progress/);
  assert.doesNotMatch(h.text(), /Empty word bank|You're all caught up/);
  fail = false;
  h.button('Try again').props.onPress();
  await h.flush();
  await h.flush();
  assert.match(h.text(), /Empty word bank/);
});

test('the final Next word finishes all twelve words with a count and Home link', async () => {
  let loads = 0;
  const h = harness(async (_, init) => {
    if (!init) {
      loads++;
      return Response.json(
        Array.from({ length: 12 }, (_, index) => ({
          ...prompts[0],
          word_id: String(index),
          attempt_id: `attempt-${index}`,
        })),
      );
    }
    return Response.json({ result: 'correct', correct_word: 'Hello' });
  });
  await h.flush();
  for (let index = 0; index < 12; index++) {
    const percent = Math.round(((index + 1) / 12) * 100);
    assert.equal(
      h.progress().props.accessibilityLabel,
      `Word ${index + 1} of 12, ${percent}% complete`,
    );
    assert.match(h.text(), new RegExp(`${percent}% complete`));
    assert.ok(h.sentence());
    assert.doesNotMatch(h.text(), /Hello/);
    h.input().props.onChangeText('Hello');
    await h.flush();
    h.button('Check answer').props.onPress();
    await h.flush();
    assert.ok(h.sentence());
    h.button('Next word').props.onPress();
    await h.flush();
  }
  assert.match(h.text(), /Review finished/);
  assert.match(h.text(), /You reviewed all 12 words/);
  assert.match(h.text(), /12 of 12 answers correct/);
  assert.match(h.liveRegion().props.children, /You reviewed all 12 words/);
  assert.equal(h.navigation('Back to Home').props.href, '/');
  assert.equal(h.input(), undefined);
  assert.equal(h.button('Next word'), undefined);
  assert.equal(loads, 1);
});

test('session conflict does not claim every snapshot word was reviewed', async () => {
  let submissions = 0;
  const h = harness(async (_, init) => {
    if (!init)
      return Response.json([
        prompts[0],
        { ...prompts[0], word_id: 'two', attempt_id: 'two' },
      ]);
    submissions++;
    return submissions === 1
      ? Response.json({ result: 'correct', correct_word: 'Hello' })
      : Response.json(
          { detail: 'Review session expired or changed' },
          { status: 409 },
        );
  });
  await h.flush();
  h.input().props.onChangeText('Hello');
  await h.flush();
  h.button('Check answer').props.onPress();
  await h.flush();
  h.button('Next word').props.onPress();
  await h.flush();
  h.input().props.onChangeText('Hello');
  await h.flush();
  h.button('Check answer').props.onPress();
  await h.flush();
  h.button('Next word').props.onPress();
  await h.flush();
  assert.match(h.text(), /You reviewed 1 of 2 words/);
  assert.doesNotMatch(h.text(), /You reviewed all 2/);
});

test('choice submits once on rapid taps and retries the original answer after failure', async () => {
  const bodies = [];
  let rejectRequest;
  const h = harness(async (_, init) => {
    if (!init)
      return Response.json([
        { ...prompts[0], choices: ['Hello', 'Goodbye', 'Welcome', 'Farewell'] },
      ]);
    bodies.push(init.body);
    if (bodies.length === 1)
      return new Promise((_, reject) => {
        rejectRequest = reject;
      });
    return Response.json({ result: 'correct', correct_word: 'Hello' });
  });
  await h.flush();
  h.button('Multiple choice').props.onPress();
  await h.flush();
  h.button('A. Hello').props.onPress();
  h.button('B. Goodbye').props.onPress();
  assert.equal(bodies.length, 1);
  rejectRequest(new Error('offline'));
  await h.flush();
  assert.equal(h.button('Check answer'), undefined);
  assert.equal(h.button('A. Hello').props.disabled, true);
  assert.equal(h.button('A. Hello').props.accessibilityState.checked, true);
  await h.button('Retry submission').props.onPress();
  await h.flush();
  assert.equal(bodies.length, 2);
  assert.equal(bodies[0], bodies[1]);
  assert.equal(JSON.parse(bodies[0]).typed_answer, 'Hello');
  assert.match(h.feedbackText(), /Correct answer/);
});
