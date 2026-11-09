import * as SecureStore from 'expo-secure-store';

const KEY = 'wordrecall.refresh';
export const readRefreshToken = () => SecureStore.getItemAsync(KEY);
export const writeRefreshToken = (value: string) =>
  SecureStore.setItemAsync(KEY, value);
export const clearRefreshToken = () => SecureStore.deleteItemAsync(KEY);
export const nativeAuth = true;
