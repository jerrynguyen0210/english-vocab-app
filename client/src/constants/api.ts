import { validateApiBaseUrl } from './api-config.ts';

/** Native devices reach the API through its configured LAN or deployed URL. */
export function getApiBaseUrl(): string {
  return validateApiBaseUrl(process.env.EXPO_PUBLIC_API_BASE_URL);
}
