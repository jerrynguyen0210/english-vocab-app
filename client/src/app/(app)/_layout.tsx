import { Stack } from 'expo-router';
export const unstable_settings = { anchor: 'index' };

export default function AppLayout() {
  return (
    <Stack>
      <Stack.Screen
        name="index"
        options={{ title: 'Home', headerShown: false }}
      />
      <Stack.Screen
        name="add-word"
        options={{ title: 'Add word', headerShown: false }}
      />
      <Stack.Screen
        name="review"
        options={{ title: 'Review', headerShown: false }}
      />
      <Stack.Screen
        name="account"
        options={{ title: 'Account', headerShown: false }}
      />
    </Stack>
  );
}
