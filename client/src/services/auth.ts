import { getApiBaseUrl } from '../constants/api';
import {
  clearRefreshToken,
  nativeAuth,
  readRefreshToken,
  writeRefreshToken,
} from './refresh-storage';

let accessToken: string | null = null;
let refreshPending: Promise<void> | null = null;
let sessionVersion = 0;
let refreshVersion = 0;
let storagePending: Promise<void> = Promise.resolve();

function updateStorage(operation: () => Promise<void>) {
  const pending = storagePending.then(operation);
  storagePending = pending.catch(() => {});
  return pending;
}
const expiryListeners = new Set<() => void>();

export function onSessionExpired(listener: () => void) {
  expiryListeners.add(listener);
  return () => {
    expiryListeners.delete(listener);
  };
}

async function expireSession(version = sessionVersion) {
  if (version !== sessionVersion) return;
  accessToken = null;
  try {
    await updateStorage(async () => {
      if (version === sessionVersion) await clearRefreshToken();
    });
  } finally {
    if (version === sessionVersion)
      expiryListeners.forEach((listener) => listener());
  }
}

export class AuthError extends Error {
  constructor(public status: number) {
    super(`Authentication request failed (${status}).`);
  }
}

async function authRequest(path: string, body: object) {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/auth/${path}`, {
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

async function acceptTokens(response: Response, version = sessionVersion) {
  const tokens: { access_token: string; refresh_token?: string } =
    await response.json();
  if (version !== sessionVersion)
    throw new Error('Session changed during request.');
  if (typeof tokens.access_token !== 'string' || !tokens.access_token)
    throw new Error('Missing access credential.');
  if (nativeAuth) {
    if (!tokens.refresh_token) throw new Error('Missing refresh credential.');
    const refreshToken = tokens.refresh_token;
    await updateStorage(async () => {
      if (version === sessionVersion) await writeRefreshToken(refreshToken);
    });
  }
  if (version !== sessionVersion)
    throw new Error('Session changed during request.');
  accessToken = tokens.access_token;
}

export async function register(email: string, password: string, name: string) {
  const version = ++sessionVersion;
  await acceptTokens(
    await authRequest('register', { email, password, name }),
    version,
  );
}

export async function signIn(email: string, password: string) {
  const version = ++sessionVersion;
  await acceptTokens(
    await authRequest('sign-in', { email, password }),
    version,
  );
}

// Single-flight refresh prevents concurrent requests from reusing rotated tokens.
// Call on startup to restore a session; access tokens are never persisted.
export function refreshSession(): Promise<void> {
  if (!refreshPending || refreshVersion !== sessionVersion) {
    const version = sessionVersion;
    refreshVersion = version;
    const pending = (async () => {
      try {
        const refresh_token = await readRefreshToken();
        if (nativeAuth && !refresh_token) throw new AuthError(401);
        await acceptTokens(
          await authRequest('refresh', { refresh_token }),
          version,
        );
      } catch (error) {
        if (
          version === sessionVersion &&
          error instanceof AuthError &&
          error.status === 401
        )
          await expireSession(version);
        throw error;
      }
    })().finally(() => {
      if (refreshPending === pending) refreshPending = null;
    });
    refreshPending = pending;
  }
  return refreshPending;
}

export async function signOut() {
  const version = ++sessionVersion;
  const refresh_token = await readRefreshToken();
  try {
    await authRequest('logout', { refresh_token });
  } catch (error) {
    if (!(error instanceof AuthError && error.status === 401)) throw error;
  }
  if (version !== sessionVersion)
    throw new Error('Session changed during request.');
  accessToken = null;
  await updateStorage(async () => {
    if (version === sessionVersion) await clearRefreshToken();
  });
}

/** Use for replayable JSON API requests; refresh once after an expired token. */
export async function authenticatedFetch(path: string, init: RequestInit = {}) {
  if (!path.startsWith('/') || path.startsWith('//'))
    throw new Error('Expected an API-relative path.');
  if (!accessToken) await refreshSession();
  const send = (token: string | null) => {
    const headers = new Headers(init.headers);
    headers.set('Authorization', `Bearer ${token}`);
    return fetch(`${getApiBaseUrl()}/api/v1${path}`, {
      ...init,
      headers,
      credentials: 'omit',
    });
  };
  const requestVersion = sessionVersion;
  const attemptedToken = accessToken;
  const response = await send(attemptedToken);
  if (requestVersion !== sessionVersion)
    throw new Error('Session changed during request.');
  if (response.status !== 401) return response;
  // Another request may already have rotated the token while this one was in flight.
  if (accessToken === attemptedToken) await refreshSession();
  if (requestVersion !== sessionVersion)
    throw new Error('Session changed during request.');
  const retryToken = accessToken;
  const retried = await send(retryToken);
  if (requestVersion !== sessionVersion)
    throw new Error('Session changed during request.');
  if (retried.status === 401 && accessToken === retryToken) {
    await expireSession(requestVersion);
    throw new AuthError(401);
  }
  return retried;
}
