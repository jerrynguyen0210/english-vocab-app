import { CONNECTIVITY_MESSAGE } from '@/services/connectivity';
import {
  DarkTheme,
  DefaultTheme,
  ThemeProvider,
  Stack,
  usePathname,
} from 'expo-router';
import {
  ActivityIndicator,
  Button,
  Modal,
  View,
  useColorScheme,
} from 'react-native';
import { SessionProvider, useSession } from '@/context/session';
import { Screen } from '@/components/screen';
import { ThemedText } from '@/components/themed-text';
import { AuthForm } from '@/components/auth-form';

function Navigation() {
  const { loading, signedIn, needsSignIn, restoreError, retryRestore, appKey } =
    useSession();
  const pathname = usePathname();
  const protectedLink = ['/add-word', '/review', '/account'].includes(pathname);
  if (loading)
    return (
      <Screen>
        <ActivityIndicator accessibilityLabel="Loading session" />
        <ThemedText>Restoring your session…</ThemedText>
      </Screen>
    );
  if (restoreError && !signedIn && !needsSignIn)
    return (
      <Screen>
        <ThemedText accessibilityRole="alert">
          {CONNECTIVITY_MESSAGE}
        </ThemedText>
        <Button title="Retry" onPress={retryRestore} />
      </Screen>
    );
  const keepApp = signedIn || needsSignIn || (protectedLink && appKey === 0);
  return (
    <View style={{ flex: 1 }}>
      {restoreError && signedIn ? (
        <View accessibilityLiveRegion="polite">
          <ThemedText>
            {CONNECTIVITY_MESSAGE} Your work is still here.
          </ThemedText>
          <Button title="Retry connection" onPress={retryRestore} />
        </View>
      ) : null}
      <Stack key={appKey} screenOptions={{ headerShown: false }}>
        <Stack.Protected guard={!keepApp}>
          <Stack.Screen name="(auth)" />
        </Stack.Protected>
        <Stack.Protected guard={keepApp}>
          <Stack.Screen name="(app)" />
        </Stack.Protected>
      </Stack>
      <Modal
        visible={keepApp && !signedIn}
        animationType="slide"
        presentationStyle="fullScreen"
        onRequestClose={() => {}}
        accessibilityLabel="Sign in to continue"
      >
        <AuthForm reauthenticate />
      </Modal>
    </View>
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
