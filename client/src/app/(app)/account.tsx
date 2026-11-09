import { useState } from 'react';
import { Button } from 'react-native';
import { Screen } from '@/components/screen';
import { ThemedText } from '@/components/themed-text';
import { useSession } from '@/context/session';
export default function AccountScreen() {
  const { signOut } = useSession();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  async function logout() {
    setPending(true);
    setError('');
    try {
      await signOut();
    } catch {
      setError('Unable to sign out. Check your connection and try again.');
    } finally {
      setPending(false);
    }
  }
  return (
    <Screen>
      <ThemedText type="title">Account</ThemedText>
      {error ? (
        <ThemedText accessibilityRole="alert">{error}</ThemedText>
      ) : null}
      <Button
        title={pending ? 'Signing out…' : 'Sign out'}
        disabled={pending}
        onPress={logout}
      />
    </Screen>
  );
}
