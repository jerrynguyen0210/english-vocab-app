import assert from 'node:assert/strict';
import { test } from 'node:test';

import { getApiBaseUrl } from '../src/constants/api.ts';
import { getApiBaseUrl as getWebApiBaseUrl } from '../src/constants/api.web.ts';

test('API base URL follows the selected environment and trims trailing slashes', () => {
  const previous = process.env.EXPO_PUBLIC_API_BASE_URL;
  try {
    for (const url of [
      'http://192.168.0.50:8001',
      'https://preview-api.example.com',
      'https://api.example.com/v1',
    ]) {
      process.env.EXPO_PUBLIC_API_BASE_URL = ` ${url}/ `;
      assert.equal(getApiBaseUrl(), url);
    }
  } finally {
    restoreEnvironment(previous);
  }
});

test('API configuration rejects missing, malformed, or credential-bearing URLs', () => {
  const previous = process.env.EXPO_PUBLIC_API_BASE_URL;
  try {
    delete process.env.EXPO_PUBLIC_API_BASE_URL;
    assert.throws(getApiBaseUrl);
    for (const value of [
      '',
      'not-a-url',
      'ftp://example.com',
      'https://user:placeholder@example.com',
      'https://api.example.com?token=placeholder',
      'https://api.example.com#fragment',
    ]) {
      process.env.EXPO_PUBLIC_API_BASE_URL = value;
      assert.throws(getApiBaseUrl);
    }
  } finally {
    restoreEnvironment(previous);
  }
});

function restoreEnvironment(value) {
  if (value === undefined) {
    delete process.env.EXPO_PUBLIC_API_BASE_URL;
  } else {
    process.env.EXPO_PUBLIC_API_BASE_URL = value;
  }
}

test('web API override keeps native LAN configuration unchanged', () => {
  const native = process.env.EXPO_PUBLIC_API_BASE_URL;
  const web = process.env.EXPO_PUBLIC_WEB_API_BASE_URL;
  try {
    process.env.EXPO_PUBLIC_API_BASE_URL = 'http://192.168.0.50:8001';
    process.env.EXPO_PUBLIC_WEB_API_BASE_URL = 'http://localhost:8001/';
    assert.equal(getApiBaseUrl(), 'http://192.168.0.50:8001');
    assert.equal(getWebApiBaseUrl(), 'http://localhost:8001');
    delete process.env.EXPO_PUBLIC_WEB_API_BASE_URL;
    assert.equal(getWebApiBaseUrl(), getApiBaseUrl());
    process.env.EXPO_PUBLIC_WEB_API_BASE_URL = 'not-a-url';
    assert.throws(getWebApiBaseUrl);
  } finally {
    restoreEnvironment(native);
    if (web === undefined) delete process.env.EXPO_PUBLIC_WEB_API_BASE_URL;
    else process.env.EXPO_PUBLIC_WEB_API_BASE_URL = web;
  }
});

test('local web development follows the page host without rewriting production APIs', () => {
  const previousWindow = globalThis.window;
  const previousWeb = process.env.EXPO_PUBLIC_WEB_API_BASE_URL;
  const previousMode = process.env.NODE_ENV;
  try {
    process.env.NODE_ENV = 'development';
    process.env.EXPO_PUBLIC_WEB_API_BASE_URL = 'http://localhost:8001';
    globalThis.window = { location: new URL('http://192.168.0.50:8081') };
    assert.equal(getWebApiBaseUrl(), 'http://192.168.0.50:8001');
    globalThis.window = { location: new URL('http://localhost:8081') };
    assert.equal(getWebApiBaseUrl(), 'http://localhost:8001');
    globalThis.window = { location: new URL('https://app.example.com') };
    assert.equal(getWebApiBaseUrl(), 'http://localhost:8001');
    globalThis.window = { location: new URL('http://192.168.0.50:8081') };
    process.env.NODE_ENV = 'production';
    assert.equal(getWebApiBaseUrl(), 'http://localhost:8001');
    process.env.NODE_ENV = 'development';
    process.env.EXPO_PUBLIC_WEB_API_BASE_URL = 'https://api.example.com';
    assert.equal(getWebApiBaseUrl(), 'https://api.example.com');
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
    if (previousWeb === undefined)
      delete process.env.EXPO_PUBLIC_WEB_API_BASE_URL;
    else process.env.EXPO_PUBLIC_WEB_API_BASE_URL = previousWeb;
    if (previousMode === undefined) delete process.env.NODE_ENV;
    else process.env.NODE_ENV = previousMode;
  }
});
