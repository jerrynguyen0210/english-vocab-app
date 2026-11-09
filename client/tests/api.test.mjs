import assert from 'node:assert/strict';
import { test } from 'node:test';

import { getApiBaseUrl } from '../src/constants/api.ts';

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
