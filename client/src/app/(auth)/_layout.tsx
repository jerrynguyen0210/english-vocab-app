import { Stack } from 'expo-router';
export const unstable_settings = { anchor: 'sign-up' };

export default function AuthLayout() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="sign-up" options={{ title: 'Sign up' }} />
      <Stack.Screen name="sign-in" options={{ title: 'Sign in' }} />
    </Stack>
  );
}
