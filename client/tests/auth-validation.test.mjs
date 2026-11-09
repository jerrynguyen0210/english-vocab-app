import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  validateCredentials,
  validateName,
  authErrorMessage,
} from '../src/utils/auth-validation.ts';

test('credentials require email and password and reject malformed emails', () => {
  assert.deepEqual(validateCredentials('', ''), {
    email: 'Enter your email address.',
    password: 'Enter your password.',
  });
  for (const email of [
    'example.com',
    'a@',
    'a b@example.com',
    'a@@example.com',
  ]) {
    assert.ok(validateCredentials(email, 'a'.repeat(12)).email);
  }
  assert.deepEqual(
    validateCredentials(' learner@example.com ', 'a'.repeat(12)),
    {},
  );
});

test('password validation matches server length boundaries without trimming passwords', () => {
  for (const length of [11, 129])
    assert.ok(
      validateCredentials('learner@example.com', 'a'.repeat(length)).password,
    );
  for (const password of [
    'a'.repeat(12),
    'a'.repeat(128),
    ' a'.repeat(6),
    '🔑'.repeat(12),
  ]) {
    assert.deepEqual(validateCredentials('learner@example.com', password), {});
  }
});

test('authentication errors distinguish retry and credential failures', () => {
  assert.match(authErrorMessage(401, false), /incorrect/);
  assert.match(authErrorMessage(409, true), /signing in/);
  assert.match(authErrorMessage(429, false), /wait/);
  assert.match(authErrorMessage(503, false), /temporarily unavailable/);
  assert.match(authErrorMessage(undefined, true), /connection/);
});

test('sign-up names are required, trimmed, and limited to 100 characters', () => {
  assert.ok(validateName('   '));
  assert.ok(validateName('A'.repeat(101)));
  assert.equal(validateName(' Alex '), undefined);
  assert.equal(validateName('李明'), undefined);
  assert.equal(validateName('A'.repeat(100)), undefined);
});
