/** Validate public API configuration shared by web and native. */
export function validateApiBaseUrl(configured: string | undefined): string {
  const value = configured?.trim();
  if (!value) {
    throw new Error('Set EXPO_PUBLIC_API_BASE_URL for this environment.');
  }
  const url = new URL(value);
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.username ||
    url.password
  ) {
    throw new Error(
      'EXPO_PUBLIC_API_BASE_URL must be an HTTP(S) URL without credentials.',
    );
  }
  if (url.search || url.hash) {
    throw new Error(
      'EXPO_PUBLIC_API_BASE_URL must not contain a query or fragment.',
    );
  }
  return value.replace(/\/+$/, '');
}
