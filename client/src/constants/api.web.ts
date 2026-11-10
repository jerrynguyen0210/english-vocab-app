import { validateApiBaseUrl } from './api-config.ts';

/** Web may use a same-site URL so browsers can retain the refresh cookie. */
export function getApiBaseUrl(): string {
  return validateApiBaseUrl(
    process.env.EXPO_PUBLIC_WEB_API_BASE_URL ??
      process.env.EXPO_PUBLIC_API_BASE_URL,
  );
}
