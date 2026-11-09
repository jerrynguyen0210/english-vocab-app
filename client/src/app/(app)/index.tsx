import { Link } from 'expo-router';
import { Screen } from '@/components/screen';
import { ThemedText } from '@/components/themed-text';
export default function HomeScreen() {
  return (
    <Screen>
      <ThemedText type="title">Your vocabulary</ThemedText>
      <Link href="/add-word">Add word</Link>
      <Link href="/review">Review</Link>
      <Link href="/account">Account</Link>
    </Screen>
  );
}
