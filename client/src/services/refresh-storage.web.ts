// Browser refresh credentials belong only in the API's HttpOnly cookie.
export const readRefreshToken = async (): Promise<string | null> => null;
export const writeRefreshToken = async (_value: string): Promise<void> => {};
export const clearRefreshToken = async (): Promise<void> => {};
export const nativeAuth = false;
