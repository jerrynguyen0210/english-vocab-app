import * as SecureStore from 'expo-secure-store';

const KEY = 'wordrecall.refresh';
// The only app-managed persistent value in R0. Keep the existing key/service so
// installed sessions remain readable; rotation applies these options on write.
const OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};
export const readRefreshToken = () => SecureStore.getItemAsync(KEY, OPTIONS);
export const writeRefreshToken = (value: string) =>
  SecureStore.setItemAsync(KEY, value, OPTIONS);
export const clearRefreshToken = () =>
  SecureStore.deleteItemAsync(KEY, OPTIONS);
export const nativeAuth = true;
