import { DarkTheme, DefaultTheme, ThemeProvider, Stack } from 'expo-router';
import { ActivityIndicator, useColorScheme } from 'react-native';
import { SessionProvider, useSession } from '@/context/session';
import { Screen } from '@/components/screen';
import { ThemedText } from '@/components/themed-text';

function Navigation() {
  const { loading, signedIn } = useSession();
  if (loading)
    return (
      <Screen>
        <ActivityIndicator accessibilityLabel="Loading session" />
        <ThemedText>Restoring your session…</ThemedText>
      </Screen>
    );
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
      <Stack.Protected guard={signedIn}>
        <Stack.Screen name="(app)" />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  const colorScheme = useColorScheme();
  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <SessionProvider>
        <Navigation />
      </SessionProvider>
    </ThemeProvider>
  );
}
