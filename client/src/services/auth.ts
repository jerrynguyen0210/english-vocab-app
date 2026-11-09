import { getApiBaseUrl } from '../constants/api';
import {
  clearRefreshToken,
  nativeAuth,
  readRefreshToken,
  writeRefreshToken,
} from './refresh-storage';

let accessToken: string | null = null;
let refreshPending: Promise<void> | null = null;

export class AuthError extends Error {
  constructor(public status: number) {
    super(`Authentication request failed (${status}).`);
  }
}

async function authRequest(path: string, body: object) {
  const response = await fetch(`${getApiBaseUrl()}/auth/${path}`, {
    method: 'POST',
    credentials: nativeAuth ? 'omit' : 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(nativeAuth ? { 'X-Auth-Platform': 'native' } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new AuthError(response.status);
  return response;
}

async function acceptTokens(response: Response) {
  const tokens: { access_token: string; refresh_token?: string } =
    await response.json();
  if (nativeAuth) {
    if (!tokens.refresh_token) throw new Error('Missing refresh credential.');
    await writeRefreshToken(tokens.refresh_token);
  }
  accessToken = tokens.access_token;
}

export async function register(email: string, password: string) {
  await acceptTokens(await authRequest('register', { email, password }));
}

export async function signIn(email: string, password: string) {
  await acceptTokens(await authRequest('sign-in', { email, password }));
}

// Single-flight refresh prevents concurrent requests from reusing rotated tokens.
// Call on startup to restore a session; access tokens are never persisted.
export function refreshSession(): Promise<void> {
  if (!refreshPending) {
    refreshPending = (async () => {
      try {
        const refresh_token = await readRefreshToken();
        await acceptTokens(await authRequest('refresh', { refresh_token }));
      } catch (error) {
        accessToken = null;
        if (error instanceof AuthError && error.status === 401)
          await clearRefreshToken();
        throw error;
      }
    })().finally(() => {
      refreshPending = null;
    });
  }
  return refreshPending;
}

export async function signOut() {
  const refresh_token = await readRefreshToken();
  try {
    await authRequest('logout', { refresh_token });
  } catch (error) {
    if (!(error instanceof AuthError && error.status === 401)) throw error;
  }
  accessToken = null;
  await clearRefreshToken();
}

/** Use for replayable JSON API requests; refresh once after an expired token. */
export async function authenticatedFetch(path: string, init: RequestInit = {}) {
  if (!path.startsWith('/') || path.startsWith('//'))
    throw new Error('Expected an API-relative path.');
  if (!accessToken) await refreshSession();
  const send = () => {
    const headers = new Headers(init.headers);
    headers.set('Authorization', `Bearer ${accessToken}`);
    return fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers,
      credentials: 'omit',
    });
  };
  const response = await send();
  if (response.status !== 401) return response;
  await refreshSession();
  return send();
}
