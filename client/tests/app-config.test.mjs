import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const configure = require('../app.config.js');
const { expo: config } = require('../app.json');

test('Jetson SPA export preserves native identity and the default server build', () => {
  const previous = process.env.WORDRECALL_WEB_OUTPUT;
  try {
    delete process.env.WORDRECALL_WEB_OUTPUT;
    assert.equal(configure({ config }).web.output, 'server');
    process.env.WORDRECALL_WEB_OUTPUT = 'single';
    const spa = configure({ config });
    assert.equal(spa.web.output, 'single');
    assert.deepEqual(spa.ios, config.ios);
    assert.deepEqual(spa.android, config.android);
    assert.deepEqual(spa.plugins, config.plugins);
    assert.equal(config.web.output, 'server');
    process.env.WORDRECALL_WEB_OUTPUT = 'unsupported';
    assert.throws(() => configure({ config }), /WORDRECALL_WEB_OUTPUT/);
  } finally {
    if (previous === undefined) delete process.env.WORDRECALL_WEB_OUTPUT;
    else process.env.WORDRECALL_WEB_OUTPUT = previous;
  }
});
