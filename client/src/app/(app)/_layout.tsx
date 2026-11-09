import { Stack } from 'expo-router';
export const unstable_settings = { anchor: 'index' };

export default function AppLayout() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ title: 'Home' }} />
      <Stack.Screen name="add-word" options={{ title: 'Add word' }} />
      <Stack.Screen name="review" options={{ title: 'Review' }} />
      <Stack.Screen name="account" options={{ title: 'Account' }} />
    </Stack>
  );
}
