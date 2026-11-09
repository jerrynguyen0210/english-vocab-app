import { Link } from 'expo-router';
import { useState } from 'react';
import { Button, TextInput, StyleSheet } from 'react-native';
import { Screen } from '@/components/screen';
import { ThemedText } from '@/components/themed-text';
import { useSession } from '@/context/session';
import { useTheme } from '@/hooks/use-theme';

export function AuthForm({ signUp = false }: { signUp?: boolean }) {
  const session = useSession();
  const theme = useTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  async function submit() {
    setPending(true);
    setError('');
    try {
      await (signUp ? session.signUp : session.signIn)(email.trim(), password);
    } catch {
      setError(
        'Unable to ' +
          (signUp ? 'create your account' : 'sign in') +
          '. Check your details and connection, then try again.',
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <Screen>
      <ThemedText type="title">{signUp ? 'Sign up' : 'Sign in'}</ThemedText>
      <TextInput
        accessibilityLabel="Email"
        placeholder="Email"
        placeholderTextColor={theme.textSecondary}
        style={[
          styles.input,
          { color: theme.text, borderColor: theme.textSecondary },
        ]}
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
        autoComplete="email"
        editable={!pending}
      />
      <TextInput
        accessibilityLabel="Password"
        placeholder="Password"
        placeholderTextColor={theme.textSecondary}
        style={[
          styles.input,
          { color: theme.text, borderColor: theme.textSecondary },
        ]}
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoCapitalize="none"
        autoComplete={signUp ? 'new-password' : 'current-password'}
        editable={!pending}
      />
      {error ? (
        <ThemedText accessibilityRole="alert">{error}</ThemedText>
      ) : null}
      <Button
        title={pending ? 'Please wait…' : signUp ? 'Sign up' : 'Sign in'}
        onPress={submit}
        disabled={pending || !email.trim() || !password}
      />
      <Link href={signUp ? '/sign-in' : '/sign-up'}>
        {signUp ? 'Already have an account? Sign in' : 'Create an account'}
      </Link>
    </Screen>
  );
}
const styles = StyleSheet.create({
  input: { borderWidth: 1, borderRadius: 8, padding: 14, fontSize: 16 },
});
