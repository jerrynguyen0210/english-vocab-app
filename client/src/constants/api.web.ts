import { validateApiBaseUrl } from './api-config.ts';

function isLocalHost(host: string): boolean {
  if (['localhost', '127.0.0.1', '[::1]'].includes(host)) return true;
  const octets = host.split('.').map(Number);
  if (
    octets.length !== 4 ||
    octets.some((n) => !Number.isInteger(n) || n < 0 || n > 255)
  )
    return false;
  return (
    octets[0] === 10 ||
    (octets[0] === 192 && octets[1] === 168) ||
    (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31)
  );
}

/** Keep local browser requests on the page's host so session cookies work. */
export function getApiBaseUrl(): string {
  const configured = validateApiBaseUrl(
    process.env.EXPO_PUBLIC_WEB_API_BASE_URL ??
      process.env.EXPO_PUBLIC_API_BASE_URL,
  );
  const url = new URL(configured);
  if (
    process.env.NODE_ENV !== 'production' &&
    typeof window !== 'undefined' &&
    window.location.protocol === 'http:' &&
    url.protocol === 'http:' &&
    ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) &&
    isLocalHost(window.location.hostname)
  ) {
    url.hostname = window.location.hostname;
    return url.toString().replace(/\/+$/, '');
  }
  return configured;
}
